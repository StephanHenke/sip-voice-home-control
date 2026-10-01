#!/usr/bin/env python3
"""Interactive Proxmox bootstrap. Standard library only; run on the PVE host."""
import argparse
import base64
import getpass
import ipaddress
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import warnings

FILES = ['config.example.yaml', 'deploy/lxc/provision-lxc.sh',
         'deploy/lxc/compose.yaml', 'deploy/lxc/compose.web.yaml',
         'deploy/lxc/voice-home-deploy.sh']
APP = '/opt/sip-voice-home'


def run(*args, capture=False, data=None):
    result = subprocess.run(list(args), input=data, text=True,
                            stdout=subprocess.PIPE if capture else None, check=False)
    if result.returncode:
        # Do not include arguments, stdin, or credentials in exception output.
        raise RuntimeError(f'{args[0]} fehlgeschlagen (Exitcode {result.returncode}).')
    return result.stdout.strip() if capture else None


def ask(label, default=None):
    suffix = f' [{default}]' if default is not None else ''
    value = input(label + suffix + ': ').strip() or default
    if not value:
        raise ValueError('Eine erforderliche Eingabe fehlt.')
    return str(value)


def secret(label):
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        value = getpass.getpass(label + ': ')
    if not value:
        raise ValueError('Ein nichtleeres Geheimnis ist erforderlich.')
    return value


def select(label, choices):
    if not choices:
        raise ValueError(f'Keine Auswahl verfügbar: {label}')
    print('\n' + label)
    for index, choice in enumerate(choices, 1):
        print(f'  {index}: {choice}')
    index = int(ask('Auswahl', '1'))
    if not 1 <= index <= len(choices):
        raise ValueError('Ungültige Auswahl.')
    return choices[index - 1]


def api(path, token=''):
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'voice-home-installer'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request('https://api.github.com/' + path, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def download_sources(directory, repository, ref):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Repository als OWNER/NAME angeben.')
    endpoint = f'repos/{repository}/commits/{urllib.parse.quote(ref, safe="")}'
    token = ''
    try:
        commit = api(endpoint)
    except urllib.error.HTTPError as error:
        if error.code not in (401, 403, 404):
            raise RuntimeError('GitHub-Quellstand nicht abrufbar.') from None
        print('Repository nicht öffentlich erreichbar. Token mit Lesezugriff angeben.')
        token = secret('GitHub-Token (nur im RAM)')
        commit = api(endpoint, token)
    sha = commit['sha']
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Ungültiger GitHub-Quellstand.')
    for filename in FILES:
        item = api(f'repos/{repository}/contents/{filename}?ref={sha}', token)
        if item.get('encoding') != 'base64' or item.get('type') != 'file':
            raise ValueError('Ungültige Installationsdatei.')
        target = directory / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(item['content']))
    print('Installationsdateien geladen, Commit:', sha)


def storage(node, content):
    records = json.loads(run('pvesh', 'get', f'/nodes/{node}/storage',
                             '--content', content, '--enabled', '1',
                             '--output-format', 'json', capture=True))
    return sorted(r['storage'] for r in records if r.get('active'))


def initial_config(source):
    # Keep the annotated example for editing. Deliberately invalid SIP credentials
    # stop the SIP child; the independently authenticated web editor remains usable.
    if source.count('password: "CHANGE_ME"') != 1 or source.count('initial_accepting: true') != 1:
        raise ValueError('Unbekannte Konfigurationsvorlage; Installation abgebrochen.')
    return source.replace('password: "CHANGE_ME"', 'password: ""').replace(
        'initial_accepting: true', 'initial_accepting: false')


def registry_host(image):
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._/:@-]+', image):
        raise ValueError('Ungültige Image-Referenz.')
    first = image.split('/')[0]
    return first if '/' in image and ('.' in first or ':' in first or first == 'localhost') else 'docker.io'


