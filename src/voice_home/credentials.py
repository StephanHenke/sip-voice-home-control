"""Authenticated encryption for inline credentials; no plaintext temp files."""
import json
import os
from pathlib import Path
import secrets

import yaml
from cryptography.fernet import Fernet, InvalidToken

from .settings import SettingsError

PREFIX = 'enc:v1:'
FIELDS = {'sip': 'password', 'openhab': 'token'}


class ConfigLoader(yaml.SafeLoader):
    pass


def mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str) or key in result:
            raise SettingsError('YAML: doppelte oder nicht-textuelle Schlüssel nicht erlaubt')
        result[key] = loader.construct_object(value_node, deep=True)
    return result


ConfigLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)


def parse_yaml(text):
    if not isinstance(text, str) or len(text.encode()) > 256 * 1024:
        raise SettingsError('YAML: maximal 256 KiB erlaubt')
    if any(isinstance(event, yaml.AliasEvent) for event in yaml.parse(text)):
        raise SettingsError('YAML-Aliase werden nicht unterstützt; Werte direkt eintragen')
    return yaml.load(text, Loader=ConfigLoader)


def web_settings(raw):
    web = {'enabled': True, 'bind': '0.0.0.0', 'port': 8443, **raw.get('web', {})}
    if set(web) != {'enabled', 'bind', 'port'} or type(web['enabled']) is not bool:
        raise SettingsError('web: enabled als Boolean, bind und port erlaubt')
    import ipaddress
    try:
        ipaddress.IPv4Address(web['bind'])
    except (ValueError, TypeError):
        raise SettingsError('web.bind: IPv4-Adresse erforderlich') from None
    if type(web['port']) is not int or not 1024 <= web['port'] <= 65535:
        raise SettingsError('web.port: Port zwischen 1024 und 65535 erforderlich')
    return web


def key_file(config):
    return Path(os.environ.get('VOICE_HOME_SECRETS_KEY_FILE') or (Path(config).resolve().parent / '.secrets.key'))


def cipher(config, create=False):
    path = key_file(config)
    try:
        if path.is_symlink():
            raise OSError()
        if create and not path.exists():
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(fd, 'wb') as out:
                    out.write(Fernet.generate_key())
                    out.flush()
                    os.fsync(out.fileno())
        if os.name != 'nt' and path.stat().st_mode & 0o077:
            raise OSError()
        return Fernet(path.read_bytes().strip())
    except (OSError, ValueError):
        raise SettingsError('Secret-Schlüssel fehlt, ist ungültig oder nicht privat lesbar (0600). Schlüssel und Mount prüfen.') from None


def decrypt_inline(settings, name, config):
    value = settings.get(name)
    if isinstance(value, str) and value.startswith(PREFIX):
        try:
            settings[name] = cipher(config).decrypt(value[len(PREFIX):].encode()).decode()
        except (InvalidToken, UnicodeError, ValueError):
            raise SettingsError('Zugangsdaten können mit diesem Schlüssel nicht entschlüsselt werden.') from None


def encrypt_text(text, config):
    raw = parse_yaml(text)
    if not isinstance(raw, dict):
        raise SettingsError('Konfiguration muss ein YAML-Objekt sein')
    # Validate existing tokens before generating any new key.
    for section, name in FIELDS.items():
        values = raw.get(section, {})
        if not isinstance(values, dict):
            raise SettingsError('Zugangsbereich muss ein YAML-Objekt sein')
        decrypt_inline(dict(values), name, config)
    edits = []
    tree = yaml.compose(text)
    for section_node, values in tree.value:
        name = FIELDS.get(section_node.value)
        if not name or not isinstance(values, yaml.MappingNode):
            continue
        for key, value in values.value:
            if key.value != name:
                continue
            plain = raw[section_node.value].get(name)
            if not isinstance(plain, str) or not plain or plain.startswith(PREFIX):
                continue
            encrypted = PREFIX + cipher(config, create=True).encrypt(plain.encode()).decode()
            replacement = json.dumps(encrypted)
            if text[value.start_mark.index:value.end_mark.index].endswith('\n'):
                replacement += '\n'
            edits.append((value.start_mark.index, value.end_mark.index, replacement))
    for start, end, value in sorted(edits, reverse=True):
        text = text[:start] + value + text[end:]
    return text


def atomic_private(path, text):
    path = Path(path)
    if path.is_symlink():
        raise SettingsError('Konfigurationsdatei darf kein Symlink sein')
    temporary = path.with_name('.' + path.name + '.' + secrets.token_hex(8))
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def protect_file(path, config=None):
    path = Path(path)
    current = path.read_text(encoding='utf-8')
    protected = encrypt_text(current, config or path)
    if protected != current:
        atomic_private(path, protected)


def protect_config(path):
    protect_file(path)
    for version in (Path(path).resolve().parent / '.versions').glob('*.yaml'):
        protect_file(version, path)
