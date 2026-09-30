"""Validated configuration. Secrets are read separately and never logged."""

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse
import ipaddress
import math
import re

import phonenumbers
import yaml

from .settings import credential_source, operational_settings


def number(value: str, region: str = "DE") -> str:
    if not isinstance(value, str):
        raise ValueError("Rufnummern müssen Strings sein")
    value = value.strip()
    if not re.fullmatch(r"\+?[0-9 ()/.-]+", value):
        raise ValueError("Rufnummer muss eine externe Telefonnummer sein")
    try:
        parsed = phonenumbers.parse(value, region)
    except phonenumbers.NumberParseException as exc:
        raise ValueError("Ungültige Rufnummer") from exc
    if not phonenumbers.is_possible_number(parsed):
        raise ValueError("Unvollständige Rufnummer")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def secret(path: str) -> str:
    result = Path(path).read_text(encoding="utf-8").strip()
    if not result:
        raise ValueError("Leere Secret-Datei")
    return result


def credential(settings: dict, name: str) -> str:
    return settings.get(name) or (secret(settings[name + '_file']) if settings.get(name + '_file') else '')


@dataclass(frozen=True)
class Caller:
    number: str
    name: str
    access_mode: str = "callback"


@dataclass(frozen=True)
class Action:
    id: str
    aliases: list[str]
    patterns: list[str]
    enabled: bool = False
    command_item: str = ""
    command: str = ""
    feedback_item: str = ""
    feedback_mode: str = "state"
    success_values: list[str] = field(default_factory=list)
    failure_values: list[str] = field(default_factory=list)
    timeout_seconds: float = 10
    success_text: str = "OK."
    state_values: dict[str, list[str]] = field(default_factory=dict)
    success_states: list[str] = field(default_factory=list)
    failure_states: list[str] = field(default_factory=list)
    open_position: float = 0
    closed_position: float = 100
    require_confirmation: bool = False
    confirmation_text: str = ""

    @property
    def resolved_success_values(self) -> set[str]:
        return set(self.success_values) | {v for state in self.success_states for v in self.state_values[state]}

    @property
    def resolved_failure_values(self) -> set[str]:
        return set(self.failure_values) | {v for state in self.failure_states for v in self.state_values[state]}

    def state_for(self, value: str) -> str | None:
        return next((state for state, values in self.state_values.items() if value in values), None)