def install_app(ctid, directory, image):
    def ct(*args, **kwargs):
        return run('pct', 'exec', ctid, '--', *args, **kwargs)
    files = {'deploy/lxc/compose.yaml': 'compose.yaml',
             'deploy/lxc/compose.web.yaml': 'compose.web.yaml',
             'deploy/lxc/voice-home-deploy.sh': 'voice-home-deploy.sh',
             'config.initial.yaml': 'config/config.yaml'}
    (directory / 'config.initial.yaml').write_text(initial_config(
        (directory / 'config.example.yaml').read_text(encoding='utf-8')), encoding='utf-8')
    for source, target in files.items():
        run('pct', 'push', ctid, str(directory / source), APP + '/' + target, '--perms', '0600')
    ct('chown', '10001:10001', APP + '/config/config.yaml')
    ct('chmod', '0700', APP + '/voice-home-deploy.sh')
    addresses = json.loads(ct('ip', '-j', '-4', 'addr', 'show', 'dev', 'eth0', 'scope', 'global', capture=True))
    candidates = [str(ipaddress.IPv4Address(a['local'])) for interface in addresses
                  for a in interface.get('addr_info', []) if a.get('family') == 'inet']
    if not candidates:
        raise RuntimeError('Keine DHCP-Adresse auf eth0. LXC-Netzwerk prüfen.')
    address = candidates[0]
    ct('openssl', 'req', '-x509', '-newkey', 'rsa:3072', '-nodes', '-days', '365',
       '-keyout', APP + '/web/tls.key', '-out', APP + '/web/tls.crt',
       '-subj', '/CN=sip-voice-home', '-addext', 'subjectAltName=IP:' + address)
    ct('chown', '10001:10001', APP + '/web/tls.key', APP + '/web/tls.crt')
    ct('chmod', '0600', APP + '/web/tls.key')
    registry = registry_host(image)
    try:
        ct('docker', 'pull', image)
    except RuntimeError:
        print('Image-Pull fehlgeschlagen. Bei privatem Image anmelden; sonst mit Strg+C abbrechen.')
        username = ask('Registry-Benutzer')
        token = secret('Registry-Token (Docker speichert den Login im LXC)')
        ct('docker', 'login', registry, '--username', username, '--password-stdin', data=token + '\n')
        del token
        ct('docker', 'pull', image)
    # Use the exact pulled image for initial deployment.
    pinned = ct('docker', 'image', 'inspect', image, '--format', '{{.Id}}', capture=True)
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', pinned):
        raise ValueError('Ungültige Image-ID.')
    ct('python3', '-c', 'from pathlib import Path; import sys; Path(sys.argv[1]).write_text(sys.stdin.read())',
       APP + '/.env', data='VOICE_HOME_IMAGE=' + pinned + '\n')
    compose = ('docker', 'compose', '--project-directory', APP, '--project-name', 'sip-voice-home',
               '-f', APP + '/compose.yaml', '-f', APP + '/compose.web.yaml')
    ct(*compose, 'up', '-d', '--no-build')
    ct('python3', '-c', '''
import ssl, sys, time, urllib.request, urllib.error
context = ssl.create_default_context(cafile='/opt/sip-voice-home/web/tls.crt')
for attempt in range(60):
    try:
        urllib.request.urlopen('https://' + sys.argv[1] + ':8443/api/session', context=context, timeout=2)
    except urllib.error.HTTPError as error:
        if error.code == 401:
            sys.exit(0)
    except (OSError, urllib.error.URLError):
        pass
    time.sleep(1)
sys.exit('Weboberfläche nicht bereit; Containerzustand prüfen.')
''', address)
    print('\nWeboberfläche bereit: https://' + address + ':8443')
    ct('openssl', 'x509', '-in', APP + '/web/tls.crt', '-noout', '-fingerprint', '-sha256')
    print('SIP noch NICHT eingerichtet; Docker unhealthy ist bis zur Konfiguration zu erwarten.')
    print('Mit dem gewählten Webpasswort anmelden, SIP/openHAB eintragen, validieren und neu laden.')
    print('Anrufer und Aktionen sind nicht freigegeben. Erst nach eigener Abnahme aktivieren.')
    print('Updates im LXC: cd ' + APP + ' && ./voice-home-deploy.sh update ' + image)


