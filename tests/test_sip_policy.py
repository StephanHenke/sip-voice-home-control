"""Exercise the actual SIP policy adapter with a minimal native-API test double."""

import importlib
import queue
import struct
import sys
import threading
import time
import types
from dataclasses import replace
from pathlib import Path

import pytest

from voice_home.config import Caller, load
from voice_home.dialog import Dialog
from voice_home.limits import CallbackLimits


@pytest.fixture
def setup(monkeypatch, tmp_path):
    pj = types.SimpleNamespace(Account=object, Call=object, AudioMediaPort=object, AudioMediaPlayer=object, PJSUA_INVALID_ID=-1, PJSIP_INV_STATE_CONFIRMED=5, PJSIP_INV_STATE_DISCONNECTED=6, PJSIP_REDIRECT_STOP=0)
    monkeypatch.setitem(sys.modules, "pjsua2", pj)
    pj.CallOpParam = lambda: types.SimpleNamespace(opt=types.SimpleNamespace())
    old = sys.modules.pop("voice_home.sip", None)
    sip = importlib.import_module("voice_home.sip")
    cfg = load(Path(__file__).parents[1] / "config.example.yaml")
    cfg = replace(cfg, callers=[Caller("+4915123456789", "Anna")], data_dir=tmp_path)
    engine = sip.Engine.__new__(sip.Engine)
    engine.config = cfg
    engine.dialog = Dialog(cfg)
    engine.probe = False
    engine.current = engine.pending = engine.task = None
    engine.calls = {}
    engine.limits = CallbackLimits(tmp_path / "budget.sqlite", 60, 5)
    captured = []

    class FakeCall:
        def __init__(self, owner, call_id):
            self.engine = owner
            self.caller = None
            self.call_id = call_id
            self.callback_trigger = False
            self.confirmed = False
            self.session = None
            self.cancelled = threading.Event()
            captured.append(self)

        def getInfo(self):
            return types.SimpleNamespace(remoteUri='"fake display name" <sip:+4915123456789@fritz.box>')

        def end(self, code=200):
            self.code = code

        def answer(self, op):
            self.answered_with = op.statusCode

        def clear_media(self):
            pass

    monkeypatch.setattr(sip, "Call", FakeCall)
    account = sip.Account(engine)
    params = types.SimpleNamespace(callId=1, rdata=types.SimpleNamespace(srcAddress=f"{cfg.sip['host']}:5060", wholeMsg="Contact: <sip:attacker@other.invalid>"))
    yield sip, pj, engine, account, params, captured
    sys.modules.pop("voice_home.sip", None)
    if old is not None:
        sys.modules["voice_home.sip"] = old


def test_callback_rejects_before_scheduling_and_never_connects_inbound(setup):
    sip, pj, e, account, p, captured = setup
    account.onIncomingCall(p)
    call = captured[0]
    assert call.code == 603
    assert e.pending is None
    assert e.current is call
    e.process_event("state", call, pj.PJSIP_INV_STATE_CONFIRMED)
    assert call.session is None  # Trigger call cannot be upgraded to a voice session.
    e.process_event("state", call, pj.PJSIP_INV_STATE_DISCONNECTED)
    assert e.current is None
    assert e.pending[1] is e.config.callers[0]
    assert e.pending[1].number == "+4915123456789"
    assert e.busy


def test_parallel_request_gets_busy_without_new_budget(setup):
    _, _, e, account, p, calls = setup
    account.onIncomingCall(p)
    original = e.current
    p.callId = 2
    account.onIncomingCall(p)
    assert calls[1].code == 486
    assert not calls[1].callback_trigger
    assert e.current is original


def test_answer_hangup_trigger_has_no_dialog_and_calls_back_after_disconnect(setup):
    _, pj, e, account, p, calls = setup
    e.config = replace(e.config, callback={**e.config.callback, "trigger_mode": "answer_hangup"})
    account.onIncomingCall(p)
    call = calls[0]
    assert call.answered_with == 200
    assert e.pending is None
    assert not hasattr(call, "code")
    e.process_event("state", call, pj.PJSIP_INV_STATE_CONFIRMED)
    assert call.code == 200  # hang up, with no voice session or audio bridge
    assert call.session is None
    assert e.pending is None
    e.process_event("state", call, pj.PJSIP_INV_STATE_DISCONNECTED)
    assert e.pending[1] is e.config.callers[0]


def test_failed_answer_never_starts_callback(setup):
    _, pj, e, account, p, calls = setup
    e.config = replace(e.config, callback={**e.config.callback, "trigger_mode": "answer_hangup"})
    account.onIncomingCall(p)
    e.process_event("state", calls[0], pj.PJSIP_INV_STATE_DISCONNECTED)
    assert e.pending is None
    assert not e.busy


@pytest.mark.parametrize("probe,source", [(True, "192.0.2.1:5060"), (False, "192.0.2.2:5060")])
def test_probe_and_wrong_peer_never_schedule(setup, probe, source):
    _, _, e, account, p, calls = setup
    e.probe = probe
    p.rdata.srcAddress = source
    account.onIncomingCall(p)
    assert calls[0].code == 403
    assert not e.busy


def test_budget_rejection_never_falls_back_to_direct(setup):
    _, _, e, account, p, calls = setup
    e.limits.reserve(e.config.callers[0].number)
    account.onIncomingCall(p)
    assert calls[0].code == 486
    assert not e.busy


