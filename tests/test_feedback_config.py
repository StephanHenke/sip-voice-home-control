"""YAML-defined state meanings and measured motion in either direction."""

from dataclasses import replace
from pathlib import Path
import queue
import threading
import time

import httpx
import pytest
import yaml

from voice_home.config import load
from voice_home.openhab import Feedback, OpenHAB


EXAMPLE = Path(__file__).parents[1] / "config.example.yaml"


def configured_action(tmp_path, **settings):
    raw = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    raw["actions"][1].update(
        enabled=True, command_item="Garage_Command", feedback_item="Garage_Actual",
        command="UP", feedback_mode="state", success_values=[], failure_values=[],
        state_values={"closed": ["1"], "opening": ["3"], "open": ["2", "OPEN"], "error": ["9"]},
        success_states=["opening", "open"], failure_states=["error"],
    )
    raw["actions"][1].update(settings)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return load(path).actions[1]


def execute(action, baseline, event, *, auto="false", stale=False, item_type="Rollershutter"):
    watchers, requests = [], []

    class Watch:
        def __init__(self, client, item):
            assert item == action.feedback_item
            self.events = queue.Queue()
            self.failed = threading.Event()
            watchers.append(self)

        def start(self):
            self.started = True

        def close(self):
            pass

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/state"):
            assert request.headers["Accept"] == "text/plain"
            return httpx.Response(200, text=baseline)
        if request.method == "GET":
            return httpx.Response(200, json={"type": item_type, "metadata": {"autoupdate": {"value": auto}}})
        assert watchers[0].started
        assert request.url.path == f"/rest/items/{action.command_item}"
        assert request.content.decode() == action.command
        if event is not None:
            watchers[0].events.put(Feedback(time.monotonic() - (10 if stale else 0), event))
        return httpx.Response(202)

    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler)) as client:
        oh = OpenHAB({}, client=client, watch_factory=Watch)
        # Allow normal Windows scheduler jitter while the Docker build runs.
        result = oh.execute(replace(action, timeout_seconds=.2), threading.Event())
    return result, sum(r.method == "POST" for r in requests)


@pytest.mark.parametrize("baseline,event,expected", [
    ("1", "3", "ok"), ("1", "2", "ok"), ("1", "9", "failed"),
    ("2", "2", "unconfirmed"), ("OPEN", "2", "unconfirmed"),
    ("1", "1", "unconfirmed"), ("1", "unknown", "unconfirmed"),
    ("1", "UNDEF", "unconfirmed"), ("1", None, "unconfirmed"),
])
def test_mapped_device_feedback(tmp_path, baseline, event, expected):
    action = configured_action(tmp_path)
    assert execute(action, baseline, event) == (expected, 1)


def test_inverted_contact_mapping_and_final_open_only(tmp_path):
    action = configured_action(
        tmp_path, state_values={"closed": ["OPEN"], "open": ["CLOSED"]},
        success_states=["open"], failure_states=[],
    )
    assert execute(action, "OPEN", "CLOSED") == ("ok", 1)
    assert execute(action, "CLOSED", "OPEN") == ("unconfirmed", 1)
    action = configured_action(tmp_path, success_states=["open"])
    assert execute(action, "1", "3") == ("unconfirmed", 1)
    assert execute(action, "1", "2", stale=True) == ("unconfirmed", 1)


@pytest.mark.parametrize("auto,expected", [("false", "ok"), ("true", "unconfirmed"), (None, "unconfirmed")])
def test_one_item_state_mapping_requires_autoupdate_disabled(tmp_path, auto, expected):
    action = configured_action(tmp_path, feedback_item="Garage_Command")
    assert execute(action, "1", "3", auto=auto, item_type="Number") == (expected, 1)


@pytest.mark.parametrize("event,expected", [("3", "unconfirmed"), ("5", "ok"), ("254", "failed")])
def test_door_unlatch_requires_latch_feedback(tmp_path, event, expected):
    action = configured_action(
        tmp_path, command="3", state_values={"locked": ["1"], "unlocked": ["3"], "unlatched": ["5"], "blocked": ["254"]},
        success_states=["unlatched"], failure_states=["blocked"],
    )
    assert execute(action, "1", event) == (expected, 1)


@pytest.mark.parametrize("settings", [
    {"state_values": {"open": ["2"], "closed": ["2"]}},
    {"state_values": {"open": [2]}},
    {"state_values": {"open": "2"}},
    {"state_values": {"open": []}},
    {"state_values": []},
    {"success_states": ["missing"]},
    {"failure_states": ["open"]},
    {"success_values": ["2"]},
    {"state_values": {"open": ["UNDEF"]}, "success_states": ["open"], "failure_states": []},
    {"success_states": "open"},
    {"open_position": 100, "closed_position": 0},
])
def test_ambiguous_or_invalid_state_mapping_rejected(tmp_path, settings):
    with pytest.raises(ValueError):
        configured_action(tmp_path, **settings)


@pytest.mark.parametrize("opened,closed,baseline,event,expected", [
    (0, 100, "100", "50", "ok"), (100, 0, "0", "50", "ok"),
    (100, 0, "40", "30", "unconfirmed"), (100, 0, "100", "100", "unconfirmed"),
    (100, 0, "0", "101", "unconfirmed"), (100, 0, "0", "NaN", "unconfirmed"),
    (100, 0, "0", "UNDEF", "unconfirmed"),
    (80, 20, "20", "50", "ok"), (80, 20, "20", "90", "unconfirmed"),
])
def test_configured_position_direction(tmp_path, opened, closed, baseline, event, expected):
    action = configured_action(
        tmp_path, feedback_mode="rollershutter_opening", state_values={},
        success_states=[], failure_states=[], open_position=opened, closed_position=closed,
    )
    assert execute(action, baseline, event) == (expected, 1)


def test_inversion_does_not_bypass_autoupdate_or_invalid_baseline(tmp_path):
    action = configured_action(
        tmp_path, feedback_mode="rollershutter_opening", state_values={},
        success_states=[], failure_states=[], open_position=100, closed_position=0,
        feedback_item="Garage_Command", command="DOWN",
    )
    assert execute(action, "0", "100", auto="true") == ("unconfirmed", 1)
    assert execute(action, "0", "50", stale=True) == ("unconfirmed", 1)
    assert execute(action, "UNDEF", "50") == ("unconfirmed", 0)
    assert execute(action, "101", "50") == ("unconfirmed", 0)


@pytest.mark.parametrize("settings", [
    {"open_position": 100, "closed_position": 100}, {"open_position": -1},
    {"closed_position": 101}, {"open_position": float("nan")},
    {"open_position": True}, {"open_position": "100"}, {"command": "STOP"},
    {"command": "nan"}, {"command": "101"}, {"success_values": ["0"]},
])
def test_invalid_position_config_rejected(tmp_path, settings):
    with pytest.raises(ValueError):
        configured_action(
            tmp_path, **dict(feedback_mode="rollershutter_opening", state_values={},
                            success_states=[], failure_states=[], **settings),
        )
