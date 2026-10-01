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