@pytest.mark.parametrize("mode", ["callback", "direct"])
def test_transport_proxy_never_authorizes_caller(setup, mode):
    _, _, e, account, p, calls = setup
    e.config = replace(e.config, callers=[replace(e.config.callers[0], access_mode=mode)])
    p.rdata.srcAddress = "172.17.0.1:41000"
    account.onIncomingCall(p)
    assert not calls[0].callback_trigger
    assert calls[0].code == 403


@pytest.mark.parametrize("disconnected", [False, True])
def test_question_playback_and_beep_preserve_confirmation_until_explicit_yes(setup, disconnected):
    _, _, e, _, _, _ = setup
    action = replace(e.config.actions[0], enabled=True, require_confirmation=True,
                     confirmation_text="Soll ich die Haustür öffnen?")
    e.dialog = Dialog(replace(e.config, actions=[action]))
    e.endpoint = types.SimpleNamespace(libHandleEvents=lambda _: None)
    e.events = queue.Queue()
    preparation = []
    e.speech = types.SimpleNamespace(path=lambda text: text, beep="beep", reset=lambda: preparation.append("reset"))
    submitted = []
    e.openhab = types.SimpleNamespace(execute=lambda *_: None)
    e.pool = types.SimpleNamespace(submit=lambda *args: submitted.append(args))
    call = types.SimpleNamespace(
        session=e.dialog.connected(e.config.callers[0]), cancelled=threading.Event(),
        confirmed=True, media=object(), audio=queue.Queue(), beep_at=None,
        listening=False, followup=False,
    )
    def play(path, after):
        preparation.append(path)
        call.player = types.SimpleNamespace(after=after, stopTransmit=lambda _: None)
    call.play = play
    e.current = call
    e.dialog.listened(call.session, time.monotonic())
    e.dispatch(call, e.dialog.recognize(call.session, "Haustür öffnen", 1))
    assert not submitted
    e.process_event("playback", call, call.player)  # question -> echo guard
    assert not call.listening
    assert call.player is None
    call.beep_at = time.monotonic() - 1
    e.step()
    assert preparation[-2:] == ["reset", "beep"]
    assert not call.listening
    e.process_event("playback", call, call.player)  # beep -> immediate listening
    assert call.listening
    assert call.session.state == "confirming"
    assert not submitted
    received = []
    e.speech.feed = lambda pcm: received.append(pcm)
    from voice_home.sip import AudioSink
    sink = AudioSink.__new__(AudioSink)
    sink.call = call
    first_frame = struct.pack('<h', 500) * 320
    sink.onFrameReceived(types.SimpleNamespace(buf=first_frame))
    e.step()
    assert received == [first_frame]  # No reset/queue clearing after the ready tone.
    assert preparation.count("reset") == 1
    if disconnected:
        call.cancelled.set()
    e.dispatch(call, e.dialog.recognize(call.session, "ja", 1))
    assert len(submitted) == (0 if disconnected else 1)
    if submitted:
        assert submitted[0][1].id == action.id


def listening_engine(setup, monkeypatch):
    sip, _, e, _, _, _ = setup
    clock = [100.0]
    monkeypatch.setattr(sip.time, "monotonic", lambda: clock[0])
    e.dialog = Dialog(replace(e.config, actions=[replace(e.config.actions[0], enabled=True)]))
    e.endpoint = types.SimpleNamespace(libHandleEvents=lambda _: None)
    e.events = queue.Queue()
    resets, effects = [], []
    e.speech = types.SimpleNamespace(feed=lambda _: None, finish=lambda: None, reset=lambda: resets.append(True))
    call = types.SimpleNamespace(
        session=e.dialog.connected(e.config.callers[0]), cancelled=threading.Event(),
        confirmed=True, media=object(), audio=queue.Queue(), beep_at=None,
        listening=True, followup=False, audio_overflow=False, last_voice=None,
    )
    e.current = call
    e.dispatch = lambda _call, effect: effects.append(effect) if effect else None
    e.dialog.listened(call.session, clock[0])
    return e, call, clock, effects, resets


def test_beep_or_click_without_transcription_does_not_prompt_immediately(setup, monkeypatch):
    e, call, clock, effects, resets = listening_engine(setup, monkeypatch)
    for at in (100.2, 103, 108, 114):
        clock[0] = at
        call.audio.put(struct.pack('<h', 500) * 320)
        e.step()
        clock[0] = at + .8
        e.step()
        assert not effects
        assert call.session.failures == 0
        assert call.session.deadline == 115
        assert call.last_voice is None
    assert len(resets) == 4
    clock[0] = 115
    e.step()
    assert len(effects) == 1
    assert effects[0][0] == "say"


def test_adapter_accepts_complete_speech_after_original_answer_deadline(setup, monkeypatch):
    e, call, clock, effects, _ = listening_engine(setup, monkeypatch)
    clock[0] = 114.5
    call.audio.put(struct.pack('<h', 500) * 320)
    e.step()
    assert call.session.deadline == 129.5
    e.speech.finish = lambda: ("Haustür öffnen", 1)
    clock[0] = 115.3
    e.step()
    assert effects == [("execute", "front_door_open")]


def test_adapter_does_not_execute_a_prefix_at_maximum_utterance_duration(setup, monkeypatch):
    e, call, clock, effects, _ = listening_engine(setup, monkeypatch)
    clock[0] = 101
    call.audio.put(struct.pack('<h', 500) * 320)
    e.step()
    e.speech.finish = lambda: ("Haustür öffnen", 1)
    clock[0] = 116
    e.step()
    assert len(effects) == 1 and effects[0][0] == "say"
