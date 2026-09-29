"""PJSUA2 adapter. SIP objects live on one event-loop thread."""

import audioop
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import queue
import signal
import threading
import time

import pjsua2 as pj

from .config import Config, secret
from .dialog import Dialog
from .limits import CallbackLimits
from .openhab import OpenHAB
from .routing import callback_uri, identify
from .speech import Speech

log = logging.getLogger(__name__)


class AudioSink(pj.AudioMediaPort):
    def __init__(self, call):
        super().__init__()
        self.call = call
        fmt = pj.MediaFormatAudio()
        fmt.type = pj.PJMEDIA_TYPE_AUDIO
        fmt.clockRate = 16000
        fmt.channelCount = 1
        fmt.bitsPerSample = 16
        fmt.frameTimeUsec = 20000
        self.createPort("voice-input", fmt)

    def onFrameReceived(self, frame):
        if self.call.listening:
            try:
                self.call.audio.put_nowait(bytes(frame.buf))
            except queue.Full:
                self.call.audio_overflow = True


class Player(pj.AudioMediaPlayer):
    def __init__(self, call, path, after):
        super().__init__()
        self.call, self.after = call, after
        self.createPlayer(str(path), pj.PJMEDIA_FILE_NO_LOOP)

    def onEof2(self):
        self.call.engine.events.put(("playback", self.call, self))


class Call(pj.Call):
    def __init__(self, engine, call_id=pj.PJSUA_INVALID_ID):
        super().__init__(engine.account, call_id)
        self.engine = engine
        self.caller = None
        self.session = None
        self.confirmed = False
        self.disconnected = False
        self.callback_trigger = False
        self.callback_pending = False
        self.created_at = time.monotonic()
        self.cancelled = threading.Event()
        self.media = None
        self.sink = None
        self.player = None
        self.listening = False
        self.beep_at = None
        self.followup = False
        self.last_voice = None
        self.audio = queue.Queue(maxsize=100)
        self.audio_overflow = False

    def onCallState(self, prm):
        info = self.getInfo()
        log.info("sip_call state=%s status=%s", info.stateText, info.lastStatusCode)
        self.engine.events.put(("state", self, info.state))
        if info.state == pj.PJSIP_INV_STATE_DISCONNECTED:
            self.cancelled.set()
            self.listening = False

    def onCallMediaState(self, prm):
        self.engine.events.put(("media", self, None))

    def onCallRedirected(self, prm):
        return pj.PJSIP_REDIRECT_STOP

    def onCallTransferRequest(self, prm):
        prm.statusCode = 403

    def onCallReplaceRequest(self, prm):
        prm.statusCode = 403

    def end(self, code=200):
        self.cancelled.set()
        self.listening = False
        if not self.disconnected:
            op = pj.CallOpParam()
            op.statusCode = code
            try:
                self.hangup(op)
            except pj.Error:
                pass

    def attach_media(self):
        info = self.getInfo()
        for media in info.media:
            if media.type == pj.PJMEDIA_TYPE_AUDIO and media.status == pj.PJSUA_CALL_MEDIA_ACTIVE:
                current = self.getAudioMedia(media.index)
                if self.media is not None and current.getPortId() == self.media.getPortId():
                    return
                self.clear_media()
                self.media = current
                self.sink = AudioSink(self)
                self.media.startTransmit(self.sink)
                return

    def clear_media(self):
        self.listening = False
        if self.player and self.media:
            try:
                self.player.stopTransmit(self.media)
            except pj.Error:
                pass
        self.player = None
        if self.media and self.sink:
            try:
                self.media.stopTransmit(self.sink)
            except pj.Error:
                pass
        self.sink = None
        self.media = None

    def play(self, path, after):
        self.listening = False
        self.beep_at = None
        if not self.confirmed or self.media is None or self.cancelled.is_set():
            self.end()
            return
        self.player = Player(self, path, after)
        self.player.startTransmit(self.media)


