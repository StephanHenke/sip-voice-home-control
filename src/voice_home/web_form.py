"""Form defaults and presentation metadata. YAML stays the only configuration store."""
from dataclasses import asdict
from copy import deepcopy
import json
import yaml
from .config import Action, Caller
from .credentials import parse_yaml
from .settings import SettingsError

DEFAULTS = {
    'region': 'DE', 'data_dir': '/data',
    'sip': {'host': '', 'username': '', 'password': '', 'password_file': '', 'port': 5060,
            'local_port': 5062, 'rtp_port': 40000, 'transport': 'udp', 'controller_number': '', 'public_address': ''},
    'openhab': {'base_url': 'http://openhab:8080', 'token': '', 'token_file': ''},
    'callers': [], 'actions': [],
    'web': {'enabled': True, 'bind': '0.0.0.0', 'port': 8443},
    'dialog': {'answer_delay_ms': 1000, 'listen_timeout_seconds': 15, 'max_utterance_seconds': 15,
               'max_failures': 2, 'max_call_seconds': 120},
    'callback': {'trigger_mode': 'reject', 'delay_ms': 3000, 'ring_timeout_seconds': 30,
                 'cooldown_seconds': 60, 'max_attempts_per_number_per_hour': 5},
    'speech': {'command_vocabulary': True, 'asr_model': '/models/vosk-model-small-de-0.15',
               'tts_model': '/models/de_DE-thorsten-medium.onnx', 'min_confidence': .85, 'end_silence_ms': 700},
    'call_control': {'enabled': False, 'initial_accepting': True, 'switch_item': '', 'status_item': '',
                     'call_active_item': '', 'heartbeat_item': '', 'heartbeat_interval_seconds': 10},
    'smarthome': {'adapter': 'openhab', 'notification_item': ''},
    'logging': {'level': 'INFO', 'target': 'console', 'path': '', 'max_bytes': 10485760,
                'backup_count': 2, 'host': '', 'port': 514, 'transport': 'udp', 'facility': 'local0', 'queue_size': 1000},
}
TEMPLATES = {'callers': asdict(Caller('', '', 'callback')),
             'actions': asdict(Action('', ['Haustür'], ['{target} öffnen']))}
