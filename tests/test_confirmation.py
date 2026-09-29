from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from voice_home.config import Caller, load
from voice_home.dialog import Dialog


EXAMPLE = Path(__file__).parents[1] / "config.example.yaml"
QUESTION = "Soll ich die Haustür entriegeln und die Falle ziehen?"


@pytest.fixture
def dialog():
    config = load(EXAMPLE)
    actions = [replace(a, enabled=True, require_confirmation=a.id == "front_door_open",
                       confirmation_text=QUESTION if a.id == "front_door_open" else "") for a in config.actions]
    return Dialog(replace(config, actions=actions, callers=[Caller("+4915123456789", "Anna")]))


def session(dialog):
    s = dialog.connected(dialog.config.callers[0], 0)
    dialog.listened(s, 1)
    return s


def ask(dialog, s):
    assert dialog.recognize(s, "Haustür öffnen", 1) == ("say", QUESTION)
    assert s.pending_action == "front_door_open"
    # Speech during the question cannot authorize the command.
    assert dialog.recognize(s, "ja", 1) is None
    dialog.listened(s, 2)
    assert s.state == "confirming"


@pytest.mark.parametrize("yes", ["ja", "ja bitte"])
def test_confirmation_required_again_for_each_request(dialog, yes):
    s = session(dialog)
    for _ in range(2):
        ask(dialog, s)
        assert dialog.recognize(s, yes, 1) == ("execute", "front_door_open")
        assert s.pending_action is None
        assert dialog.recognize(s, yes, 1) is None
        dialog.result(s, "front_door_open", "ok")
        dialog.listened(s, 5, followup=True)


@pytest.mark.parametrize("no", ["nein", "nein danke", "nee danke", "nö", "abbrechen"])
def test_decline_cancels_only_pending_action(dialog, no):
    s = session(dialog)
    ask(dialog, s)
    assert dialog.recognize(s, no, 1) == ("followup", "Abgebrochen. Möchtest du noch etwas?")
    assert s.pending_action is None
    dialog.listened(s, 3, followup=True)
    assert dialog.recognize(s, "ja", 1) == ("say", "Was möchtest du tun?")
    dialog.listened(s, 4)
    assert dialog.recognize(s, "Garage öffnen", 1) == ("execute", "garage_open")


@pytest.mark.parametrize("text,confidence", [("ja", .1), ("ja aber nicht öffnen", 1), ("Garage öffnen", 1), ("", 0)])
def test_uncertain_or_different_request_never_confirms(dialog, text, confidence):
    s = session(dialog)
    ask(dialog, s)
    response = dialog.recognize(s, text, confidence)
    assert response == ("say", "Bitte antworte mit Ja oder Nein. " + QUESTION)
    assert s.pending_action == "front_door_open"
    dialog.listened(s, 3)
    assert dialog.recognize(s, "ja", 1) == ("execute", "front_door_open")


def test_confirmation_silence_and_call_deadline_clear_pending(dialog):
    s = session(dialog)
    ask(dialog, s)
    assert dialog.tick(s, 17) == ("say", "Bitte antworte mit Ja oder Nein. " + QUESTION)
    dialog.listened(s, 18)
    assert dialog.tick(s, 33) == ("goodbye", "Ich konnte dich nicht verstehen. Auf Wiederhören.")
    assert s.pending_action is None
    assert dialog.recognize(s, "ja", 1) is None
    s = session(dialog)
    ask(dialog, s)
    assert dialog.tick(s, 120) == ("hangup", "")
    assert s.pending_action is None
    assert dialog.recognize(s, "ja", 1) is None


@pytest.mark.parametrize("text", ["auflegen", "bitte auflegen", "tschüss"])
def test_hangup_during_confirmation_never_executes(dialog, text):
    s = session(dialog)
    ask(dialog, s)
    assert dialog.recognize(s, text, 1) == ("goodbye", "Auf Wiederhören.")
    assert s.pending_action is None


def test_no_confirmation_for_disabled_action_and_no_pending_in_new_call(dialog):
    s = session(dialog)
    ask(dialog, s)
    new = session(dialog)
    assert dialog.recognize(new, "ja", 1)[0] == "say"
    assert new.pending_action is None
    disabled = Dialog(replace(dialog.config, actions=[replace(a, enabled=False) for a in dialog.config.actions]))
    s = session(disabled)
    assert disabled.recognize(s, "Haustür öffnen", 1) == ("followup", "Diese Aktion ist noch nicht eingerichtet. Möchtest du noch etwas?")
    assert s.pending_action is None


def test_no_confirmation_repeats_even_after_failure(dialog):
    s = session(dialog)
    assert dialog.recognize(s, "Garage öffnen", 1) == ("execute", "garage_open")
    dialog.result(s, "garage_open", "failed")
    dialog.listened(s, 3, followup=True)
    assert dialog.recognize(s, "Garage öffnen", 1) == ("execute", "garage_open")


def test_short_greeting_and_cached_confirmation_prompts(dialog):
    assert dialog.greeting(dialog.config.callers[0]) == "Hallo Anna, was möchtest du tun?"
    prompts = dialog.prompts()
    assert QUESTION in prompts
    assert "Bitte antworte mit Ja oder Nein. " + QUESTION in prompts
    assert "Abgebrochen. Möchtest du noch etwas?" in prompts
    assert not any("Verfügbar sind" in text or "bereits angefordert" in text for text in prompts)


@pytest.mark.parametrize("required,text,valid", [
    (True, QUESTION, True), (False, "", True), (True, "", False),
    (True, "   ", False), ("true", QUESTION, False), (1, QUESTION, False),
    (False, None, False), (True, 42, False),
])
def test_confirmation_yaml_validation(tmp_path, required, text, valid):
    raw = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    raw["actions"][0].update(require_confirmation=required, confirmation_text=text)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    if valid:
        assert load(path).actions[0].require_confirmation is required
    else:
        with pytest.raises(ValueError):
            load(path)
