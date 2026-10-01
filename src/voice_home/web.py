"""Small TLS-only administration server. No Docker socket, no shell commands."""
from collections import OrderedDict, deque
import getpass
import hashlib
import hmac
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import signal
import ssl
import subprocess
import sys
import threading
import time

import yaml

from .config import load, credential
from .runtime import read_status

LIMIT = 256 * 1024
AUTH = Path('/web/password.json')


def atomic(path, content):
    path = Path(path)
    temporary = path.with_name('.' + path.name + '.' + secrets.token_hex(8))
    try:
        with temporary.open('x', encoding='utf-8') as f:
            temporary.chmod(0o600)
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def reset_password(path=AUTH):
    password = getpass.getpass('Neues Admin-Passwort (mindestens 12 Zeichen): ')
    if len(password) < 12 or password != getpass.getpass('Wiederholen: '):
        raise ValueError('Passwörter stimmen nicht überein oder sind zu kurz')
    salt = secrets.token_hex(16)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic(path, json.dumps({'salt': salt, 'hash': password_hash(password, salt)}))
    print('Admin-Passwort gesetzt. Bestehende Sitzungen sind ungültig.')


class Store:
    def __init__(self, config):
        self.path = Path(config).resolve()
        self.versions = self.path.parent / '.versions'
        self.versions.mkdir(mode=0o700, exist_ok=True)
        self.lock = threading.RLock()

    def read(self):
        text = self.path.read_text(encoding='utf-8')
        return {'yaml': text, 'revision': hashlib.sha256(text.encode()).hexdigest()}

    def validate(self, text):
        if not isinstance(text, str) or len(text.encode()) > LIMIT:
            raise ValueError('YAML ist zu groß (maximal 256 KiB).')
        # Same directory preserves relative secret paths. Never expose YAML values
        # or exception snippets (which could contain secrets) in diagnostics.
        test = self.path.parent / ('.validate-' + secrets.token_hex(8))
        try:
            atomic(test, text)
            cfg = load(test)
            credential(cfg.sip, 'password')
            credential(cfg.openhab, 'token')
        except yaml.YAMLError as e:
            mark = getattr(e, 'problem_mark', None)
            where = f' bei Zeile {mark.line + 1}, Spalte {mark.column + 1}' if mark else ''
            raise ValueError('YAML-Syntaxfehler' + where) from None
        except Exception:
            raise ValueError('Konfiguration ungültig oder Secret-Datei nicht lesbar. Konfigurationsreferenz prüfen.') from None
        finally:
            test.unlink(missing_ok=True)

    def save(self, text, revision):
        with self.lock:
            current = self.read()
            if not hmac.compare_digest(current['revision'], str(revision)):
                raise ValueError('Konfiguration wurde zwischenzeitlich geändert. Zuerst neu laden.')
            self.validate(text)
            if text != current['yaml']:
                name = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + secrets.token_hex(4) + '.yaml'
                atomic(self.versions / name, current['yaml'])
                atomic(self.path, text)
                for old in sorted(self.versions.glob('*.yaml'))[:-20]:
                    old.unlink()
            return self.read()


class Admin:
    def __init__(self, config, auth=AUTH):
        self.store, self.auth = Store(config), auth
        self.sessions = OrderedDict()
        self.attempts = OrderedDict()
        self.lock = threading.RLock()
        self.restart = threading.Event()
        self.child = None
        self.applied = self.store.read()['revision']

    def fingerprint(self):
        try:
            return hashlib.sha256(self.auth.read_bytes()).hexdigest()
        except OSError:
            return ''

    def login(self, password, ip):
        with self.lock:
            now = time.monotonic()
            attempts = self.attempts.setdefault(ip, deque(maxlen=5))
            while attempts and now - attempts[0] > 60:
                attempts.popleft()
            if len(attempts) >= 5:
                return None
            attempts.append(now)
            while len(self.attempts) > 128:
                self.attempts.popitem(last=False)
            try:
                raw = self.auth.read_bytes()
                data = json.loads(raw)
                valid = hmac.compare_digest(password_hash(password, data['salt']), data['hash'])
            except (OSError, ValueError, KeyError, TypeError):
                valid = False
            if not valid:
                return None
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            self.sessions[token] = (now + 3600, hashlib.sha256(raw).hexdigest(), csrf)
            while len(self.sessions) > 32:
                self.sessions.popitem(last=False)
            return token, csrf

    def session(self, token):
        with self.lock:
            data = self.sessions.get(token)
            if data and data[0] > time.monotonic() and data[1] == self.fingerprint():
                return data
            self.sessions.pop(token, None)
            return None

    def can_restart(self):
        if self.child is not None and self.child.poll() is not None:
            return True  # Repair configuration after a child startup failure.
        state = read_status()
        return state.get('fresh') and state.get('accepting') is False and not state.get('busy') and not state.get('call_active')


