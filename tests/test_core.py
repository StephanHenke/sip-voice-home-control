from dataclasses import replace
from pathlib import Path
import queue
import threading
import time

import httpx
import pytest
import yaml

from voice_home.config import Action, Caller, load, number
from voice_home.dialog import Dialog
from voice_home.intents import Intents
from voice_home.limits import CallbackLimits
from voice_home.openhab import Feedback, OpenHAB, decode_event
from voice_home.routing import callback_uri, identify

EXAMPLE = Path(__file__).parents[1] / "config.example.yaml"


@pytest.fixture
def config(tmp_path):
    cfg = load(EXAMPLE)
    cfg = replace(cfg, data_dir=tmp_path, callers=[Caller("+4915123456789", "Anna")])
    return replace(cfg, actions=[replace(a, enabled=a.id == "front_door_open") for a in cfg.actions])


@pytest.mark.parametrize("text", ["Öffne Haustür", "Haustür öffnen", "schließe die Haustür auf", "Haustür aufschließen", "öffne Tür", "Tür öffnen", "schließe die Tür auf", "Tür aufschließen", "Mach die Tür auf", "Bitte öffne die Tür", "öffne bitte die Haustür", "Tür bitte öffnen", "Tür öffnen bitte", "Oeffne die Tuer!"])
def test_phrases(config, text):
    assert Intents(config.actions).parse(text) == ("action", "front_door_open")


@pytest.mark.parametrize("text", ["Tür nicht öffnen", "nicht die Haustür aufschließen", "Haustür abschließen", "ich habe Haustür öffnen gesagt", "Tür öffnen und Garage öffnen", "öffne das Fenster", "", "[unk] tür öffnen", "kein tür öffnen"])
def test_rejects_unsafe_utterances(config, text):
    assert Intents(config.actions).parse(text)[0] == "unknown"


def test_alias_collision(config):
    with pytest.raises(ValueError):
        Intents([config.actions[0], replace(config.actions[0], id="other")])


def test_lights_extend_without_code(config):
    action = Action("hall_on", ["Flurlicht", "Licht im Flur"], ["{target} einschalten", "schalte das {target} ein"])
    assert Intents([action]).parse("schalte das Licht im Flur ein") == ("action", "hall_on")


def test_number_formats_and_source(config):
    assert number("0151 23456789") == "+4915123456789"
    caller = config.callers[0]
    assert identify('"Name" <sip:015123456789@fritz.box>', "192.0.2.1:5060", "192.0.2.1", config.callers) == caller
    assert identify('"+4915123456789" <sip:anonymous@fritz.box>', "192.0.2.1:5060", "192.0.2.1", config.callers) is None
    assert identify('sip:+4915123456789@fritz.box', "192.0.2.2:5060", "192.0.2.1", config.callers) is None
    assert callback_uri(caller, "192.0.2.1", 5060) == "sip:+4915123456789@192.0.2.1:5060"


def test_config_blocks_self_callback_and_missing_feedback(tmp_path):
    raw = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    raw["sip"]["controller_number"] = "+4915123456789"
    raw["callers"] = [{"number": "015123456789", "name": "Anna"}]
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        load(path)
    raw["callers"] = []
    raw["actions"][1]["enabled"] = True
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        load(path)


def test_limits_persist_and_count_failed_attempts(tmp_path):
    path = tmp_path / "limits.sqlite"
    assert CallbackLimits(path, 60, 2).reserve("a", 1000)
    assert not CallbackLimits(path, 60, 2).reserve("a", 1050)
    assert CallbackLimits(path, 60, 2).reserve("a", 1061)
    assert not CallbackLimits(path, 60, 2).reserve("a", 1122)
    assert CallbackLimits(path, 60, 2).reserve("b", 1122)
    assert CallbackLimits(path, 60, 2).reserve("a", 5000)


