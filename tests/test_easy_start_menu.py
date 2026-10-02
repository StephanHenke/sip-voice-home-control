import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('menu', ROOT / 'scripts/easy_start_menu.py')
menu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(menu)
IDLE = {'fresh': True, 'busy': False, 'call_active': False, 'accepting': False}


@pytest.mark.parametrize('field,value', [('fresh', False), ('busy', True), ('call_active', True), ('accepting', True)])
def test_guard_rejects_unsafe_state(field, value):
    state = {**IDLE, field: value}
    with pytest.raises(ValueError):
        menu.require_idle(lambda *a, **k: json.dumps(state))


def test_update_cancel_does_not_deploy():
    calls = []
    def run(*a, **k):
        calls.append(a)
        return json.dumps(IDLE) if a[-1] == 'status' else ''
    api = SimpleNamespace(run=run, ask=lambda *a: 'no', image_reference=lambda x: x)
    menu.update(api, ['pct', 'exec', '200', '--'], 'example/image:latest')
    assert not any('update' in c for c in calls)


def test_update_uses_selected_host_target():
    calls = []
    def run(*a, **k):
        calls.append(a)
        return json.dumps(IDLE) if a[-1] == 'status' else ''
    api = SimpleNamespace(run=run, ask=lambda *a: 'UPDATE', image_reference=lambda x: x)
    menu.update(api, ['pct', 'exec', '200', '--'], 'example/image:latest')
    assert calls[-1] == ('pct', 'exec', '200', '--', str(menu.APP / 'voice-home-deploy.sh'), 'update', 'example/image:latest')


def test_targets_exclude_stopped_remote_and_foreign(monkeypatch):
    monkeypatch.setattr(menu.socket, 'gethostname', lambda: 'node.example')
    records = [dict(type='lxc', node='node', status='running', vmid=200),
               dict(type='lxc', node='other', status='running', vmid=201),
               dict(type='lxc', node='node', status='stopped', vmid=202),
               dict(type='qemu', node='node', status='running', vmid=203)]
    calls = []
    def run(*a, **k):
        calls.append(a)
        return json.dumps(records) if a[0] == 'pvesh' else ''
    assert menu.targets(SimpleNamespace(run=run)) == ['200']
    assert len(calls) == 2


@pytest.mark.parametrize('place', ['host', 'lxc'])
def test_quit_has_no_operations(monkeypatch, place):
    monkeypatch.setattr(menu, 'environment', lambda: place)
    api = SimpleNamespace(ask=lambda *a: '0', run=lambda *a, **k: pytest.fail('Unexpected operation'))
    menu.dispatch(SimpleNamespace(update=None, status=None, image=None), api)


@pytest.mark.parametrize('failure', [False, True])
def test_reset_preserves_backup_password_and_restores_on_failure(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(menu, 'APP', tmp_path)
    (tmp_path / 'compose.web.yaml').write_text('web')
    (tmp_path / 'config').mkdir()
    config = tmp_path / 'config/config.yaml'
    config.write_bytes(b'original secret config')
    (tmp_path / 'web').mkdir()
    password = tmp_path / 'web/password.json'
    password.write_bytes(b'unchanged hash')
    import builtins
    real_open = builtins.open
    def redirected(path, *a, **k):
        if str(path) == '/run/lock/voice-home-deploy.lock':
            path = tmp_path / 'lock'
        return real_open(path, *a, **k)
    monkeypatch.setattr(builtins, 'open', redirected)
    monkeypatch.setitem(sys.modules, 'fcntl', SimpleNamespace(LOCK_EX=1, LOCK_NB=2, flock=lambda *a: None))
    monkeypatch.setattr(os, 'fchown', lambda *a: None, raising=False)
    monkeypatch.setattr(os, 'fchmod', lambda *a: None, raising=False)
    calls = []
    def run(*a, **k):
        calls.append(a)
        return json.dumps(IDLE)
    def ready(_):
        if failure:
            raise RuntimeError('listener failed')
    monkeypatch.setattr(menu, 'check_web', ready)
    api = SimpleNamespace(run=run, ask=lambda *a: 'RESET', initial_config=lambda x: 'locked initial config', example='example')
    if failure:
        with pytest.raises(RuntimeError, match='wiederhergestellt'):
            menu.reset_config(api)
    else:
        menu.reset_config(api)
    assert config.read_bytes() == (b'original secret config' if failure else b'locked initial config')
    assert password.read_bytes() == b'unchanged hash'
    assert next((tmp_path / 'backups').iterdir()).read_bytes() == b'original secret config'
    assert any('stop' in call for call in calls)


def test_piped_shell_help_and_truncated_download():
    shell = 'C:/Program Files/Git/bin/sh.exe' if os.name == 'nt' else '/bin/sh'
    if not Path(shell).exists():
        pytest.skip('POSIX shell unavailable')
    script = (ROOT / 'deploy/lxc/easy-start.sh').read_text(encoding='utf-8')
    result = subprocess.run([shell, '-s', '--', '--help'], input=script, text=True, capture_output=True)
    assert result.returncode == 0 and 'menu' in result.stdout
    # The main function must be fully received before any provisioning executes.
    partial = script.split("cat >\"$installer\"", 1)[0]
    result = subprocess.run([shell], input=partial, text=True, capture_output=True)
    assert result.returncode != 0
    assert not result.stdout