def handler(admin):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # No request/body/password logging.

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def respond(self, code, data, content='application/json', cookie=None):
            payload = json.dumps(data).encode() if content == 'application/json' else data.encode()
            self.send_response(code)
            self.send_header('Content-Type', content + '; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if cookie:
                self.send_header('Set-Cookie', cookie)
            if content == 'application/yaml':
                self.send_header('Content-Disposition', 'attachment; filename="config.yaml"')
            self.end_headers()
            self.wfile.write(payload)

        def token(self):
            try:
                cookies = SimpleCookie(self.headers.get('Cookie', ''))
                return cookies['session'].value if 'session' in cookies else ''
            except Exception:
                return ''

        def do_GET(self):
            if self.path in ('/', '/app.js', '/style.css'):
                file, mime = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}[self.path]
                return self.respond(200, (Path(__file__).parent / 'web_static' / file).read_text(encoding='utf-8'), mime)
            session = admin.session(self.token())
            if not session:
                return self.respond(401, {'error': 'Bitte anmelden.'})
            if self.path == '/api/session':
                return self.respond(200, {'csrf': session[2]})
            if self.path == '/api/config':
                return self.respond(200, admin.store.read())
            if self.path == '/api/status':
                return self.respond(200, {**read_status(), 'pending_changes': admin.store.read()['revision'] != admin.applied})
            if self.path == '/api/logs':
                try:
                    text = Path('/tmp/voice-home/web.log').read_text(encoding='utf-8')[-32000:]
                except OSError:
                    text = ''
                return self.respond(200, {'text': text or 'Keine Logeinträge. Bei OFF/none bleibt die Loganzeige leer.'})
            if self.path == '/api/versions':
                return self.respond(200, {'versions': sorted((p.name for p in admin.store.versions.glob('*.yaml')), reverse=True)})
            if self.path == '/api/download':
                return self.respond(200, admin.store.read()['yaml'], 'application/yaml')
            match = re.fullmatch(r'/api/versions/(\d{8}T\d{6}Z-[a-f0-9]{8}\.yaml)', self.path)
            if match:
                p = admin.store.versions / match[1]
                if p.is_file():
                    return self.respond(200, p.read_text(encoding='utf-8'), 'application/yaml')
            self.respond(404, {'error': 'Nicht gefunden.'})

        def do_POST(self):
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= LIMIT * 2 or self.headers.get('Content-Type') != 'application/json':
                    return self.respond(400, {'error': 'JSON-Anfrage fehlt oder ist zu groß.'})
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError('Ungültige Anfrage.')
                if self.path == '/api/login':
                    password = data.get('password', '')
                    if not isinstance(password, str) or len(password) > 1024:
                        raise ValueError('Ungültige Anmeldung.')
                    result = admin.login(password, self.client_address[0])
                    if not result:
                        return self.respond(401, {'error': 'Anmeldung fehlgeschlagen. Nach fünf Versuchen eine Minute warten.'})
                    token, csrf = result
                    return self.respond(200, {'csrf': csrf}, cookie=f'session={token}; Secure; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600')
                token = self.token()
                session = admin.session(token)
                if not session or not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), session[2]):
                    return self.respond(403, {'error': 'Sitzung ungültig. Neu anmelden.'})
                if self.path == '/api/logout':
                    with admin.lock:
                        admin.sessions.pop(token, None)
                    return self.respond(200, {}, cookie='session=; Secure; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
                if self.path == '/api/validate':
                    admin.store.validate(data.get('yaml'))
                    return self.respond(200, {'message': 'YAML und Konfiguration gültig.'})
                if self.path == '/api/save':
                    result = admin.store.save(data.get('yaml'), data.get('revision'))
                    return self.respond(200, {'revision': result['revision'], 'message': 'Gespeichert. Zum Anwenden neu starten.'})
                if self.path == '/api/restart':
                    with admin.store.lock:
                        admin.store.validate(admin.store.read()['yaml'])
                        if not admin.can_restart():
                            return self.respond(409, {'error': 'Zuerst Anrufannahme in openHAB ausschalten und Gesprächsende abwarten. Frischer Status erforderlich.'})
                        self.respond(200, {'message': 'Neustart angefordert. Gleich erneut anmelden.'})
                        admin.restart.set()
                        return
                self.respond(404, {'error': 'Nicht gefunden.'})
            except ValueError as e:
                message = str(e) if type(e) is ValueError else 'Ungültiges JSON.'
                self.respond(400, {'error': message})
            except Exception:
                self.respond(500, {'error': 'Anfrage fehlgeschlagen. Dateirechte und Speicher prüfen.'})
    return Handler


def serve(config):
    admin = Admin(config)
    class BoundedServer(ThreadingHTTPServer):
        slots = threading.BoundedSemaphore(16)

        def process_request(self, request, address):
            if not self.slots.acquire(blocking=False):
                request.close()
                return
            try:
                super().process_request(request, address)
            except Exception:
                self.slots.release()
                raise

        def process_request_thread(self, request, address):
            try:
                super().process_request_thread(request, address)
            finally:
                self.slots.release()

    server = BoundedServer((os.getenv('VOICE_HOME_WEB_BIND', '0.0.0.0'), int(os.getenv('VOICE_HOME_WEB_PORT', '8443'))), handler(admin))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain('/web/tls.crt', '/web/tls.key')
    server.socket = context.wrap_socket(server.socket, server_side=True, do_handshake_on_connect=False)
    stopped = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopped.set())
    # Config may be invalid after manual edits: keep editor available for repairs.
    child = subprocess.Popen([sys.executable, '-m', 'voice_home.cli', '--config', str(config), 'serve'], env={**os.environ, 'VOICE_HOME_WEB_LOG': '1'})
    admin.child = child
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        while not stopped.wait(.2):
            if admin.restart.is_set():
                if admin.can_restart() or child.poll() is not None:
                    break
                admin.restart.clear()
    finally:
        server.shutdown()
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=20)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        server.server_close()
    # Docker restart: unless-stopped restarts PID 1. No socket access needed.