def main():
    parser = argparse.ArgumentParser(description='Geführte Erstinstallation auf einem Proxmox-Host')
    parser.add_argument('--repository', help='GitHub OWNER/NAME; keine Zugangsdaten in die URL')
    parser.add_argument('--ref', default='main', help='Quell-Commit/Tag/Branch, Standard main')
    parser.add_argument('--source-dir', type=Path, help='Alternativ vorhandenes Repository-Verzeichnis')
    args = parser.parse_args()
    if platform.system() != 'Linux' or os.geteuid() != 0 or not Path('/etc/pve').is_dir():
        raise RuntimeError('Als root direkt auf dem Proxmox-Host ausführen.')
    if platform.machine() != 'x86_64' or not sys.stdin.isatty():
        raise RuntimeError('Interaktive amd64-Proxmox-Konsole erforderlich.')
    for tool in ('pct', 'pvesh', 'pveam', 'bash', 'python3'):
        if not shutil.which(tool):
            raise RuntimeError('Erforderliches Programm fehlt: ' + tool)
    repository = args.repository
    if not args.source_dir and not repository:
        repository = ask('GitHub-Repository (OWNER/sip-voice-home-control)')
    with tempfile.TemporaryDirectory(prefix='voice-home-install-') as temporary:
        directory = Path(temporary)
        if args.source_dir:
            for filename in FILES:
                target = directory / filename
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(args.source_dir / filename, target)
        else:
            download_sources(directory, repository, args.ref)
        node = socket.gethostname().split('.')[0]
        next_id = json.loads(run('pvesh', 'get', '/cluster/nextid', '--output-format', 'json', capture=True))
        ctid = ask('Neue LXC-ID', str(next_id))
        if not re.fullmatch(r'[1-9][0-9]{2,8}', ctid):
            raise ValueError('Ungültige LXC-ID.')
        resources = json.loads(run('pvesh', 'get', '/cluster/resources', '--type', 'vm',
                                  '--output-format', 'json', capture=True))
        if any(str(r['vmid']) == ctid for r in resources):
            raise ValueError('Diese ID ist bereits belegt. Es wird nichts überschrieben.')
        rootfs = select('Storage für LXC-Festplatte', storage(node, 'rootdir'))
        templates = select('Storage für Debian-Vorlage', storage(node, 'vztmpl'))
        networks = json.loads(run('pvesh', 'get', f'/nodes/{node}/network', '--type', 'bridge',
                                 '--output-format', 'json', capture=True))
        bridge = select('Netzwerkbrücke (DHCP erforderlich)', sorted(n['iface'] for n in networks if n.get('active')))
        run('pveam', 'update')
        available = run('pveam', 'available', '--section', 'system', capture=True)
        choices = sorted(set(re.findall(r'debian-(?:12|13)-standard_[A-Za-z0-9_.-]+_amd64\.tar\.(?:zst|xz|gz)', available)), reverse=True)
        template = select('Debian-Vorlage', choices)
        default_image = f'ghcr.io/{repository.lower()}:latest' if repository else None
        image = ask('Container-Image', default_image)
        registry_host(image)
        print(f'\nAnlegen: LXC {ctid}, 2 CPUs, 3 GiB RAM, 12 GiB Disk, {rootfs}, {bridge}, DHCP.')
        print('Unprivilegiert mit Docker-Nesting; bestehende Container bleiben unverändert.')
        if ask('Zum Anlegen INSTALL eingeben') != 'INSTALL':
            raise ValueError('Installation abgebrochen.')
        run('pveam', 'download', templates, template)
        try:
            run('bash', str(directory / 'deploy/lxc/provision-lxc.sh'), ctid,
                templates + ':vztmpl/' + template, rootfs, bridge)
            install_app(ctid, directory, image)
        except (RuntimeError, ValueError, KeyboardInterrupt, EOFError):
            print(f'Installation nicht abgeschlossen. LXC {ctid} ggf. prüfen; er wird nicht automatisch gelöscht.', file=sys.stderr)
            raise


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, KeyError, OSError, EOFError, KeyboardInterrupt, getpass.GetPassWarning) as error:
        # HTTP exceptions and command failures must not expose response bodies/tokens.
        print('Installation abgebrochen.' if not isinstance(error, (RuntimeError, ValueError)) else str(error), file=sys.stderr)
        sys.exit(1)
