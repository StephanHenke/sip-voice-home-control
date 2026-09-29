from dataclasses import replace
import json
from pathlib import Path

import pytest
import yaml

from voice_home.config import Action, load
from voice_home.dialog import Dialog
from voice_home.intents import Intents
from voice_home.speech import Speech, command_vocabulary


def result(text, confidence=1.0):
    return json.dumps({'text': text, 'result': [{'word': w, 'conf': confidence} for w in text.split()]})


def test_vocabulary_supports_new_yaml_actions_and_unknown_words():
    words = command_vocabulary([Action('light_on', ['Flurlicht', 'Licht im Flur'], ['schalte {target} ein'])])
    assert {'flurlicht', 'licht', 'im', 'flur', 'schalte', 'ein', '[unk]', 'nicht', 'nein', 'ausschalten'} <= set(words)
    assert 'schalte flurlicht ein' not in words  # Extra words must remain transcribable.


@pytest.mark.parametrize('refusal', ['Haustür nicht öffnen', 'niemals die Tür öffnen', 'nein', 'abbrechen'])
def test_unrestricted_refusal_overrides_positive_vocabulary_guess(refusal):
    selected = Speech._select(result('Haustür öffnen'), result(refusal))
    cfg = load(Path(__file__).parents[1] / 'config.example.yaml')
    cfg = replace(cfg, actions=[replace(a, enabled=True) for a in cfg.actions])
    dialog = Dialog(cfg)
    session = dialog.connected(None, now=0)
    dialog.listened(session, 0)
    assert dialog.recognize(session, *selected)[0] != 'execute'


def test_vocabulary_can_recover_command_but_not_confirm_from_unrelated_text():
    assert Speech._select(result('Haustür öffnen'), result('ist es nun')) == ('Haustür öffnen', 1.0)
    assert Speech._select(result('ja'), result('ist es nun')) == ('ja', 0.0)
    assert Speech._select(result('ja'), result('ja bitte', 0.6)) == ('ja', 0.6)
    assert Speech._select(result('ja bitte'), result('ja', 0.95)) == ('ja bitte', 0.95)
    assert Speech._select(result('Haustür öffnen'), result('ja')) == ('ja', 1.0)


def test_conflicting_known_targets_cannot_execute():
    cfg = load(Path(__file__).parents[1] / 'config.example.yaml')
    parser = Intents(cfg.actions)
    assert Speech._select(result('Haustür öffnen'), result('Garagentor öffnen'), parser)[1] == 0.0
    assert Speech._select(result('Haustür öffnen'), result('Tür öffnen'), parser)[1] == 1.0


def test_empty_unrestricted_result_blocks_vocabulary_noise_guess():
    assert Speech._select(result('Tür öffnen'), result('')) is None
    assert Speech._select(result(''), result('')) is None
    assert Speech._select(result('Tür öffnen', 0.7), None) == ('Tür öffnen', 0.7)


@pytest.mark.parametrize('setting', [True, False, 'false', 1])
def test_vocabulary_setting_is_boolean(tmp_path, setting):
    raw = yaml.safe_load((Path(__file__).parents[1] / 'config.example.yaml').read_text(encoding='utf-8'))
    raw['speech']['command_vocabulary'] = setting
    path = tmp_path / 'config.yaml'
    path.write_text(yaml.safe_dump(raw), encoding='utf-8')
    if type(setting) is bool:
        assert load(path).speech['command_vocabulary'] is setting
    else:
        with pytest.raises(ValueError, match='command_vocabulary'):
            load(path)
