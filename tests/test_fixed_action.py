from dataclasses import replace
from pathlib import Path
import pytest
import yaml
from voice_home.config import Caller, load, load_text
from voice_home.dialog import Dialog

EXAMPLE = Path(__file__).parents[1] / 'config.example.yaml'


def setup(confirm=False, action_confirm=False, enabled=True):
    cfg = load(EXAMPLE)
    caller = Caller('+4915123456789', 'Anna', 'callback', 'front_door_open', confirm)
    actions = [replace(a, enabled=enabled, require_confirmation=action_confirm) for a in cfg.actions]
    dialog = Dialog(replace(cfg, actions=actions, callers=[caller]))
    s = dialog.connected(caller, 0)
    return dialog, s


def ready(dialog, s):
    assert dialog.tick(s, 1) is None
    dialog.media_ready(s, 1)
    assert dialog.tick(s, 1.5) is None
    return dialog.tick(s, 2)


def test_fixed_action_once_after_media_and_delay():
    dialog, s = setup()
    assert ready(dialog, s) == ('execute', 'front_door_open')
    assert dialog.tick(s, 3) is None
    assert dialog.recognize(s, 'Haustür öffnen', 1) is None
    for result in ('ok', 'failed', 'unconfirmed', 'disabled'):
        kind, text = dialog.result(s, 'front_door_open', result)
        assert kind == 'goodbye' and 'Möchtest du' not in text
        assert text in dialog.prompts()


@pytest.mark.parametrize('caller_confirm,action_confirm', [(True, False), (False, True), (True, True)])
def test_confirmation_cannot_switch_action(caller_confirm, action_confirm):
    dialog, s = setup(caller_confirm, action_confirm)
    assert ready(dialog, s) == ('say', dialog.actions['front_door_open'].confirmation_text)
    assert dialog.recognize(s, 'ja', 1) is None  # Question still playing.
    dialog.listened(s, 3)
    assert dialog.recognize(s, 'Garage öffnen', 1)[0] == 'say'
    assert s.pending_action == 'front_door_open'
    dialog.listened(s, 4)
    assert dialog.recognize(s, 'ja', 1) == ('execute', 'front_door_open')
    assert dialog.recognize(s, 'ja', 1) is None


@pytest.mark.parametrize('response', ['nein', 'abbrechen', 'auflegen'])
def test_decline_hangs_up_without_followup(response):
    dialog, s = setup(True)
    ready(dialog, s)
    dialog.listened(s, 3)
    assert dialog.recognize(s, response, 1)[0] == 'goodbye'
    assert s.pending_action is None


def test_disabled_and_silence_fail_closed():
    dialog, s = setup(enabled=False)
    assert ready(dialog, s)[0] == 'goodbye'
    dialog, s = setup(True)
    ready(dialog, s)
    for i in range(2):
        dialog.listened(s, 3+i*20)
        effect = dialog.tick(s, 18+i*20)
    assert effect[0] == 'goodbye' and s.pending_action is None


@pytest.mark.parametrize('fields', [{'fixed_action':'missing'}, {'require_confirmation':True},
                                  {'fixed_action':False}, {'fixed_action':'front_door_open','require_confirmation':'yes'}])
def test_invalid_caller_config(fields):
    raw = yaml.safe_load(EXAMPLE.read_text(encoding='utf-8'))
    raw['callers'] = [{'name':'Anna','number':'+4915123456789', **fields}]
    with pytest.raises(ValueError):
        load_text(yaml.safe_dump(raw), EXAMPLE)


def test_normal_dialog_still_asks_and_continues():
    dialog, _ = setup()
    caller = Caller('+4915123456789', 'Anna', 'direct')
    s = dialog.connected(caller, 0)
    assert ready(dialog, s) == ('say', 'Hallo Anna, was möchtest du tun?')
    assert dialog.result(s, 'front_door_open', 'ok')[0] == 'followup'
