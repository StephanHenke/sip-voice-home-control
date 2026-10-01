import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('easy_start', ROOT / 'deploy/lxc/easy-start.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def test_initial_config_is_locked_and_keeps_action_examples():
    config = yaml.safe_load(installer.initial_config((ROOT / 'config.example.yaml').read_text()))
    assert config['sip']['password'] == ''
    assert config['callers'] == []
    assert config['call_control']['initial_accepting'] is False
    assert config['actions'] and all(not a['enabled'] for a in config['actions'])


def test_unknown_template_fails_closed():
    with pytest.raises(ValueError):
        installer.initial_config('sip: {}')


def test_standalone_unpacks_without_checkout_or_network(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(installer.shutil, 'copyfile', lambda *a: pytest.fail('Checkout dependency'))
    installer.prepare_sources(tmp_path / 'unpacked')
    for name, content in installer.BUNDLED_FILES.items():
        assert (tmp_path / 'unpacked' / name).read_text(encoding='utf-8') == content


def test_bundle_matches_reviewed_sources():
    for name, content in installer.BUNDLED_FILES.items():
        assert content == (ROOT / name).read_text(encoding='utf-8'), 'Run scripts/bundle_installer.py'


@pytest.mark.parametrize('value,expected', [
    ('ghcr.io/example/project', 'ghcr.io/example/project:latest'),
    ('registry.example:5000/project', 'registry.example:5000/project:latest'),
    ('example/project:v1', 'example/project:v1'),
    ('example/project@sha256:' + 'a' * 64, 'example/project@sha256:' + 'a' * 64),
])
def test_latest_default_and_explicit_image_versions(value, expected):
    assert installer.image_reference(value) == expected


@pytest.mark.parametrize('image', ['-danger', 'image;touch /tmp/x', 'image\nSECRET'])
def test_rejects_image_argument_injection(image):
    with pytest.raises(ValueError):
        installer.registry_host(image)


@pytest.mark.parametrize('image,host', [('user/image:latest', 'docker.io'),
                                      ('ghcr.io/user/image:latest', 'ghcr.io'),
                                      ('registry.example:5000/image:v1', 'registry.example:5000')])
def test_registry_host(image, host):
    assert installer.registry_host(image) == host


def test_command_errors_never_echo_stdin(monkeypatch):
    monkeypatch.setattr(installer.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=1))
    with pytest.raises(RuntimeError) as error:
        installer.run('docker', 'login', data='private-token')
    assert 'private-token' not in str(error.value)


def test_install_private_image_and_locked_web(tmp_path, monkeypatch):
    (tmp_path / 'config.example.yaml').write_text((ROOT / 'config.example.yaml').read_text())
    calls = []
    pulls = 0
    def run(*args, **kwargs):
        nonlocal pulls
        calls.append((args, kwargs))
        if 'pull' in args:
            pulls += 1
            if pulls == 1:
                raise RuntimeError('Unauthenticated')
        if 'addr' in args:
            return json.dumps([{'addr_info': [{'family': 'inet', 'local': '192.0.2.10'}]}])
        if 'inspect' in args:
            return 'sha256:' + 'b' * 64
        return ''
    monkeypatch.setattr(installer, 'run', run)
    monkeypatch.setattr(installer, 'ask', lambda *a: 'example-user')
    monkeypatch.setattr(installer, 'secret', lambda *a: 'private-token')
    installer.install_app('200', tmp_path, 'ghcr.io/example/image:latest')
    login = next((a, kw) for a, kw in calls if 'login' in a)
    assert '--password-stdin' in login[0]
    assert login[1]['data'] == 'private-token\n'
    assert all('private-token' not in ' '.join(a) for a, _ in calls)
    environment = next(kw['data'] for a, kw in calls if a[-1] == installer.APP + '/.env')
    assert environment == 'VOICE_HOME_IMAGE=sha256:' + 'b' * 64 + '\n'
    assert any('up' in a and '--no-build' in a for a, _ in calls)
    assert not any('register' in a or 'doctor' in a for a, _ in calls)


def test_main_refuses_existing_id_before_any_mutation(tmp_path, monkeypatch):
    monkeypatch.setattr(installer.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(installer.platform, 'machine', lambda: 'x86_64')
    monkeypatch.setattr(installer.os, 'geteuid', lambda: 0, raising=False)
    original_is_dir = Path.is_dir
    monkeypatch.setattr(Path, 'is_dir', lambda self: True if self.as_posix() == '/etc/pve' else original_is_dir(self))
    monkeypatch.setattr(installer.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(installer.sys, 'argv', ['easy-start.py', '--source-dir', str(ROOT)])
    monkeypatch.setattr(installer.shutil, 'which', lambda _: '/test/tool')
    monkeypatch.setattr(installer, 'ask', lambda *a: '200')
    calls = []
    def run(*args, **kwargs):
        calls.append(args)
        if '/cluster/nextid' in args:
            return '200'
        if '/cluster/resources' in args:
            return '[{"vmid": 200}]'
        pytest.fail('Unexpected operation: ' + repr(args))
    monkeypatch.setattr(installer, 'run', run)
    with pytest.raises(ValueError, match='belegt'):
        installer.main()
    assert len(calls) == 2


def test_web_can_repair_locked_initial_config(tmp_path):
    from voice_home.web import Admin, password_record
    config = tmp_path / 'config.yaml'
    config.write_text(installer.initial_config((ROOT / 'config.example.yaml').read_text()), encoding='utf-8')
    auth = tmp_path / 'password.json'
    auth.write_text(password_record('installer-password'))
    admin = Admin(config, auth)
    assert admin.login('installer-password', 'local')
    before = admin.store.read()
    with pytest.raises(ValueError):
        admin.store.validate(before['yaml'])
    admin.child = SimpleNamespace(poll=lambda: 2)
    assert admin.can_restart()
    configured = before['yaml'].replace('password: ""', 'password: "test-sip-password"')
    admin.store.save(configured, before['revision'])
    assert 'test-sip-password' in admin.store.read()['yaml']


def test_main_complete_flow_with_simulated_proxmox(monkeypatch):
    monkeypatch.setattr(installer.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(installer.platform, 'machine', lambda: 'x86_64')
    monkeypatch.setattr(installer.os, 'geteuid', lambda: 0, raising=False)
    original_is_dir = Path.is_dir
    monkeypatch.setattr(Path, 'is_dir', lambda self: True if self.as_posix() == '/etc/pve' else original_is_dir(self))
    monkeypatch.setattr(installer.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(installer.sys, 'argv', ['easy-start.py', '--image', 'example/image'])
    monkeypatch.setattr(installer.shutil, 'which', lambda _: '/test/tool')
    answers = iter(['200', '1', '1', '1', '1', 'INSTALL'])
    monkeypatch.setattr('builtins.input', lambda _: next(answers))
    calls = []
    def run(*args, **kwargs):
        calls.append(args)
        if '/cluster/nextid' in args:
            return '200'
        if '/cluster/resources' in args:
            return '[]'
        if any(a.endswith('/storage') for a in args):
            return '[{"storage":"test-storage","active":1}]'
        if any(a.endswith('/network') for a in args):
            return '[{"iface":"vmbr0","active":1}]'
        if args[:2] == ('pveam', 'available'):
            return 'system debian-13-standard_13.1-1_amd64.tar.zst'
        return ''
    monkeypatch.setattr(installer, 'run', run)
    installed = []
    monkeypatch.setattr(installer, 'install_app', lambda ctid, directory, image: installed.append((ctid, image)))
    installer.main()
    provision = next(a for a in calls if a[0] == 'bash')
    assert provision[2:] == ('200', 'test-storage:vztmpl/debian-13-standard_13.1-1_amd64.tar.zst', 'test-storage', 'vmbr0')
    assert installed == [('200', 'example/image:latest')]
    assert calls.index(next(a for a in calls if a[:2] == ('pveam', 'download'))) < calls.index(provision)
