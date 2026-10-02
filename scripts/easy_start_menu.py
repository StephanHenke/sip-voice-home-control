"""Environment-aware maintenance, embedded into the standalone installer."""
import json
import os
from pathlib import Path
import shutil
import socket
import time
import uuid

APP = Path('/opt/sip-voice-home')


def environment():
    if Path('/etc/pve').is_dir():
        return 'host'
    if (APP / 'compose.yaml').is_file() and (APP / 'voice-home-deploy.sh').is_file() and shutil.which('docker'):
        return 'lxc'
    raise ValueError('Weder Proxmox-Host noch bestehende Controller-Installation erkannt.')


def compose(*args):
    command = ['docker', 'compose', '--project-directory', str(APP), '--project-name', 'sip-voice-home',
               '-f', str(APP / 'compose.yaml')]
    if (APP / 'compose.web.yaml').is_file():
        command += ['-f', str(APP / 'compose.web.yaml')]
    return command + list(args)


def require_idle(run):
    state = json.loads(run(*compose('exec', '-T', 'controller', 'voice-home', 'status'), capture=True))
    if not state.get('fresh') or state.get('busy') or state.get('call_active') or state.get('accepting') is not False:
        raise ValueError('Annahme ausschalten und Gesprächsende abwarten; aktueller freier Status erforderlich.')


def check_web(run):
    # Check the local listener; SIP is deliberately unconfigured after reset.
    probe = "import os,socket; socket.create_connection(('127.0.0.1',int(os.getenv('VOICE_HOME_WEB_PORT','8443'))),2).close()"
    for _ in range(30):
        try:
            run(*compose('exec', '-T', 'controller', 'python', '-c', probe), capture=True)
            return
        except RuntimeError:
            time.sleep(1)
    raise RuntimeError('Weboberfläche nach Neustart nicht erreichbar.')


def reset_config(api):
    import fcntl
    if not (APP / 'compose.web.yaml').is_file():
        raise ValueError('Einstellungsreset benötigt die konfigurierte Weboberfläche.')
    with open('/run/lock/voice-home-deploy.lock', 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Eine andere Wartung läuft bereits.') from None
        require_idle(api.run)
        if api.ask('YAML sichern und Einstellungen zurücksetzen? RESET eingeben') != 'RESET':
            print('Abgebrochen.')
            return
        require_idle(api.run)
        config = APP / 'config/config.yaml'
        if config.is_symlink() or not config.is_file():
            raise ValueError('Reguläre config/config.yaml erforderlich.')
        old = config.read_bytes()
        previous = config.stat()
        backups = APP / 'backups'
        if backups.is_symlink():
            raise ValueError('Backup-Verzeichnis darf kein Symlink sein.')
        backups.mkdir(mode=0o700, exist_ok=True)
        backups.chmod(0o700)
        backup = backups / ('config-reset-' + uuid.uuid4().hex + '.yaml')
        with open(backup, 'xb') as file:
            os.chmod(backup, 0o600)
            file.write(old)
            file.flush()
            os.fsync(file.fileno())
        replacement = api.initial_config(api.example).encode('utf-8')
        temporary = config.with_name('.reset-' + uuid.uuid4().hex)
        def write_config(content, uid, gid, mode):
            with open(temporary, 'xb') as file:
                os.fchmod(file.fileno(), mode)
                os.fchown(file.fileno(), uid, gid)
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, config)
        api.run(*compose('stop', '-t', '30', 'controller'))
        try:
            write_config(replacement, 10001, 10001, 0o600)
            api.run(*compose('up', '-d', '--no-build', 'controller'))
            check_web(api.run)
        except Exception:
            temporary.unlink(missing_ok=True)
            api.run(*compose('stop', '-t', '30', 'controller'))
            write_config(old, previous.st_uid, previous.st_gid, previous.st_mode & 0o777)
            api.run(*compose('up', '-d', '--no-build', 'controller'))
            raise RuntimeError('Reset fehlgeschlagen; vorherige YAML wiederhergestellt. Betrieb prüfen.') from None
        finally:
            temporary.unlink(missing_ok=True)
        print(f'Einstellungen zurückgesetzt. Geschützte YAML-Sicherung: {backup}')
        print('Annahme und Aktionen gesperrt. Webpasswort, TLS und Secret-Dateien bleiben erhalten.')
        print('SIP bleibt bis zur Einrichtung ungesund; im Webeditor neu konfigurieren.')


