import hashlib
import json
from pathlib import Path
import threading
from http.server import ThreadingHTTPServer
import urllib.request
import urllib.error

import pytest

from voice_home import web


@pytest.fixture
def store(tmp_path):
    source = (Path(__file__).parents[1] / 'config.example.yaml').read_text(encoding='utf-8')
    # Existing sample uses a file: provide the referenced test secret explicitly.
    import yaml
    raw = yaml.safe_load(source)
    raw['sip'].pop('password_file', None)
    raw['sip']['password'] = 'test-only-secret'
    raw['openhab'].pop('token_file', None)
    path = tmp_path / 'config.yaml'
    path.write_text(yaml.safe_dump(raw), encoding='utf-8')
    return web.Store(path)


def test_save_validate_conflict_and_versions(store):
    before = store.read()
    with pytest.raises(ValueError):
        store.save('sip: [invalid', before['revision'])
    assert store.read() == before
    after = store.save(before['yaml'] + '\n# changed\n', before['revision'])
    assert after['revision'] != before['revision']
    assert next(store.versions.glob('*.yaml')).read_text() == before['yaml']
    with pytest.raises(ValueError, match='zwischenzeitlich'):
        store.save(before['yaml'], before['revision'])
    assert not list(store.path.parent.glob('.validate-*'))


def test_syntax_diagnostic_never_includes_yaml_secret(store):
    with pytest.raises(ValueError) as error:
        store.validate('password: [very-private-secret')
    assert 'very-private-secret' not in str(error.value)
    assert 'Zeile' in str(error.value)


def test_versions_bounded_and_file_private(store):
    for i in range(25):
        before = store.read()
        store.save(before['yaml'] + f'\n# {i}', before['revision'])
    assert len(list(store.versions.glob('*.yaml'))) == 20


def test_login_reset_sessions_and_rate_limit(store, tmp_path):
    auth = tmp_path / 'password.json'
    salt = 'ab' * 16
    auth.write_text(json.dumps({'salt': salt, 'hash': web.password_hash('correct password', salt)}))
    admin = web.Admin(store.path, auth)
    token, csrf = admin.login('correct password', 'one')
    assert admin.session(token)[2] == csrf
    for _ in range(5):
        assert admin.login('wrong password', 'two') is None
    assert admin.login('correct password', 'two') is None
    auth.write_text('{}')
    assert admin.session(token) is None


def test_restart_requires_disabled_idle_fresh(store, monkeypatch):
    admin = web.Admin(store.path)
    for state in ({'fresh': False}, {'fresh': True, 'accepting': True},
                  {'fresh': True, 'accepting': False, 'busy': True},
                  {'fresh': True, 'accepting': False, 'call_active': True}):
        monkeypatch.setattr(web, 'read_status', lambda: state)
        assert not admin.can_restart()
    monkeypatch.setattr(web, 'read_status', lambda: {'fresh': True, 'accepting': False, 'busy': False})
    assert admin.can_restart()


def test_http_auth_csrf_and_download(store, tmp_path):
    auth = tmp_path / 'auth'
    salt = 'cd' * 16
    auth.write_text(json.dumps({'salt': salt, 'hash': web.password_hash('valid password', salt)}))
    admin = web.Admin(store.path, auth)
    server = ThreadingHTTPServer(('127.0.0.1', 0), web.handler(admin))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    def request(path, data=None, headers=None):
        return urllib.request.urlopen(urllib.request.Request(base+path, data=json.dumps(data).encode() if data is not None else None,
            headers={'Content-Type': 'application/json', **(headers or {})}), timeout=5)
    try:
        with pytest.raises(urllib.error.HTTPError) as error:
            request('/api/config')
        assert error.value.code == 401
        response = request('/api/login', {'password': 'valid password'})
        cookie = response.headers['Set-Cookie']
        assert 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=Strict' in cookie
        csrf = json.load(response)['csrf']
        headers = {'Cookie': cookie.split(';')[0]}
        with pytest.raises(urllib.error.HTTPError) as error:
            request('/api/save', {'yaml': store.read()['yaml'], 'revision': store.read()['revision']}, headers)
        assert error.value.code == 403
        headers['X-CSRF-Token'] = csrf
        assert request('/api/validate', {'yaml': store.read()['yaml']}, headers).status == 200
        response = request('/api/download', headers=headers)
        assert response.headers['Cache-Control'] == 'no-store'
        assert hashlib.sha256(response.read()).hexdigest() == store.read()['revision']
        with pytest.raises(urllib.error.HTTPError):
            request('/api/versions/../../password.json', headers=headers)
    finally:
        server.shutdown()
        server.server_close()