LABELS = {
    'region': 'Land für Rufnummern', 'data_dir': 'Datenverzeichnis',
    'sip': 'Telefonie · FRITZ!Box / SIP', 'openhab': 'Verbindung zu openHAB',
    'callers': 'Erlaubte Anrufer', 'actions': 'Geräte und Aktionen', 'web': 'Weboberfläche',
    'dialog': 'Gespräch und Wartezeiten', 'callback': 'Rückruf und Limits', 'speech': 'Spracherkennung und Stimme',
    'call_control': 'Anrufannahme und Betriebsstatus', 'smarthome': 'Smart-Home-Adapter und Benachrichtigungen',
    'logging': 'Protokollierung', 'host': 'Serveradresse', 'username': 'SIP-Benutzername',
    'password': 'SIP-Passwort', 'password_file': 'Alternative: Passwortdatei',
    'token': 'openHAB-API-Token', 'token_file': 'Alternative: Tokendatei', 'base_url': 'openHAB-Adresse (URL)',
    'port': 'Port', 'local_port': 'Lokaler SIP-Port', 'rtp_port': 'Erster RTP-Port', 'transport': 'Transport',
    'controller_number': 'Eigene Rufnummer des Controllers', 'public_address': 'Angekündigte IP (optional)',
    'name': 'Name für die Begrüßung', 'number': 'Telefonnummer', 'access_mode': 'Anrufzugang',
    'fixed_action': 'Feste Aktion bei Anruf', 'require_confirmation': 'Explizite Bestätigung verlangen',
    'id': 'Aktionskennung', 'aliases': 'Zielnamen / Synonyme', 'patterns': 'Sprachmuster mit {target}',
    'enabled': 'Aktiviert', 'command_item': 'Befehls-Item', 'command': 'Befehl', 'feedback_item': 'Status-Item',
    'feedback_mode': 'Art der Rückmeldung', 'success_values': 'Erfolgreiche Rohwerte',
    'failure_values': 'Fehler-Rohwerte', 'timeout_seconds': 'Zeit für Gerätebestätigung (Sekunden)',
    'success_text': 'Erfolgsansage', 'notification_text': 'Push-Text (optional, {name} möglich)',
    'state_values': 'Zustandsnamen und Rohwerte', 'success_states': 'Erfolgreiche Zustände',
    'failure_states': 'Fehlerzustände', 'open_position': 'Position geöffnet (%)', 'closed_position': 'Position geschlossen (%)',
    'confirmation_text': 'Bestätigungsfrage', 'bind': 'Lokale Bind-Adresse',
    'answer_delay_ms': 'Pause nach Annehmen (Millisekunden)', 'listen_timeout_seconds': 'Auf Antwort warten (Sekunden)',
    'max_utterance_seconds': 'Maximale Sprechdauer (Sekunden)', 'max_failures': 'Maximale Fehlversuche',
    'max_call_seconds': 'Maximale Gesprächsdauer (Sekunden)', 'trigger_mode': 'Rückruf auslösen durch',
    'delay_ms': 'Pause vor Rückruf (Millisekunden)', 'ring_timeout_seconds': 'Maximale Klingeldauer (Sekunden)',
    'cooldown_seconds': 'Mindestabstand zwischen Rückrufen (Sekunden)',
    'max_attempts_per_number_per_hour': 'Rückrufe pro Nummer und Stunde',
    'command_vocabulary': 'Auf bekannte Befehle begrenzen', 'asr_model': 'Spracherkennungsmodell (Pfad)',
    'tts_model': 'Stimmenmodell (Pfad)', 'min_confidence': 'Minimale Erkennungssicherheit (0–1)',
    'end_silence_ms': 'Sprechende nach Stille (Millisekunden)', 'adapter': 'Adapter',
    'notification_item': 'Benachrichtigungs-Item (optional)', 'initial_accepting': 'Anrufe nach Start annehmen',
    'switch_item': 'Annahme-Switch', 'status_item': 'Betriebsstatus-Item', 'call_active_item': 'Gespräch-aktiv-Item',
    'heartbeat_item': 'Lebenszeichen-Item', 'heartbeat_interval_seconds': 'Lebenszeichenintervall (Sekunden)',
    'level': 'Detailgrad', 'target': 'Logziel', 'path': 'Absoluter Log-Dateipfad', 'max_bytes': 'Rotation ab (Bytes)',
    'backup_count': 'Archivdateien', 'facility': 'Syslog-Facility', 'queue_size': 'Maximale RAM-Warteschlange',
}
HELP = {
    'callers': 'Ohne Eintrag werden keine Anrufer freigegeben. Rückruf verwendet immer die hier gespeicherte Nummer.',
    'actions': 'Neue Aktionen sind deaktiviert. Zuerst echte Geräterückmeldungen einrichten und vor Ort testen.',
    'fixed_action': 'Leer: normaler Sprachdialog. Sonst genau diese Aktion nach Annahme, Ergebnisansage und Auflegen. Beim Rückruf erst nach dessen Annahme.',
    'require_confirmation': 'Eine Bestätigung an der Aktion gilt immer. Bei Anrufern ist dies eine zusätzliche Anforderung für die feste Aktion.',
    'password': 'Neuen Wert eingeben oder gespeicherten verschlüsselten Wert beibehalten. Beim Speichern verschlüsselt.',
    'token': 'Optional. Neuen Wert eingeben oder gespeicherten verschlüsselten Wert beibehalten.',
    'password_file': 'Nur eine Quelle verwenden: Passwort ODER Datei. Relativ zur YAML-Datei. Externe Dateien werden nicht automatisch verändert.',
    'token_file': 'Nur eine Quelle verwenden: Token ODER Datei. Relativ zur YAML-Datei.',
    'patterns': 'Eine Zeile pro Muster, jeweils genau ein {target}. Beispiel: öffne die {target}',
    'aliases': 'Ein Zielname pro Zeile. Beispiel: Haustür und Tür.',
    'feedback_item': 'Dasselbe Item wie der Befehl ist möglich, benötigt aber echte Geräteupdates (autoupdate=false).',
    'state_values': 'Optional: Rohwerte benannten Zuständen zuordnen. Nicht gleichzeitig success_values verwenden.',
    'cooldown_seconds': '0 deaktiviert den Mindestabstand.',
    'max_attempts_per_number_per_hour': '0 deaktiviert das Stundenlimit. Neustarts setzen die RAM-Limits zurück.',
    'web': 'Deaktivieren schließt die Oberfläche nach dem Neustart. Wieder aktivieren: YAML per Konsole ändern und Container neu starten. TLS und Webpasswort bleiben erhalten.',
    'logging': 'OFF oder none unterdrückt reguläre Logs. Docker-Logging wird separat in Compose eingestellt.',
    'speech': 'Die Modellpfade müssen im Container vorhanden sein. Hier wird kein Modell heruntergeladen.',
}
OPTIONS = {
    'sip.transport': ['udp', 'tcp'], 'logging.transport': ['udp', 'tcp'],
    'access_mode': ['callback', 'direct'], 'feedback_mode': ['state', 'rollershutter_opening'],
    'callback.trigger_mode': ['reject', 'answer_hangup'], 'smarthome.adapter': ['openhab'],
    'logging.level': ['OFF', 'ERROR', 'WARNING', 'INFO', 'DEBUG'],
    'logging.target': ['none', 'console', 'file', 'syslog'],
    'logging.facility': [f'local{i}' for i in range(8)],
}


def merge(default, value):
    if isinstance(default, dict) and isinstance(value, dict):
        return {**{k: merge(v, value.get(k, v)) for k, v in default.items()}, **{k: v for k, v in value.items() if k not in default}}
    return deepcopy(value)


def form_document(text):
    try:
        raw = parse_yaml(text)
        if not isinstance(raw, dict):
            raise ValueError()
        data = merge(DEFAULTS, raw)
        for key in TEMPLATES:
            if not isinstance(data[key], list) or not all(isinstance(v, dict) for v in data[key]):
                raise ValueError()
            data[key] = [merge(TEMPLATES[key], v) for v in data[key]]
        return {'config': data, 'templates': TEMPLATES, 'labels': LABELS, 'help': HELP, 'options': OPTIONS}
    except (ValueError, TypeError, yaml.YAMLError):
        raise ValueError('Formular kann diese YAML nicht laden. Syntax und Struktur im YAML-Editor prüfen.') from None


def form_yaml(raw):
    # JSON round trip bounds input size and excludes non-JSON values before YAML.
    try:
        encoded = json.dumps(raw, allow_nan=False)
        if not isinstance(raw, dict) or len(encoded.encode()) > 256 * 1024:
            raise ValueError()
        return yaml.safe_dump(raw, allow_unicode=True, sort_keys=False)
    except (TypeError, ValueError, RecursionError):
        raise ValueError('Formulardaten ungültig oder zu groß.') from None