def targets(api):
    records = json.loads(api.run('pvesh', 'get', '/cluster/resources', '--type', 'vm', '--output-format', 'json', capture=True))
    node = socket.gethostname().split('.')[0]
    result = []
    for record in records:
        if record.get('type') != 'lxc' or record.get('status') != 'running' or record.get('node') != node:
            continue
        ctid = str(record['vmid'])
        try:
            api.run('pct', 'exec', ctid, '--', 'test', '-x', str(APP / 'voice-home-deploy.sh'), capture=True)
        except RuntimeError:
            continue
        result.append(ctid)
    return result


def update(api, prefix, image):
    image = api.image_reference(image or api.ask('Ziel-Image (ohne Tag: latest)'))
    state = json.loads(api.run(*prefix, str(APP / 'voice-home-deploy.sh'), 'status', capture=True))
    if not state.get('fresh') or state.get('busy') or state.get('call_active') or state.get('accepting') is not False:
        raise ValueError('Update abgelehnt: Annahme ausschalten, Gesprächsende und aktuellen Status abwarten.')
    cid = api.run(*prefix, *compose('ps', '-q', 'controller'), capture=True)
    if cid:
        print('Aktuelles Image: ' + api.run(*prefix, 'docker', 'inspect', cid, '--format', '{{.Image}}', capture=True))
    print('Ziel: ' + image)
    if api.ask('Update starten? UPDATE eingeben') != 'UPDATE':
        print('Abgebrochen.')
        return
    api.run(*prefix, str(APP / 'voice-home-deploy.sh'), 'update', image)


def dispatch(args, api):
    place = environment()
    direct = 'update' if args.update is not None else 'status' if args.status is not None else None
    while True:
        if direct:
            action = direct
        else:
            print('\n1) ' + ('Neuen LXC installieren' if place == 'host' else 'Controller aktualisieren'))
            print('2) ' + ('Installation aktualisieren' if place == 'host' else 'Webpasswort zurücksetzen'))
            print('3) ' + ('Status anzeigen' if place == 'host' else 'Einstellungen zurücksetzen'))
            print('0) Beenden')
            choice = api.ask('Auswahl', '0')
            if choice == '0':
                return
            actions = {'1': 'install', '2': 'update', '3': 'status'} if place == 'host' else {'1': 'update', '2': 'password', '3': 'reset'}
            action = actions.get(choice)
            if action is None:
                print('Ungültige Auswahl.')
                continue
        try:
            if action == 'install':
                api.install()
            else:
                prefix = []
                if place == 'host':
                    supplied = args.update if action == 'update' else args.status
                    choices = targets(api)
                    ctid = supplied or api.select('Laufende lokale Controller-LXC', choices)
                    if ctid not in choices:
                        raise ValueError('Kein laufender lokaler Controller-LXC mit dieser ID gefunden.')
                    prefix = ['pct', 'exec', ctid, '--']
                elif args.update or args.status:
                    raise ValueError('Im LXC keine fremde LXC-ID angeben.')
                if action == 'status':
                    api.run(*prefix, str(APP / 'voice-home-deploy.sh'), 'status')
                elif action == 'update':
                    update(api, prefix, args.image)
                elif action == 'password':
                    if not (APP / 'compose.web.yaml').is_file():
                        raise ValueError('Weboberfläche ist nicht eingerichtet.')
                    api.run(*compose('run', '--rm', '--no-deps', 'controller', 'web-password'))
                elif action == 'reset':
                    reset_config(api)
        except (RuntimeError, ValueError) as error:
            if direct:
                raise
            print(str(error))
        if direct:
            return