class Account(pj.Account):
    def __init__(self, engine):
        super().__init__()
        self.engine = engine

    def onRegState(self, prm):
        info = self.getInfo()
        self.engine.registered = info.regIsActive and 200 <= prm.code < 300
        self.engine.registration_code = prm.code
        log.info("sip_registration code=%s active=%s", prm.code, self.engine.registered)

    def onIncomingCall(self, prm):
        call = Call(self.engine, prm.callId)
        self.engine.calls[prm.callId] = call
        caller = identify(call.getInfo().remoteUri, prm.rdata.srcAddress, self.engine.config.sip["host"], self.engine.config.callers, self.engine.config.region)
        log.info("sip_incoming peer=%s caller_allowed=%s", prm.rdata.srcAddress, caller is not None)
        if self.engine.probe or caller is None:
            log.info("sip_rejected reason=%s", "registration_probe" if self.engine.probe else "untrusted_peer_or_number")
            call.end(403)
            return
        if self.engine.busy:
            log.info("sip_rejected reason=busy")
            call.end(486)
            return
        call.caller = caller
        if caller.access_mode == "callback":
            if not self.engine.limits.reserve(caller.number):
                log.info("callback_rate_limited")
                call.end(486)
                return
            self.engine.current = call  # reserve capacity before rejection
            call.callback_trigger = True
            log.info("callback_trigger_accepted")
            if self.engine.config.callback["trigger_mode"] == "answer_hangup":
                op = pj.CallOpParam()
                op.statusCode = 200
                op.opt.audioCount = 1
                op.opt.videoCount = 0
                call.answer(op)
            else:
                call.end(603)  # Global decline; 486 can leave other forked phones ringing.
        else:
            self.engine.current = call
            op = pj.CallOpParam()
            op.statusCode = 200
            op.opt.audioCount = 1
            op.opt.videoCount = 0
            call.answer(op)


