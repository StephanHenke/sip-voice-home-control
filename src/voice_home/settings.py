"""Validation for optional operational settings (without exposing values)."""
import math
from pathlib import Path
import re


class SettingsError(ValueError):
    """Safe, value-free configuration diagnostic."""


def credential_source(settings, name, base, required=False):
    direct, file = settings.get(name), settings.get(name + '_file')
    if direct and file:
        raise SettingsError(f'{name}: Wert und Secret-Datei gleichzeitig angegeben')
    if direct is not None and not isinstance(direct, str):
        raise SettingsError(f'{name}: String erforderlich')
    if file is not None and not isinstance(file, str):
        raise SettingsError(f'{name}_file: String erforderlich')
    if required and not (direct or file):
        raise SettingsError(f'{name}: Wert oder Secret-Datei erforderlich')
    if file:
        path = Path(file)
        settings[name + '_file'] = str(path if path.is_absolute() else base / path)


def operational_settings(raw):
    control = {'enabled': False, 'initial_accepting': True, 'heartbeat_interval_seconds': 10, **raw.get('call_control', {})}
    for key in ('enabled', 'initial_accepting'):
        if type(control[key]) is not bool:
            raise SettingsError(f'call_control.{key}: Boolean erforderlich')
    interval = control['heartbeat_interval_seconds']
    if type(interval) not in (int, float) or not math.isfinite(interval) or interval <= 0:
        raise SettingsError('Ungültiges Lebenszeichenintervall')
    if control['enabled']:
        items = [control.get(key) for key in ('switch_item', 'status_item', 'call_active_item', 'heartbeat_item')]
        if not all(isinstance(item, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', item) for item in items) or len(set(items)) != 4:
            raise SettingsError('Vier unterschiedliche gültige Steuerungs-Items erforderlich')
    smart = {'adapter': 'openhab', 'notification_item': '', **raw.get('smarthome', {})}
    if smart['adapter'] != 'openhab':
        raise SettingsError('Unbekannter Smart-Home-Adapter')
    notification = smart['notification_item']
    if not isinstance(notification, str) or (notification and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', notification)):
        raise SettingsError('smarthome.notification_item: gültiger Itemname erforderlich')
    reserved = [control.get(k) for k in ('switch_item', 'status_item', 'call_active_item', 'heartbeat_item')]
    reserved += [a.get(k) for a in raw.get('actions', []) for k in ('command_item', 'feedback_item')]
    if notification and notification in reserved:
        raise SettingsError('Benachrichtigungs-Item muss von Steuerungs- und Geräte-Items verschieden sein')
    logs = {'level': 'INFO', 'target': 'console', 'max_bytes': 10 * 1024 * 1024, 'backup_count': 2,
            'port': 514, 'transport': 'udp', 'facility': 'local0', 'queue_size': 1000, **raw.get('logging', {})}
    if logs['level'] not in {'OFF', 'ERROR', 'WARNING', 'INFO', 'DEBUG'} or logs['target'] not in {'none', 'console', 'file', 'syslog'}:
        raise SettingsError('Ungültiger Log-Level oder Log-Ziel')
    for key, minimum in (('max_bytes', 1), ('backup_count', 1), ('queue_size', 1), ('port', 1)):
        if type(logs[key]) is not int or logs[key] < minimum:
            raise SettingsError(f'logging.{key}: positive ganze Zahl erforderlich')
    if logs['port'] > 65535 or logs['transport'] not in {'udp', 'tcp'} or logs['facility'] not in {f'local{i}' for i in range(8)}:
        raise SettingsError('Ungültige Syslog-Einstellungen')
    if logs['target'] == 'file' and (not isinstance(logs.get('path'), str) or not Path(logs['path']).is_absolute()):
        raise SettingsError('Absoluter Log-Dateipfad erforderlich')
    if logs['target'] == 'syslog' and (not isinstance(logs.get('host'), str) or not logs['host'].strip()):
        raise SettingsError('Syslog-Host erforderlich')
    return control, smart, logs
