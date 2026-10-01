"""Exercise the provisioner's actual password blocks without creating a CT."""
import getpass
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from voice_home.web import password_hash


SCRIPT = (Path(__file__).parents[1] / 'deploy/lxc/provision-lxc.sh').read_text(encoding='utf-8')
PROMPT = SCRIPT.split("<<'PASSWORD'\n", 1)[1].split('\nPASSWORD\n', 1)[0]
WRITER = SCRIPT.split('pct exec "$ctid" -- python3 -c \'\n', 1)[1].split("\n'\n", 1)[0]


def test_installer_generates_compatible_hash_without_plaintext(monkeypatch, capsys):
    answers = iter(['installer test password', 'installer test password'])
    monkeypatch.setattr(getpass, 'getpass', lambda _: next(answers))
    exec(compile(PROMPT, 'provision-password', 'exec'), {})
    output = capsys.readouterr().out
    record = json.loads(output)
    assert set(record) == {'salt', 'hash'}
    assert record['hash'] == password_hash('installer test password', record['salt'])
    assert 'installer test password' not in output


@pytest.mark.parametrize('answers', [ ['', ''], ['secret', 'different'], ['x' * 1025] ])
def test_installer_rejects_invalid_password(monkeypatch, answers, capsys):
    values = iter(answers)
    monkeypatch.setattr(getpass, 'getpass', lambda _: next(values))
    with pytest.raises(SystemExit, match='Installation abgebrochen'):
        exec(compile(PROMPT, 'provision-password', 'exec'), {})
    assert capsys.readouterr().out == ''


@pytest.mark.parametrize('error', [EOFError, KeyboardInterrupt, getpass.GetPassWarning])
def test_installer_rejects_unavailable_secure_input(monkeypatch, error, capsys):
    def unavailable(_):
        raise error()
    monkeypatch.setattr(getpass, 'getpass', unavailable)
    with pytest.raises(SystemExit, match='Installation abgebrochen'):
        exec(compile(PROMPT, 'provision-password', 'exec'), {})
    assert capsys.readouterr().out == ''


def test_installer_writes_hash_exclusively_with_private_permissions(tmp_path, monkeypatch):
    path = tmp_path / 'password.json'
    calls = []
    original_open = os.open
    def redirected_open(target, flags, mode):
        assert target == '/opt/sip-voice-home/web/password.json'
        assert mode == 0o600
        return original_open(path, flags, mode)
    monkeypatch.setattr(os, 'open', redirected_open)
    monkeypatch.setattr(os, 'fchown', lambda fd, uid, gid: calls.append((uid, gid)), raising=False)
    record = '{"salt":"test-salt","hash":"test-hash"}'
    monkeypatch.setattr(sys, 'stdin', io.StringIO(record))
    exec(compile(WRITER, 'provision-password-file', 'exec'), {})
    assert path.read_text() == record
    assert calls == [(10001, 10001)]
    with pytest.raises(FileExistsError):
        exec(compile(WRITER, 'provision-password-file', 'exec'), {})
    assert path.read_text() == record


@pytest.mark.parametrize('accepted', [False, True])
def test_provisioning_requires_password_before_creating_ct(accepted):
    bash = shutil.which('bash') if os.name != 'nt' else 'C:/Program Files/Git/bin/bash.exe'
    if not bash or not Path(bash).is_file():
        pytest.skip('Bash is required for the isolated provisioning test')
    # Stub infrastructure commands, not the script's ordering/error handling.
    commands = '''
pvesh() { printf '[]'; }
python3() {
  if [[ "$1" == -c ]]; then return 1; fi
  if [[ "$ACCEPT_PASSWORD" == yes ]]; then printf '{"salt":"salt","hash":"hash"}'; else return 1; fi
}
pct() {
  case "$1" in
    create|start) printf 'CT_OPERATION:%s\\n' "$1" ;;
    exec) if [[ "$4" == bash ]]; then cat >/dev/null; else cat; fi ;;
  esac
}
export -f pvesh python3 pct
bash "$1" 999 test-template test-storage test-bridge
'''
    script = Path(__file__).parents[1] / 'deploy/lxc/provision-lxc.sh'
    result = subprocess.run([bash, '-c', commands, 'test', script.as_posix()],
        env={**os.environ, 'ACCEPT_PASSWORD': 'yes' if accepted else 'no'}, capture_output=True, text=True)
    if accepted:
        assert result.returncode == 0, result.stderr
        assert 'CT_OPERATION:create' in result.stdout
        assert '{"salt":"salt","hash":"hash"}' in result.stdout
    else:
        assert result.returncode != 0
        assert 'CT_OPERATION:' not in result.stdout
