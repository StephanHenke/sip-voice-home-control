from concurrent.futures import ThreadPoolExecutor
import json
import logging
import queue
import socket
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import yaml

from voice_home.config import load, credential
from voice_home.limits import CallbackLimits
from voice_home.logging_config import configure, RemoteSink
from voice_home.openhab import OpenHAB, decode_command
from voice_home.runtime import read_status, write_status, operating_status
from voice_home.settings import operational_settings
from voice_home.smarthome import ControlBridge


def config_file(tmp_path, **changes):
    raw = yaml.safe_load(Path('config.example.yaml').read_text(encoding='utf-8'))
    raw.update(changes)
    path = tmp_path / 'config.yaml'
    path.write_text(yaml.safe_dump(raw), encoding='utf-8')
    return path


def test_inline_and_relative_credentials(tmp_path):
    path = config_file(tmp_path)
    raw = yaml.safe_load(path.read_text(encoding='utf-8'))
    raw['sip'].pop('password_file', None)
    raw['sip']['password'] = 'private-value'
    raw['openhab'] = {'token_file': 'token.txt'}
    (tmp_path / 'token.txt').write_text('file-value\n', encoding='utf-8')
    path.write_text(yaml.safe_dump(raw), encoding='utf-8')
    cfg = load(path)
    assert credential(cfg.sip, 'password') == 'private-value'
    assert credential(cfg.openhab, 'token') == 'file-value'
    raw['sip']['password_file'] = 'another.txt'
    path.write_text(yaml.safe_dump(raw), encoding='utf-8')
    with pytest.raises(ValueError) as error:
        load(path)
    assert 'private-value' not in str(error.value)
    assert 'gleichzeitig' in str(error.value)


@pytest.mark.parametrize('hourly,cooldown', [(0, 0), (0, 60), (2, 0), (2, 60)])
def test_independent_limits_and_restart(hourly, cooldown):
    limit = CallbackLimits(cooldown, hourly)
    assert limit.reserve('a', 10)
    assert limit.reserve('a', 10) is (cooldown == 0)
    assert limit.reserve('b', 10)
    assert CallbackLimits(cooldown, hourly).reserve('a', 10)
    assert limit.reserve('a', 4000)
    if not hourly and not cooldown:
        assert limit.attempts == {}


def test_limit_atomic():
    limit = CallbackLimits(0, 1)
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(lambda _: limit.reserve('a', 10), range(40))) == 1


@pytest.mark.parametrize('value', [-1, 0.5, True])
def test_invalid_hourly_limits(tmp_path, value):
    with pytest.raises(ValueError):
        load(config_file(tmp_path, callback={'max_attempts_per_number_per_hour': value}))


def test_zero_limits_valid(tmp_path):
    cfg = load(config_file(tmp_path, callback={'max_attempts_per_number_per_hour': 0, 'cooldown_seconds': 0}))
    assert cfg.callback['cooldown_seconds'] == 0


def test_status_fresh_stale_missing(tmp_path):
    path = tmp_path / 'ram' / 'health.json'
    assert read_status(path) == {'fresh': False, 'status': 'UNKNOWN'}
    write_status({'at': time.time(), 'status': 'BUSY', 'call_active': True}, path)
    assert read_status(path)['call_active'] is True
    write_status({'at': time.time() - 16, 'status': 'BUSY', 'call_active': True}, path)
    assert read_status(path)['call_active'] is None
    assert not read_status(path)['fresh']


def test_status_priorities():
    args = dict(stopping=True, starting=True, error=True, busy=True, accepting=False)
    for field, expected in [('stopping', 'OFFLINE'), ('starting', 'STARTING'), ('error', 'ERROR'), ('busy', 'BUSY')]:
        assert operating_status(**args) == expected
        args[field] = False
    assert operating_status(**args) == 'DISABLED'
    args['accepting'] = True
    assert operating_status(**args) == 'READY'


def test_command_decoder_ignores_updates_and_other_items():
    event = {'type': 'ItemCommandEvent', 'topic': 'openhab/items/Accept/command', 'payload': json.dumps({'value': 'OFF'})}
    assert decode_command(json.dumps(event), 'Accept') == 'OFF'
    assert decode_command(json.dumps(event), 'Other') is None
    event['type'] = 'ItemStateEvent'
    assert decode_command(json.dumps(event), 'Accept') is None


def test_adapter_read_write_separation():
    requests = []
    def handle(request):
        requests.append(request)
        if request.url.path.endswith('/state'):
            return httpx.Response(200, text='ON')
        return httpx.Response(200, json={'type': 'Switch'})
    client = httpx.Client(base_url='http://local', transport=httpx.MockTransport(handle))
    adapter = OpenHAB({}, client=client)
    assert adapter.read_item('A')['type'] == 'Switch'
    assert adapter.read_state('A') == 'ON'
    adapter.send_command('A', 'OFF')
    adapter.publish_state('A', 'ON')
    assert [r.method for r in requests] == ['GET', 'GET', 'POST', 'PUT']
    adapter.close()


def control_config():
    return {'enabled': True, 'switch_item': 'Accept', 'status_item': 'Status', 'call_active_item': 'Active', 'heartbeat_item': 'Heartbeat', 'heartbeat_interval_seconds': 0.05}


def wait_until(predicate, timeout=2):
    end = time.monotonic() + timeout
    while not predicate() and time.monotonic() < end:
        time.sleep(0.01)
    assert predicate()


