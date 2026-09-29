"""Validated configuration. Secrets are read separately and never logged."""

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse
import ipaddress
import math
import re

import phonenumbers
import yaml


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
    success_values: list[str] = field(default_factory=list)
    failure_values: list[str] = field(default_factory=list)
    timeout_seconds: float = 10
    success_text: str = "OK."


@dataclass(frozen=True)
class Config:
    sip: dict
    callers: list[Caller]
    actions: list[Action]
    dialog: dict
    callback: dict
    openhab: dict
    speech: dict
    data_dir: Path
    region: str = "DE"


def load(path: str | Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Konfiguration muss ein YAML-Objekt sein")
    unknown = set(raw) - {"sip", "callers", "actions", "dialog", "callback", "openhab", "speech", "data_dir", "region"}
    if unknown:
        raise ValueError(f"Unbekannte Konfigurationsbereiche: {sorted(unknown)}")
    region = raw.get("region", "DE")
    sip = {"port": 5060, "local_port": 5062, "rtp_port": 40000, **raw.get("sip", {})}
    ipaddress.IPv4Address(sip["host"])
    for key in ("port", "local_port", "rtp_port"):
        if type(sip[key]) is not int or not 1024 <= sip[key] <= 65520:
            raise ValueError(f"Ungültiger SIP-Port: {key}")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", sip["username"]):
        raise ValueError("Ungültiger SIP-Benutzername")
    if not sip.get("password_file"):
        raise ValueError("sip.password_file fehlt")
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
        if not all(isinstance(s, str) and s.strip() for s in action.aliases + action.patterns):
            raise ValueError("Leere/ungültige Sprachmuster")
        if any(p.count("{target}") != 1 or "{" in p.replace("{target}", "") or "}" in p.replace("{target}", "") for p in action.patterns):
            raise ValueError("Satzmuster benötigen genau einen {target}-Platzhalter")
        if type(action.timeout_seconds) not in (int, float) or not 0 < action.timeout_seconds <= 60:
            raise ValueError("Aktions-Timeout muss zwischen 0 und 60 Sekunden liegen")
        if not all(isinstance(v, str) for v in action.success_values + action.failure_values):
            raise ValueError("Rückmeldewerte müssen Strings sein (Zahlen in Anführungszeichen)")
        if set(action.success_values) & set(action.failure_values):
            raise ValueError("Erfolgs- und Fehlerwerte überschneiden sich")
        if {"NULL", "UNDEF"} & set(action.success_values):
            raise ValueError("NULL/UNDEF sind keine Erfolgszustände")
        if action.enabled:
            if not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", s) for s in (action.command_item, action.feedback_item)):
                raise ValueError("Aktivierte Aktionen benötigen gültige Item-Namen")
            if action.command_item == action.feedback_item:
                raise ValueError("Ein separates Geräte-Rückmelde-Item ist erforderlich")
            if not isinstance(action.command, str) or not action.command or not action.success_values:
                raise ValueError("Aktivierte Aktion benötigt Befehl und Erfolgswerte")
        actions.append(action)
    dialog = {"answer_delay_ms": 1000, "listen_timeout_seconds": 8, "max_failures": 2, "max_call_seconds": 120, **raw.get("dialog", {})}
    callback = {"delay_ms": 3000, "ring_timeout_seconds": 30, "cooldown_seconds": 60, "max_attempts_per_number_per_hour": 5, **raw.get("callback", {})}
    speech = {"asr_model": "/models/vosk-model-small-de-0.15", "tts_model": "/models/de_DE-thorsten-medium.onnx", "min_confidence": 0.85, "end_silence_ms": 700, **raw.get("speech", {})}
    for settings in (dialog, callback):
        for key, value in settings.items():
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or (key not in {"answer_delay_ms", "delay_ms"} and value == 0):
                raise ValueError(f"Ungültige Zeit/Grenze: {key}")
    if type(callback["max_attempts_per_number_per_hour"]) is not int or type(dialog["max_failures"]) is not int:
        raise ValueError("Zählergrenzen müssen ganze Zahlen sein")
    if not 0 <= speech["min_confidence"] <= 1 or not 300 <= speech["end_silence_ms"] <= 2000:
        raise ValueError("Ungültige Spracherkennungseinstellungen")
    openhab = {"base_url": "http://openhab:8080", "token_file": "", **raw.get("openhab", {})}
    parsed_url = urlparse(openhab["base_url"])
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname or parsed_url.username or parsed_url.query or parsed_url.fragment:
        raise ValueError("Ungültige openHAB-URL")
    return Config(sip, callers, actions, dialog, callback, openhab, speech, Path(raw.get("data_dir", "/data")), region)