@pytest.mark.parametrize("delay", [0, 1000, 2500])
def test_answer_delay_and_name(config, delay):
    cfg = replace(config, dialog={**config.dialog, "answer_delay_ms": delay})
    d = Dialog(cfg)
    s = d.connected(cfg.callers[0], 100)
    d.media_ready(s, 100)
    if delay:
        assert d.tick(s, 100 + delay / 1000 - .001) is None
    assert d.tick(s, 100 + delay / 1000)[1].startswith("Hallo Anna,")
    assert d.tick(s, 110) is None


def test_answer_pause_waits_for_audio_readiness(config):
    d = Dialog(config)
    s = d.connected(config.callers[0], 100)
    assert d.tick(s, 104) is None
    d.media_ready(s, 104)
    d.media_ready(s, 104.5)  # later media notifications cannot restart the pause
    assert d.tick(s, 104.999) is None
    assert d.tick(s, 105)[1].startswith("Hallo Anna,")


def test_multiple_actions_no_and_no_duplicates(config):
    d = Dialog(config)
    s = d.connected(config.callers[0], 0)
    d.listened(s, 1)
    assert d.recognize(s, "Tür öffnen", .99) == ("execute", "front_door_open")
    assert d.recognize(s, "Tür öffnen", .99) is None
    effect = d.result(s, "front_door_open", "ok")
    assert effect[0] == "followup"
    d.listened(s, 2, True)
    assert d.recognize(s, "ja", .99) == ("say", "Was möchtest du tun?")
    d.listened(s, 3)
    assert d.recognize(s, "Tür öffnen", .99)[0] == "followup"
    d.listened(s, 4, True)
    assert d.recognize(s, "nein", .99)[0] == "goodbye"


def test_low_confidence_silence_and_max_duration(config):
    d = Dialog(config)
    s = d.connected(config.callers[0], 0)
    d.listened(s, 1)
    assert d.recognize(s, "Tür öffnen", .2)[0] == "say"
    d.listened(s, 2)
    assert d.tick(s, 11)[0] == "goodbye"
    assert d.tick(s, 120)[0] == "hangup"


def test_event_filter():
    import json
    event = {"type": "ItemStateChangedEvent", "topic": "openhab/items/Door_State/statechanged", "payload": json.dumps({"value": "5", "oldValue": "3"})}
    assert decode_event(json.dumps(event), "Door_State") == "5"
    assert decode_event(json.dumps(event), "Other") is None
    event["type"] = "ItemCommandEvent"
    assert decode_event(json.dumps(event), "Door_State") is None


@pytest.mark.parametrize("mode, expected", [("success", "ok"), ("failure", "failed"), ("stale", "unconfirmed"), ("same", "unconfirmed"), ("no_event", "unconfirmed"), ("timeout", "unconfirmed"), ("unauthorized", "failed")])
def test_execution_requires_new_feedback(config, mode, expected):
    requests = []
    ready = []

    class Watch:
        def __init__(self, *args):
            self.events = queue.Queue()
            self.failed = threading.Event()
            ready.append(self)
        def start(self):
            self.started = True
        def close(self):
            pass

    def handler(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, text="5" if mode == "same" else "3")
        assert ready[0].started
        if mode == "timeout":
            raise httpx.ReadTimeout("simulated")
        if mode == "unauthorized":
            return httpx.Response(401)
        if mode != "no_event":
            ready[0].events.put(Feedback(time.monotonic() - 10 if mode == "stale" else time.monotonic(), "254" if mode == "failure" else "5"))
        return httpx.Response(202)

    action = replace(config.actions[0], timeout_seconds=.02)
    client = httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler))
    oh = OpenHAB({}, client=client, watch_factory=Watch)
    assert oh.execute(action, threading.Event()) == expected
    assert len([r for r in requests if r.method == "POST"]) == 1
    oh.close()


def test_disabled_action_never_connects(config):
    class Never:
        def __init__(self, *args):
            pytest.fail("disabled action connected")
    oh = OpenHAB({}, client=object(), watch_factory=Never)
    assert oh.execute(config.actions[1], threading.Event()) == "disabled"