def test_bridge_commands_publication_and_reconnect():
    writes, watches = [], []
    def watch(item):
        watcher = SimpleNamespace(events=queue.Queue(), failed=threading.Event(), start=lambda: None, close=lambda: None)
        watches.append(watcher)
        return watcher
    adapter = SimpleNamespace(watch_commands=watch, publish_state=lambda item, value: writes.append((item, value)), close=lambda: None)
    bridge = ControlBridge(adapter, control_config())
    bridge.update({'accepting': True, 'call_active': False, 'status': 'READY'})
    bridge.start()
    try:
        wait_until(lambda: ('Accept', 'ON') in writes)
        watches[0].events.put(SimpleNamespace(value='OFF'))
        assert bridge.commands.get(timeout=1) is False
        bridge.update({'accepting': False, 'call_active': True, 'status': 'BUSY'})
        wait_until(lambda: ('Accept', 'OFF') in writes and ('Active', 'ON') in writes)
        watches[0].failed.set()
        wait_until(lambda: len(watches) == 2)
        wait_until(lambda: bridge.connected)
        assert bridge.commands.empty()  # no replay/state read on reconnect
    finally:
        bridge.close()


@pytest.fixture
def restore_logging():
    root = logging.getLogger()
    handlers, level, disabled = root.handlers[:], root.level, logging.root.manager.disable
    root.handlers = []
    yield
    for handler in root.handlers[:]:
        handler.close()
    root.handlers, root.level = handlers, level
    logging.disable(disabled)


def settings(**changes):
    return operational_settings({'logging': changes})[2]


@pytest.mark.parametrize('level', ['ERROR', 'WARNING', 'INFO', 'DEBUG'])
def test_log_filter_rotation_and_secret_redaction(tmp_path, restore_logging, level):
    path = tmp_path / 'voice.log'
    handler = configure(settings(level=level, target='file', path=str(path), max_bytes=200, backup_count=2), ['sensitive'])
    logger = logging.getLogger('voice_home.test')
    for _ in range(20):
        logger.error('event sensitive')
    logging.getLogger('httpx').warning('Authorization: sensitive')
    handler.flush()
    files = list(tmp_path.glob('voice.log*'))
    assert len(files) <= 3
    text = ''.join(p.read_text(encoding='utf-8') for p in files)
    assert 'sensitive' not in text
    assert 'Authorization' not in text


@pytest.mark.parametrize('changes', [{'target': 'none'}, {'level': 'OFF'}])
def test_logging_off(changes, restore_logging, capsys):
    configure(settings(**changes))
    logging.getLogger('voice_home.test').critical('must not appear')
    assert 'must not appear' not in capsys.readouterr().err


def test_remote_syslog_udp(restore_logging):
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(('127.0.0.1', 0))
    server.settimeout(2)
    handler = configure(settings(target='syslog', host='127.0.0.1', port=server.getsockname()[1]))
    try:
        logging.getLogger('voice_home.test').info('hello')
        payload = server.recv(4096)
        assert payload.startswith(b'<134>') and b'hello' in payload
    finally:
        handler.close()
        server.close()


def test_syslog_failure_counts_without_file():
    sink = RemoteSink(settings(target='syslog', host='127.0.0.1', transport='tcp', port=1, queue_size=1))
    try:
        sink.emit(logging.LogRecord('voice_home', logging.INFO, '', 0, 'event', (), None))
        wait_until(lambda: sink.dropped > 0)
    finally:
        sink.close()


def test_stalled_controller_stops_heartbeat():
    writes = []
    watcher = SimpleNamespace(events=queue.Queue(), failed=threading.Event(), start=lambda: None, close=lambda: None)
    bridge = ControlBridge(SimpleNamespace(watch_commands=lambda _: watcher, publish_state=lambda *args: writes.append(args), close=lambda: None), control_config())
    bridge.update({'accepting': True, 'call_active': False, 'status': 'READY'})
    bridge.updated_at = time.monotonic() - 16
    bridge.start()
    try:
        wait_until(lambda: bridge.connected)
        time.sleep(0.15)
        assert writes == []
    finally:
        bridge.close()


@pytest.mark.parametrize('changes', [
    {'enabled': 'true'}, {'initial_accepting': 1}, {'enabled': True},
    {'enabled': True, 'switch_item': 'Same', 'status_item': 'Same', 'call_active_item': 'A', 'heartbeat_item': 'B'},
    {'heartbeat_interval_seconds': 0},
])
def test_invalid_control_settings(changes):
    with pytest.raises(ValueError):
        operational_settings({'call_control': changes})


def test_cli_status_and_health_disabled(tmp_path, monkeypatch, capsys, restore_logging):
    from voice_home import cli, runtime
    path = tmp_path / 'status.json'
    monkeypatch.setattr(runtime, 'STATUS_PATH', path)
    cfg = config_file(tmp_path)
    write_status({'at': time.time(), 'registered': True, 'speech_ready': True, 'status': 'DISABLED', 'accepting': False}, path)
    monkeypatch.setattr('sys.argv', ['voice-home', '--config', str(cfg), 'status'])
    with pytest.raises(SystemExit) as result:
        cli.main()
    assert result.value.code == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'DISABLED'
    monkeypatch.setattr('sys.argv', ['voice-home', '--config', str(cfg), 'health'])
    with pytest.raises(SystemExit) as result:
        cli.main()
    assert result.value.code == 0


def test_legacy_cleanup_is_narrow(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location('cleanup', 'scripts/remove_legacy_runtime.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ('callbacks.sqlite', 'callbacks.sqlite-wal', 'health.json', 'keep.txt'):
        (tmp_path / name).write_text('test', encoding='utf-8')
    (tmp_path / 'prompts').mkdir()
    module.remove_legacy(tmp_path)
    assert {p.name for p in tmp_path.iterdir()} == {'keep.txt', 'prompts'}