def test_bootstrap_change_persists_and_revokes_sessions(store, tmp_path, monkeypatch):
    auth = tmp_path / 'password.json'
    web.initialize_password(auth)
    admin = web.Admin(store.path, auth)
    assert json.loads(auth.read_text()) == {}
    assert admin.login('admin', 'first') is None
    assert admin.login('', 'first') is None
    answers = iter(['personal password', 'personal password'])
    monkeypatch.setattr(web.getpass, 'getpass', lambda _: next(answers))
    web.reset_password(auth)
    token, _ = admin.login('personal password', 'first')
    other, _ = admin.login('personal password', 'second')
    assert admin.session(token)
    with pytest.raises(ValueError):
        admin.change_password(token, 'wrong', 'x', 'first')
    with pytest.raises(ValueError):
        admin.change_password(token, 'personal password', '', 'first')
    admin.change_password(token, 'personal password', 'x', 'first')
    assert admin.session(token) is None
    assert admin.session(other) is None
    saved = auth.read_bytes()
    web.initialize_password(auth)
    assert auth.read_bytes() == saved
    restarted = web.Admin(store.path, auth)
    assert restarted.login('admin', 'third') is None
    token, _ = restarted.login('x', 'third')
    assert restarted.session(token)
    assert b'x' not in saved


def test_provisioned_http_allows_management_and_optional_short_password(store, tmp_path):
    auth = tmp_path / 'password.json'
    legacy = json.loads(web.password_record('personal password'))
    legacy['must_change'] = True
    auth.write_text(json.dumps(legacy))
    admin = web.Admin(store.path, auth)
    server = ThreadingHTTPServer(('127.0.0.1', 0), web.handler(admin))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'
    token, csrf = admin.login('personal password', 'test')
    headers = {'Cookie': 'session='+token, 'X-CSRF-Token': csrf, 'Content-Type': 'application/json'}
    def request(path, data=None, selected_headers=None):
        return urllib.request.urlopen(urllib.request.Request(base+path,
            data=json.dumps(data).encode() if data is not None else None,
            headers=selected_headers or headers), timeout=5)
    try:
        assert json.load(request('/api/session'))['csrf'] == csrf
        for path in ('config', 'download', 'versions', 'logs', 'status'):
            assert request('/api/'+path).status == 200
        assert request('/api/validate', {'yaml': store.read()['yaml']}).status == 200
        data = {'current_password': 'personal password', 'new_password': 'x'}
        with pytest.raises(urllib.error.HTTPError) as error:
            request('/api/password', data, {'Cookie': 'session='+token, 'Content-Type': 'application/json'})
        assert error.value.code == 403
        assert request('/api/password', data).status == 200
        with pytest.raises(urllib.error.HTTPError) as error:
            request('/api/session')
        assert error.value.code == 401
    finally:
        server.shutdown()
        server.server_close()


def test_console_accepts_short_password(store, tmp_path, monkeypatch):
    auth = tmp_path / 'password.json'
    answers = iter(['a', 'a'])
    monkeypatch.setattr(web.getpass, 'getpass', lambda _: next(answers))
    web.reset_password(auth)
    assert web.Admin(store.path, auth).login('a', 'test')


@pytest.mark.parametrize('record', [None, '', '{}', 'null', '[]', '{', '{"salt":null,"hash":null}'])
def test_unconfigured_or_invalid_record_blocks_login(store, tmp_path, record):
    auth = tmp_path / 'password.json'
    if record is not None:
        auth.write_text(record)
    admin = web.Admin(store.path, auth)
    for password in ('', 'admin', 'arbitrary password'):
        assert admin.login(password, 'test') is None


def test_empty_hashed_password_cannot_authenticate(store, tmp_path):
    auth = tmp_path / 'password.json'
    salt = 'ab' * 16
    auth.write_text(json.dumps({'salt': salt, 'hash': web.password_hash('', salt)}))
    assert web.Admin(store.path, auth).login('', 'test') is None
    with pytest.raises(ValueError):
        web.password_record('')


def test_unconfigured_http_denies_login_and_management(store, tmp_path):
    auth = tmp_path / 'password.json'
    web.initialize_password(auth)
    server = ThreadingHTTPServer(('127.0.0.1', 0), web.handler(web.Admin(store.path, auth)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        for password in ('', 'admin'):
            request = urllib.request.Request(base + '/api/login',
                data=json.dumps({'password': password}).encode(), headers={'Content-Type': 'application/json'})
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request, timeout=5)
            assert error.value.code == 401
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(base + '/api/config', timeout=5)
        assert error.value.code == 401
    finally:
        server.shutdown()
        server.server_close()


def test_password_record_has_only_salted_hash():
    first = json.loads(web.password_record('unique test password'))
    second = json.loads(web.password_record('unique test password'))
    assert set(first) == {'salt', 'hash'}
    assert first != second
    assert first['hash'] == web.password_hash('unique test password', first['salt'])
    assert 'unique test password' not in json.dumps(first)