class Engine:
    def __init__(self, config: Config, probe: bool = False):
        self.config, self.probe = config, probe
        self.dialog = Dialog(config)
        config.data_dir.mkdir(parents=True, exist_ok=True)
        self.events = queue.Queue()
        self.calls = {}
        self.current = None
        self.pending = None
        self.task = None
        self.registered = False
        self.registration_code = 0
        self.stopping = False
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.limits = CallbackLimits(config.data_dir / "callbacks.sqlite", config.callback["cooldown_seconds"], config.callback["max_attempts_per_number_per_hour"])
        self.speech = None if probe else Speech(config.speech, config.data_dir / "prompts", self.dialog.prompts(), config.actions)
        self.openhab = None if probe else OpenHAB(config.openhab)
        self.endpoint = pj.Endpoint()
        self.endpoint.libCreate()
        cfg = pj.EpConfig()
        cfg.uaConfig.threadCnt = 0
        cfg.uaConfig.mainThreadOnly = True
        cfg.uaConfig.maxCalls = 4  # one authorized session plus calls being rejected
        cfg.uaConfig.userAgent = "sip-voice-home-control/0.1"
        cfg.logConfig.level = 1
        cfg.logConfig.consoleLevel = 1
        cfg.logConfig.msgLogging = False
        cfg.medConfig.clockRate = 16000
        cfg.medConfig.sndClockRate = 16000
        cfg.medConfig.channelCount = 1
        cfg.medConfig.audioFramePtime = 20
        self.endpoint.libInit(cfg)
        transport = pj.TransportConfig()
        transport.port = config.sip["local_port"]
        transport.boundAddress = "0.0.0.0"
        transport.publicAddress = config.sip.get("public_address", "")
        transport_type = pj.PJSIP_TRANSPORT_TCP if config.sip["transport"] == "tcp" else pj.PJSIP_TRANSPORT_UDP
        tid = self.endpoint.transportCreate(transport_type, transport)
        self.endpoint.libStart()
        self.endpoint.audDevManager().setNullDev()
        for codec in self.endpoint.codecEnum2():
            priority = 240 if codec.codecId.startswith("G722/") else 230 if codec.codecId.startswith("PCMA/") else 220 if codec.codecId.startswith("PCMU/") else 0
            self.endpoint.codecSetPriority(codec.codecId, priority)
        self.account = Account(self)
        ac = pj.AccountConfig()
        host = config.sip["host"]
        transport_suffix = ";transport=tcp" if config.sip["transport"] == "tcp" else ""
        registrar = f"sip:{host}:{config.sip['port']}{transport_suffix}"
        ac.idUri = f"sip:{config.sip['username']}@{host}"
        ac.regConfig.registrarUri = registrar
        ac.regConfig.retryIntervalSec = 15
        ac.regConfig.firstRetryIntervalSec = 3
        ac.regConfig.timeoutSec = 300
        ac.sipConfig.transportId = tid
        ac.sipConfig.authCreds.append(pj.AuthCredInfo("digest", "*", config.sip["username"], 0, secret(config.sip["password_file"])))
        ac.mediaConfig.transportConfig.port = config.sip["rtp_port"]
        ac.mediaConfig.transportConfig.portRange = 10
        ac.mediaConfig.transportConfig.publicAddress = config.sip.get("public_address", "")
        self.account.create(ac)

    @property
    def busy(self):
        return self.current is not None or self.pending is not None or (self.task is not None and not self.task[0].done())

    def dispatch(self, call, effect):
        if not effect or call.cancelled.is_set():
            return
        kind, value = effect
        call.listening = False
        if kind == "hangup":
            call.end()
        elif kind == "execute":
            future = self.pool.submit(self.openhab.execute, self.dialog.actions[value], call.cancelled)
            self.task = (future, call, value)
            log.info("action_requested id=%s", value)
        else:
            call.followup = kind == "followup"
            call.play(self.speech.path(value), "hangup" if kind == "goodbye" else "beep")

    def process_event(self, kind, call, value):
        if kind == "state":
            if value == pj.PJSIP_INV_STATE_CONFIRMED and not call.confirmed:
                call.confirmed = True
                if call.callback_trigger:
                    call.end()  # ACK received; BYE ends all ringing before callback.
                elif call is self.current:
                    call.session = self.dialog.connected(call.caller)
            elif value == pj.PJSIP_INV_STATE_DISCONNECTED:
                call.disconnected = True
                call.clear_media()
                for key, obj in list(self.calls.items()):
                    if obj is call:
                        del self.calls[key]
                if call is self.current:
                    self.current = None
                    if call.callback_trigger and (self.config.callback["trigger_mode"] == "reject" or call.confirmed):
                        self.pending = (time.monotonic() + self.config.callback["delay_ms"] / 1000, call.caller)
        elif kind == "media" and not call.disconnected and not call.callback_trigger:
            call.attach_media()
        elif kind == "playback" and call.player is value and not call.cancelled.is_set():
            value.stopTransmit(call.media)
            call.player = None
            if value.after == "hangup":
                call.end()
            elif value.after == "beep":
                # Let prompt echoes fade before announcing readiness.
                call.beep_at = time.monotonic() + 0.25
            else:
                # ASR is already prepared. Capture immediately after the tone.
                self.dialog.listened(call.session, time.monotonic(), call.followup)
                call.listening = True
                log.info("dialog_listening state=%s wait_seconds=%s", call.session.state, self.config.dialog["listen_timeout_seconds"])

    def step(self):
        self.endpoint.libHandleEvents(20)
        for _ in range(100):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            self.process_event(*event)
        now = time.monotonic()
        if self.pending and now >= self.pending[0]:
            _, caller = self.pending
            self.pending = None
            if self.registered:
                call = Call(self)
                call.caller = caller
                self.current = call
                op = pj.CallOpParam(True)
                op.opt.audioCount = 1
                op.opt.videoCount = 0
                try:
                    call.makeCall(callback_uri(caller, self.config.sip["host"], self.config.sip["port"], self.config.sip["transport"]), op)
                    self.calls[call.getId()] = call
                    log.info("callback_started")
                except pj.Error:
                    self.current = None
                    log.warning("callback_failed")
        if self.task and self.task[0].done():
            future, call, action = self.task
            self.task = None
            try:
                result = future.result()
            except Exception:
                result = "unconfirmed"
            log.info("action_result id=%s result=%s", action, result)
            if call is self.current and not call.cancelled.is_set():
                self.dispatch(call, self.dialog.result(call.session, action, result))
        call = self.current
        if call is None or call.cancelled.is_set():
            return
        if not call.confirmed:
            if now - call.created_at >= self.config.callback["ring_timeout_seconds"]:
                call.end()
            return
        if call.session is None:
            return
        if now - call.session.connected_at >= self.config.dialog["max_call_seconds"]:
            call.end()
            return
        if call.media is None:
            if now - call.session.connected_at > 10:
                call.end()
            return
        self.dialog.media_ready(call.session, now)
        if call.beep_at is not None and now >= call.beep_at:
            call.beep_at = None
            while not call.audio.empty():
                call.audio.get_nowait()
            self.speech.reset()
            call.last_voice = None
            call.audio_overflow = False
            call.play(self.speech.beep, "listen")
        if call.listening:
            if now >= call.session.deadline:
                log.info("dialog_response_timeout state=%s speech_started=%s", call.session.state, call.session.speech_started_at is not None)
                self.dispatch(call, self.dialog.tick(call.session, now))
                return
            if call.audio_overflow:
                log.warning("speech_audio_overflow")
                self.dispatch(call, self.dialog.misunderstood(call.session))
                return
            for _ in range(10):
                try:
                    pcm = call.audio.get_nowait()
                except queue.Empty:
                    break
                if pcm and audioop.rms(pcm, 2) >= 250:
                    call.last_voice = now
                    self.dialog.speech_started(call.session, now)
                recognized = self.speech.feed(pcm)
                if recognized:
                    self.dispatch(call, self.dialog.recognize(call.session, *recognized))
                    break
            if call.listening and call.last_voice is not None and now - call.last_voice >= self.config.speech["end_silence_ms"] / 1000:
                recognized = self.speech.finish()
                if recognized:
                    self.dispatch(call, self.dialog.recognize(call.session, *recognized))
                else:
                    # A click/beep/echo can trigger RMS without producing speech.
                    # Keep listening within the original response window.
                    self.speech.reset()
                    call.last_voice = None
                    self.dialog.no_speech(call.session)
                    log.info("speech_empty_result ignored=True")
        self.dispatch(call, self.dialog.tick(call.session, now))

    def health(self):
        path = self.config.data_dir / "health.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"at": time.time(), "registered": self.registered, "registration_code": self.registration_code, "speech_ready": self.speech is not None, "busy": bool(self.busy)}), encoding="utf-8")
        temporary.replace(path)

    def run(self, duration=None) -> bool:
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: setattr(self, "stopping", True))
        start, last_health = time.monotonic(), 0
        registered_once = False
        try:
            while not self.stopping and (duration is None or time.monotonic() - start < duration):
                self.step()
                registered_once |= self.registered
                if time.monotonic() - last_health >= 2:
                    self.health()
                    last_health = time.monotonic()
        finally:
            self.pending = None
            for call in list(self.calls.values()):
                call.end()
            self.pool.shutdown(wait=True, cancel_futures=True)
            for _ in range(10):
                self.endpoint.libHandleEvents(20)
            for call in list(self.calls.values()):
                call.clear_media()
            self.calls.clear()
            self.current = None
            self.account.shutdown()
            self.endpoint.libDestroy()
            if self.openhab:
                self.openhab.close()
            self.registered = False
            self.health()
        return registered_once
