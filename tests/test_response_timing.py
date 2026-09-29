from dataclasses import replace
from pathlib import Path

import pytest

from voice_home.config import Caller, load
from voice_home.dialog import Dialog


@pytest.mark.parametrize("access_mode", ["direct", "callback"])
@pytest.mark.parametrize("state", ["listening", "followup", "confirming"])
def test_noise_preserves_full_answer_window_and_pending_confirmation(access_mode, state):
    config = load(Path(__file__).parents[1] / "config.example.yaml")
    caller = Caller("+4915123456789", "Anna", access_mode)
    dialog = Dialog(config)
    session = dialog.connected(caller, 0)
    if state == "confirming":
        session.pending_action = config.actions[0].id
    dialog.listened(session, 1, followup=state == "followup")
    assert session.state == state
    assert session.deadline == 16
    for start in (1.1, 3, 8, 14):
        dialog.speech_started(session, start)
        dialog.no_speech(session)
        assert session.failures == 0
        assert session.deadline == 16
        assert dialog.tick(session, start + .8) is None
    assert dialog.tick(session, 15.99) is None
    assert dialog.tick(session, 16)[0] == "say"
    assert session.failures == 1
    if state == "confirming":
        assert session.pending_action == config.actions[0].id


def test_speech_started_late_gets_own_bounded_window():
    config = load(Path(__file__).parents[1] / "config.example.yaml")
    config = replace(config, dialog={**config.dialog, "max_utterance_seconds": 12})
    dialog = Dialog(config)
    session = dialog.connected(Caller("+4915123456789", "Anna", "direct"), 0)
    dialog.listened(session, 1)
    dialog.speech_started(session, 15.5)
    assert session.deadline == 27.5
    assert dialog.tick(session, 16.1) is None
    dialog.speech_started(session, 26)
    assert session.deadline == 27.5  # Ongoing speech/noise cannot extend indefinitely.
    assert dialog.tick(session, 27.5)[0] == "say"
    dialog.listened(session, 28)
    assert session.speech_started_at is None
    assert session.deadline == 43


def test_noise_does_not_restart_an_already_elapsed_initial_window():
    config = load(Path(__file__).parents[1] / "config.example.yaml")
    dialog = Dialog(config)
    session = dialog.connected(Caller("+4915123456789", "Anna"), 0)
    dialog.listened(session, 1)
    dialog.speech_started(session, 15.5)
    dialog.no_speech(session)
    assert dialog.tick(session, 16.5)[0] == "say"
