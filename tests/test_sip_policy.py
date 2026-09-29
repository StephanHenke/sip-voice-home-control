"""Exercise the actual SIP policy adapter with a minimal native-API test double."""

import importlib
import sys
import threading
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
    assert call.code == 486
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