def validate_feedback(action: Action):
    def values(value):
        return isinstance(value, list) and all(isinstance(v, str) and v.strip() for v in value)

    if not all(values(v) for v in (action.success_values, action.failure_values, action.success_states, action.failure_states)):
        raise ValueError("Rückmeldewerte und Zustandsnamen müssen Listen nichtleerer Strings sein")
    if not isinstance(action.state_values, dict):
        raise ValueError("state_values muss Zustandsnamen auf Wertelisten abbilden")
    seen_values = set()
    for state, raw_values in action.state_values.items():
        if not isinstance(state, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", state) or not values(raw_values) or not raw_values:
            raise ValueError("Zustandszuordnung benötigt Namen und nichtleere Wertelisten")
        if seen_values & set(raw_values):
            raise ValueError("Ein Rohwert darf nur einem Zustand zugeordnet sein")
        seen_values.update(raw_values)
    if (set(action.success_states) | set(action.failure_states)) - action.state_values.keys():
        raise ValueError("Erfolgs- und Fehlerzustände müssen in state_values definiert sein")
    if action.state_values and (action.success_values or action.failure_values):
        raise ValueError("Zustandszuordnung und direkte Erfolgs-/Fehlerwerte nicht mischen")
    success, failure = action.resolved_success_values, action.resolved_failure_values
    if success & failure:
        raise ValueError("Erfolgs- und Fehlerwerte überschneiden sich")
    if {"NULL", "UNDEF"} & success:
        raise ValueError("NULL/UNDEF sind keine Erfolgszustände")
    if action.feedback_mode not in {"state", "rollershutter_opening"}:
        raise ValueError("Unbekannter Rückmeldemodus")
    for position in (action.open_position, action.closed_position):
        if type(position) not in (int, float) or not math.isfinite(position) or not 0 <= position <= 100:
            raise ValueError("Offene und geschlossene Position müssen zwischen 0 und 100 liegen")
    if action.open_position == action.closed_position:
        raise ValueError("Offene und geschlossene Position müssen unterschiedlich sein")
    if action.feedback_mode == "rollershutter_opening":
        if action.state_values or action.success_states or action.failure_states or action.success_values:
            raise ValueError("Rollershutter-Positionen nicht mit Zustandszuordnung oder Erfolgswerten mischen")
        if not isinstance(action.command, str):
            raise ValueError("Rollershutter-Befehl muss ein String sein")
        if action.command not in {"UP", "DOWN"}:
            try:
                command_position = float(action.command)
            except (TypeError, ValueError):
                raise ValueError("Rollershutter-Öffnung benötigt UP, DOWN oder eine Prozentposition") from None
            if not math.isfinite(command_position) or not 0 <= command_position <= 100:
                raise ValueError("Ungültige Rollershutter-Befehlsposition")
    elif action.open_position != 0 or action.closed_position != 100:
        raise ValueError("Positionszuordnung ist nur im Rollershutter-Modus erlaubt")


@dataclass(frozen=True)
class Config:
    sip: dict = field(repr=False)
    callers: list[Caller]
    actions: list[Action]
    dialog: dict
    callback: dict
    openhab: dict = field(repr=False)
    speech: dict
    data_dir: Path
    region: str = "DE"
    call_control: dict = field(default_factory=dict)
    smarthome: dict = field(default_factory=dict)
    logging: dict = field(default_factory=dict)


def load(path: str | Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Konfiguration muss ein YAML-Objekt sein")
    unknown = set(raw) - {"sip", "callers", "actions", "dialog", "callback", "openhab", "speech", "data_dir", "region", "call_control", "smarthome", "logging"}
    if unknown:
        raise ValueError(f"Unbekannte Konfigurationsbereiche: {sorted(unknown)}")
    region = raw.get("region", "DE")
    sip = {"port": 5060, "local_port": 5062, "rtp_port": 40000, "transport": "udp", **raw.get("sip", {})}
    ipaddress.IPv4Address(sip["host"])
    if sip["transport"] not in {"udp", "tcp"}:
        raise ValueError("sip.transport muss udp oder tcp sein")
    for key in ("port", "local_port", "rtp_port"):
        if type(sip[key]) is not int or not 1024 <= sip[key] <= 65520:
            raise ValueError(f"Ungültiger SIP-Port: {key}")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", sip["username"]):
        raise ValueError("Ungültiger SIP-Benutzername")
    credential_source(sip, "password", Path(path).resolve().parent, required=True)
    if sip.get("public_address"):
        ipaddress.IPv4Address(sip["public_address"])
    callers = [Caller(number(c["number"], region), str(c["name"]).strip(), c.get("access_mode", "callback")) for c in raw.get("callers", [])]
    seen = set()
    own_number = number(sip["controller_number"], region) if sip.get("controller_number") else None
    for c in callers:
        if not c.name or len(c.name) > 80 or c.access_mode not in {"direct", "callback"}:
            raise ValueError("Anrufer benötigt Namen und gültigen access_mode")
        if c.number in seen or c.number == own_number:
            raise ValueError("Doppelte Anrufernummer oder Rückruf auf eigene Controller-Nummer")
        seen.add(c.number)
    actions = []
    ids = set()
    for a in raw.get("actions", []):
        action = Action(**a)
        if not re.fullmatch(r"[a-z][a-z0-9_]*", action.id) or action.id in ids:
            raise ValueError("Aktionskennungen müssen eindeutig sein")
        ids.add(action.id)
        if not action.aliases or not action.patterns or type(action.enabled) is not bool:
            raise ValueError("Aktion benötigt Aliase, Satzmuster und boolesches enabled")
        if type(action.require_confirmation) is not bool or not isinstance(action.confirmation_text, str):
            raise ValueError("Bestätigung benötigt boolesches require_confirmation und einen Fragetext als String")
        if action.require_confirmation and not action.confirmation_text.strip():
            raise ValueError("Bei require_confirmation=true ist confirmation_text erforderlich")
        if not all(isinstance(s, str) and s.strip() for s in action.aliases + action.patterns):
            raise ValueError("Leere/ungültige Sprachmuster")
        if any(p.count("{target}") != 1 or "{" in p.replace("{target}", "") or "}" in p.replace("{target}", "") for p in action.patterns):
            raise ValueError("Satzmuster benötigen genau einen {target}-Platzhalter")
        if type(action.timeout_seconds) not in (int, float) or not 0 < action.timeout_seconds <= 60:
            raise ValueError("Aktions-Timeout muss zwischen 0 und 60 Sekunden liegen")
        validate_feedback(action)
        if action.enabled:
            if not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", s) for s in (action.command_item, action.feedback_item)):
                raise ValueError("Aktivierte Aktionen benötigen gültige Item-Namen")
            if not isinstance(action.command, str) or not action.command or (action.feedback_mode == "state" and not action.resolved_success_values):
                raise ValueError("Aktivierte Aktion benötigt Befehl und Erfolgswerte")
        actions.append(action)
    dialog = {"answer_delay_ms": 1000, "listen_timeout_seconds": 15, "max_utterance_seconds": 15, "max_failures": 2, "max_call_seconds": 120, **raw.get("dialog", {})}
    callback = {"trigger_mode": "reject", "delay_ms": 3000, "ring_timeout_seconds": 30, "cooldown_seconds": 60, "max_attempts_per_number_per_hour": 5, **raw.get("callback", {})}
    if callback["trigger_mode"] not in {"reject", "answer_hangup"}:
        raise ValueError("callback.trigger_mode muss reject oder answer_hangup sein")
    speech = {"asr_model": "/models/vosk-model-small-de-0.15", "tts_model": "/models/de_DE-thorsten-medium.onnx", "command_vocabulary": True, "min_confidence": 0.85, "end_silence_ms": 700, **raw.get("speech", {})}
    if type(speech["command_vocabulary"]) is not bool:
        raise ValueError("speech.command_vocabulary muss true oder false sein")
    for settings in (dialog, callback):
        for key, value in settings.items():
            if key == "trigger_mode":
                continue
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or (key not in {"answer_delay_ms", "delay_ms", "cooldown_seconds", "max_attempts_per_number_per_hour"} and value == 0):
                raise ValueError(f"Ungültige Zeit/Grenze: {key}")
    if type(callback["max_attempts_per_number_per_hour"]) is not int or type(dialog["max_failures"]) is not int:
        raise ValueError("Zählergrenzen müssen ganze Zahlen sein")
    if not 0 <= speech["min_confidence"] <= 1 or not 300 <= speech["end_silence_ms"] <= 2000:
        raise ValueError("Ungültige Spracherkennungseinstellungen")
    openhab = {"base_url": "http://openhab:8080", "token_file": "", **raw.get("openhab", {})}
    parsed_url = urlparse(openhab["base_url"])
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname or parsed_url.username or parsed_url.query or parsed_url.fragment:
        raise ValueError("Ungültige openHAB-URL")
    credential_source(openhab, "token", Path(path).resolve().parent)
    control, smart, logs = operational_settings(raw)
    return Config(sip, callers, actions, dialog, callback, openhab, speech, Path(raw.get("data_dir", "/data")), region, control, smart, logs)
