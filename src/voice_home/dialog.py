"""Testable conversation state machine, independent of SIP/ASR libraries."""

from dataclasses import dataclass, field
import time

from .config import Caller, Config
from .intents import Intents


@dataclass
class Session:
    caller: Caller
    connected_at: float
    state: str = "answer_delay"
    deadline: float = 0
    used: set[str] = field(default_factory=set)
    failures: int = 0


class Dialog:
    def __init__(self, config: Config):
        self.config = config
        self.intents = Intents(config.actions)
        self.actions = {a.id: a for a in config.actions}

    def connected(self, caller: Caller, now: float | None = None) -> Session:
        now = time.monotonic() if now is None else now
        return Session(caller, now, deadline=now + self.config.dialog["answer_delay_ms"] / 1000)

    def tick(self, s: Session, now: float) -> tuple[str, str] | None:
        if now - s.connected_at >= self.config.dialog["max_call_seconds"]:
            s.state = "ended"
            return "hangup", ""
        if s.state == "answer_delay" and now >= s.deadline:
            s.state = "speaking"
            names = ", ".join(a.aliases[0] for a in self.config.actions if a.enabled)
            suffix = f" Verfügbar sind: {names}." if names else " Aktuell ist noch keine Aktion eingerichtet."
            return "say", f"Hallo {s.caller.name}, was möchtest du tun?{suffix}"
        if s.state in {"listening", "followup"} and now >= s.deadline:
            return self.misunderstood(s)
        return None

    def listened(self, s: Session, now: float, followup: bool = False):
        s.state = "followup" if followup else "listening"
        s.deadline = now + self.config.dialog["listen_timeout_seconds"]

    def misunderstood(self, s: Session) -> tuple[str, str]:
        s.failures += 1
        s.state = "speaking"
        if s.failures >= self.config.dialog["max_failures"]:
            return "goodbye", "Ich konnte dich nicht verstehen. Auf Wiederhören."
        return "say", "Bitte nenne eine Aktion, zum Beispiel Haustür öffnen."

    def recognize(self, s: Session, text: str, confidence: float) -> tuple[str, str] | None:
        if s.state not in {"listening", "followup"}:
            return None
        kind, value = self.intents.parse(text)
        if confidence < self.config.speech["min_confidence"]:
            return self.misunderstood(s)
        if kind == "stop":
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
        if value in s.used:
            return "followup", "Diese Aktion wurde bereits angefordert. Möchtest du noch etwas?"
        s.used.add(value)
        s.state = "executing"
        return "execute", value

    def result(self, s: Session, action_id: str, result: str) -> tuple[str, str]:
        s.state = "speaking"
        text = {"ok": self.actions[action_id].success_text, "failed": "Fehlgeschlagen.", "unconfirmed": "Die Ausführung konnte nicht bestätigt werden.", "disabled": "Diese Aktion ist noch nicht eingerichtet."}[result]
        return "followup", text + " Möchtest du noch etwas?"

    def prompts(self) -> set[str]:
        texts = {"Auf Wiederhören.", "Ich konnte dich nicht verstehen. Auf Wiederhören.", "Bitte nenne eine Aktion, zum Beispiel Haustür öffnen.", "Was möchtest du tun?", "Diese Aktion ist noch nicht eingerichtet. Möchtest du noch etwas?", "Diese Aktion wurde bereits angefordert. Möchtest du noch etwas?"}
        for caller in self.config.callers:
            s = self.connected(caller, 0)
            texts.add(self.tick(s, self.config.dialog["answer_delay_ms"] / 1000)[1])
        for action in self.config.actions:
            for result in ("ok", "failed", "unconfirmed", "disabled"):
                dummy = Session(Caller("", ""), 0)
                texts.add(self.result(dummy, action.id, result)[1])
        return texts
