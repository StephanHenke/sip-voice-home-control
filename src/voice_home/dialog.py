"""Testable conversation state machine, independent of SIP/ASR libraries."""

from dataclasses import dataclass
import time

from .config import Caller, Config
from .intents import Intents, NO_PHRASES, normalize


@dataclass
class Session:
    caller: Caller
    connected_at: float
    state: str = "waiting_media"
    deadline: float = 0
    pending_action: str | None = None
    failures: int = 0


class Dialog:
    def __init__(self, config: Config):
        self.config = config
        self.intents = Intents(config.actions)
        self.actions = {a.id: a for a in config.actions}

    def connected(self, caller: Caller, now: float | None = None) -> Session:
        now = time.monotonic() if now is None else now
        return Session(caller, now)

    def media_ready(self, s: Session, now: float):
        if s.state == "waiting_media":
            s.state = "answer_delay"
            s.deadline = now + self.config.dialog["answer_delay_ms"] / 1000

    def greeting(self, caller: Caller) -> str:
        suffix = "" if any(a.enabled for a in self.config.actions) else " Aktuell ist noch keine Aktion eingerichtet."
        return f"Hallo {caller.name}, was möchtest du tun?{suffix}"

    def confirmation_retry(self, action_id: str) -> str:
        return "Bitte antworte mit Ja oder Nein. " + self.actions[action_id].confirmation_text

    def tick(self, s: Session, now: float) -> tuple[str, str] | None:
        if now - s.connected_at >= self.config.dialog["max_call_seconds"]:
            s.state = "ended"
            s.pending_action = None
            return "hangup", ""
        if s.state == "answer_delay" and now >= s.deadline:
            s.state = "speaking"
            return "say", self.greeting(s.caller)
        if s.state in {"listening", "followup", "confirming"} and now >= s.deadline:
            return self.misunderstood(s)
        return None

    def listened(self, s: Session, now: float, followup: bool = False):
        s.state = "confirming" if s.pending_action is not None else "followup" if followup else "listening"
        s.deadline = now + self.config.dialog["listen_timeout_seconds"]

    def misunderstood(self, s: Session) -> tuple[str, str]:
        s.failures += 1
        s.state = "speaking"
        if s.failures >= self.config.dialog["max_failures"]:
            s.pending_action = None
            return "goodbye", "Ich konnte dich nicht verstehen. Auf Wiederhören."
        if s.pending_action is not None:
            return "say", self.confirmation_retry(s.pending_action)
        return "say", "Bitte nenne eine Aktion, zum Beispiel Haustür öffnen."

    def recognize(self, s: Session, text: str, confidence: float) -> tuple[str, str] | None:
        if s.state not in {"listening", "followup", "confirming"}:
            return None
        kind, value = self.intents.parse(text)
        if confidence < self.config.speech["min_confidence"]:
            return self.misunderstood(s)
        if s.pending_action is not None:
            if kind == "yes":
                action_id = s.pending_action
                s.pending_action = None
                s.failures = 0
                s.state = "executing"
                return "execute", action_id
            if kind == "stop" and normalize(text) in NO_PHRASES | {"abbrechen"}:
                s.pending_action = None
                s.failures = 0
                s.state = "speaking"
                return "followup", "Abgebrochen. Möchtest du noch etwas?"
            if kind != "stop":
                return self.misunderstood(s)
        if kind == "stop":
            s.pending_action = None
            s.state = "speaking"
            return "goodbye", "Auf Wiederhören."
        if kind == "yes" and s.state == "followup":
            s.failures = 0
            s.state = "speaking"
            return "say", "Was möchtest du tun?"
        if kind != "action":
            return self.misunderstood(s)
        s.failures = 0
        s.state = "speaking"
        action = self.actions[value]
        if not action.enabled:
            return "followup", "Diese Aktion ist noch nicht eingerichtet. Möchtest du noch etwas?"
        if action.require_confirmation:
            s.pending_action = value
            return "say", action.confirmation_text
        s.state = "executing"
        return "execute", value

    def result(self, s: Session, action_id: str, result: str) -> tuple[str, str]:
        s.pending_action = None
        s.state = "speaking"
        text = {"ok": self.actions[action_id].success_text, "failed": "Fehlgeschlagen.", "unconfirmed": "Die Ausführung konnte nicht bestätigt werden.", "disabled": "Diese Aktion ist noch nicht eingerichtet."}[result]
        return "followup", text + " Möchtest du noch etwas?"

    def prompts(self) -> set[str]:
        texts = {"Auf Wiederhören.", "Ich konnte dich nicht verstehen. Auf Wiederhören.", "Bitte nenne eine Aktion, zum Beispiel Haustür öffnen.", "Was möchtest du tun?", "Diese Aktion ist noch nicht eingerichtet. Möchtest du noch etwas?", "Abgebrochen. Möchtest du noch etwas?"}
        for caller in self.config.callers:
            texts.add(self.greeting(caller))
        for action in self.config.actions:
            if action.require_confirmation:
                texts.add(action.confirmation_text)
                texts.add(self.confirmation_retry(action.id))
            for result in ("ok", "failed", "unconfirmed", "disabled"):
                dummy = Session(Caller("", ""), 0)
                texts.add(self.result(dummy, action.id, result)[1])
        return texts
