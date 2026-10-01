from dataclasses import replace
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from voice_home.config import Caller, load, validate_feedback
from voice_home.smarthome import NotificationBridge
from voice_home.settings import operational_settings


def test_only_confirmed_success_is_sent_with_configured_name():
    action = replace(load(Path(__file__).parents[1]/'config.example.yaml').actions[0],
                     notification_text='{name} hat die Haustür aufgeschlossen.')
    sent = []
    event = threading.Event()
    def publish(item, text):
        sent.append((item, text))
        if len(sent) == 2:
            event.set()
    bridge = NotificationBridge(SimpleNamespace(send_command=publish, close=lambda: None), 'VoiceController_Notification')
    caller = Caller('+491234567890', 'Testperson')
    for outcome in ('failed', 'unconfirmed', 'disabled'):
        bridge.result(action, caller, outcome)
    assert bridge.events.empty()
    bridge.result(replace(action, notification_text=''), caller, 'ok')
    assert bridge.events.empty()
    bridge.start()
    try:
        bridge.result(action, caller, 'ok')
        bridge.result(action, caller, 'ok')
        assert event.wait(2)
        assert sent == [('VoiceController_Notification', 'Testperson hat die Haustür aufgeschlossen.')] * 2
    finally:
        bridge.close()


def test_notification_failure_does_not_retry_or_log_personal_data(caplog):
    event = threading.Event()
    calls = []
    def publish(*args):
        calls.append(args)
        event.set()
        raise RuntimeError('private payload')
    bridge = NotificationBridge(SimpleNamespace(send_command=publish, close=lambda: None), 'Notification')
    bridge.events.put((0, 'expired private payload'))
    bridge.result(SimpleNamespace(notification_text='{name} opened'), Caller('', 'private name'), 'ok')
    bridge.start()
    try:
        assert event.wait(2)
    finally:
        bridge.close()
    assert len(calls) == 1
    assert 'private' not in caplog.text
    assert 'reason=adapter_error' in caplog.text
    assert 'reason=expired' in caplog.text


def test_notification_queue_is_bounded():
    bridge = NotificationBridge(None, 'Notification')
    for _ in range(100):
        bridge.result(SimpleNamespace(notification_text='{name} opened'), Caller('', 'Name'), 'ok')
    assert bridge.events.qsize() == 32


def test_notification_config_validation():
    with pytest.raises(ValueError):
        operational_settings({'smarthome': {'notification_item': '../invalid'}})
    with pytest.raises(ValueError):
        operational_settings({'smarthome': {'notification_item': 'Door'}, 'actions': [{'command_item': 'Door'}]})
    action = load(Path(__file__).parents[1]/'config.example.yaml').actions[0]
    for text in ('{number}', '{name.__class__}', 'line\nbreak', 5):
        with pytest.raises(ValueError):
            validate_feedback(replace(action, notification_text=text))
