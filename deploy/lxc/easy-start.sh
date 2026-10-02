#!/usr/bin/env bash
# Generated easy-start.sh embeds the Python installer below this header.
set +x
set -Eeuo pipefail
umask 077

if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
  cat <<'HELP'
Usage: bash easy-start.sh [--image namespace/image:latest] [--repository OWNER/NAME]
Run interactively as root on an amd64 Proxmox host.
Installs missing Python 3 via APT, then runs the embedded guided installer.
Requires a web password before creating the LXC. Existing containers are preserved.
Additional arguments are forwarded to the embedded Python installer.
HELP
  exit 0
fi

[[ $EUID -eq 0 && -d /etc/pve ]] || { echo 'Als root auf dem Proxmox-Host ausführen.' >&2; exit 1; }
[[ $(uname -m) == x86_64 && -t 0 && -t 1 ]] || { echo 'Interaktive amd64-Proxmox-Konsole erforderlich. Nicht in bash pipen.' >&2; exit 1; }
for tool in pct pvesh pveam; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Erforderliches Programm fehlt: $tool" >&2; exit 1; }
done

ensure_python() {
  if ! command -v python3 >/dev/null 2>&1; then
    echo 'Python 3 fehlt und wird aus den vorhandenen APT-Paketquellen installiert.'
    apt-get update || return $?
    apt-get install -y --no-install-recommends python3 || return $?
  fi
}
ensure_python

installer=$(mktemp /tmp/voice-home-installer.XXXXXXXX.py)
trap 'rm -f -- "$installer"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

cat >"$installer" <<'VOICE_HOME_EMBEDDED_PYTHON'
#!/usr/bin/env python3
"""Interactive Proxmox bootstrap. Standard library only; run on the PVE host."""
import argparse
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
import warnings

# BEGIN BUNDLED FILES
BUNDLED_FILES = {
    'config.example.yaml': r'''# Nur Beispielwerte: Dokumentations-IP und Zugangsdaten vor dem Start ersetzen.
region: DE
data_dir: /data

sip:
  host: 192.0.2.1
  username: voice-controller
  password: "CHANGE_ME"
  # Alternative (remove password above): password_file: /run/secrets/sip_password
  port: 5060
  local_port: 5062
  transport: udp  # Alternativ tcp, z. B. bei Docker Desktop/NAT
  rtp_port: 40000
  # controller_number: "+49..."   # Eigene externe Nummer, niemals Rückrufziel
  # public_address: 192.0.2.20 # Nur falls die automatisch gewählte IP falsch ist

# Keine Freigabe ab Werk. Nummern ohne Platzhalter vollständig eintragen.
callers: []
#  - number: "+49..."
#    name: "Testperson"
#    access_mode: callback  # Standard; direct ist ausdrücklich konfigurierbar

dialog:
  answer_delay_ms: 1000
  listen_timeout_seconds: 15  # Zeit bis zum Beginn einer Antwort, nach dem Signalton
  max_utterance_seconds: 15   # Eigene Frist ab erkanntem Sprechbeginn
  max_failures: 2
  max_call_seconds: 120

callback:
  trigger_mode: reject  # answer_hangup: kurz annehmen und vor dem Rückruf auflegen
  delay_ms: 3000
  ring_timeout_seconds: 30
  cooldown_seconds: 60
  max_attempts_per_number_per_hour: 5

openhab:
  base_url: http://openhab:8080
  token: ""
  # Alternative: token_file: /run/secrets/openhab_token

speech:
  command_vocabulary: true
  asr_model: /models/vosk-model-small-de-0.15
  tts_model: /models/de_DE-thorsten-medium.onnx
  min_confidence: 0.85
  end_silence_ms: 700

actions:
  - id: front_door_open
    enabled: false
    aliases: ["Haustür", "Tür"]
    patterns:
      - "öffne {target}"
      - "öffne die {target}"
      - "{target} öffnen"
      - "die {target} öffnen"
      - "schließe {target} auf"
      - "schließe die {target} auf"
      - "{target} aufschließen"
      - "die {target} aufschließen"
      - "mach {target} auf"
      - "mach die {target} auf"
    # Beispiel für eine Integration mit Aktion 3=Falle öffnen, Status 5=unlatched.
    # An die eigene Installation anpassen und echte Geräterückmeldung prüfen!
    command_item: FrontDoor_Action
    command: "3"
    feedback_item: FrontDoor_State
    success_values: ["5"]
    failure_values: ["254"]
    timeout_seconds: 10
    success_text: "OK, die Haustür ist freigegeben."
    require_confirmation: false  # true: erst nach explizitem Ja ausführen
    confirmation_text: "Soll ich die Haustür entriegeln und die Falle ziehen?"

  - id: garage_open
    enabled: false
    aliases: ["Garagentor", "Garage"]
    patterns:
      - "öffne {target}"
      - "öffne das {target}"
      - "öffne die {target}"
      - "{target} öffnen"
      - "das {target} öffnen"
      - "die {target} öffnen"
      - "mach {target} auf"
      - "mach das {target} auf"
      - "mach die {target} auf"
    command_item: GarageDoor
    command: UP
    feedback_item: GarageDoor_ActualState
    feedback_mode: state
    # Beispielwerte des Geräts; passend zur eigenen Installation ersetzen.
    state_values:
      closed: ["1"]
      opening: ["3"]
      open: ["2"]
    success_states: [opening, open]  # Nur [open]: erst ganz offen bestätigen
    failure_states: []
    # Ein einziges Item: feedback_item = command_item, mit autoupdate=false
    # und tatsächlichen Geräteupdates. Prozentwerte stattdessen so auswerten:
    # feedback_mode: rollershutter_opening
    # state_values: {}
    # success_states: []
    # open_position: 0    # Invertiert: 100
    # closed_position: 100 # Invertiert: 0
    timeout_seconds: 10
    success_text: "OK, das Garagentor öffnet sich."
    require_confirmation: false
    confirmation_text: "Soll ich das Garagentor öffnen?"

  - id: garage_close
    enabled: false
    aliases: ["Garagentor", "Garage"]
    patterns:
      - "schließe {target}"
      - "schließe das {target}"
      - "schließe die {target}"
      - "{target} schließen"
      - "das {target} schließen"
      - "die {target} schließen"
      - "mach {target} zu"
      - "mach das {target} zu"
      - "mach die {target} zu"
    command_item: GarageDoor
    command: DOWN
    feedback_item: GarageDoor_ActualState
    feedback_mode: state
    # Beispielwerte: an die tatsächliche Geräterückmeldung anpassen.
    state_values:
      closed: ["1"]
      opening: ["3"]
      open: ["2"]
    success_states: [closed]  # Bestätigt die Endlage, nicht nur die Bewegung.
    failure_states: []
    timeout_seconds: 45       # Muss die vollständige Fahrzeit abdecken.
    success_text: "OK, das Garagentor ist geschlossen."
    require_confirmation: false
    confirmation_text: "Soll ich das Garagentor schließen?"

# Optional controller control/status integration (item names are configurable).
smarthome:
  adapter: openhab
call_control:
  enabled: false
  initial_accepting: true
  switch_item: VoiceController_AcceptCalls
  status_item: VoiceController_Status
  call_active_item: VoiceController_CallActive
  heartbeat_item: VoiceController_Heartbeat
  heartbeat_interval_seconds: 10
logging:
  level: INFO  # OFF, ERROR, WARNING, INFO, DEBUG
  target: console  # none, console, file, syslog
  # file: absolute path; /tmp/voice-home/controller.log stays in RAM
  # path: /tmp/voice-home/controller.log
  # max_bytes: 10485760
  # backup_count: 2
  # syslog:
  # host: syslog.example.lan
  # port: 514
  # transport: udp  # udp or tcp
  # facility: local0
  # queue_size: 1000
''',
    'deploy/lxc/provision-lxc.sh': r'''#!/usr/bin/env bash
# Run on a Proxmox node. Creates a new CT only; never overwrites an existing CT.
set -Eeuo pipefail
set +x
umask 077
ctid=${1:?Usage: provision-lxc.sh CTID TEMPLATE STORAGE BRIDGE}
template=${2:?Provide a downloaded local:vztmpl/... template}
storage=${3:?Provide rootfs storage}
bridge=${4:?Provide bridge}
[[ "$ctid" =~ ^[0-9]+$ ]] || exit 2
if pvesh get /cluster/resources --type vm --output-format json | python3 -c 'import json,sys; sys.exit(not any(x["vmid"]==int(sys.argv[1]) for x in json.load(sys.stdin)))' "$ctid"; then
  echo 'CT/VM ID already in use; refusing to replace it.' >&2; exit 1
fi
# Ask before creating anything. Only the salted hash leaves this Python process;
# no plaintext password is passed in argv, environment, files or shell variables.
web_password_record=$(python3 - <<'PASSWORD'
import getpass
import hashlib
import json
import secrets
import warnings

warnings.simplefilter('error', getpass.GetPassWarning)
try:
    password = getpass.getpass('Web-Admin-Passwort: ')
    if not 1 <= len(password) <= 1024:
        raise ValueError
    if password != getpass.getpass('Web-Admin-Passwort wiederholen: '):
        raise ValueError
except (ValueError, EOFError, KeyboardInterrupt, getpass.GetPassWarning):
    raise SystemExit('Installation abgebrochen: Ein nichtleeres, bestätigtes Passwort über eine interaktive Konsole ist erforderlich.') from None
salt = secrets.token_hex(16)
digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
print(json.dumps({'salt': salt, 'hash': digest}))
PASSWORD
)
pct create "$ctid" "$template" --hostname sip-voice-home --unprivileged 1 \
  --features nesting=1,keyctl=1 --cores 2 --memory 3072 --swap 0 \
  --rootfs "$storage:12" --net0 "name=eth0,bridge=$bridge,ip=dhcp,type=veth" \
  --onboot 1 --tags sip-controller
pct start "$ctid"
pct exec "$ctid" -- bash -s <<'INSTALL'
set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive
for ((attempt=0; attempt<30; attempt++)); do
  if getent ahostsv4 download.docker.com >/dev/null; then break; fi
  sleep 2
done
getent ahostsv4 download.docker.com >/dev/null || { echo 'DHCP/DNS not ready in the LXC.' >&2; exit 1; }
apt-get update
apt-get install -y curl ca-certificates python3 openssl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
test "$ID" = debian
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian %s stable\n' "$(dpkg --print-architecture)" "$VERSION_CODENAME" > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
install -d -m 0700 /opt/sip-voice-home
install -d -o 10001 -g 10001 -m 0750 /opt/sip-voice-home/{config,secrets,data,web}
docker compose version
INSTALL
printf '%s' "$web_password_record" | pct exec "$ctid" -- python3 -c '
import os, sys
path = "/opt/sip-voice-home/web/password.json"
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as target:
    os.fchown(target.fileno(), 10001, 10001)
    target.write(sys.stdin.read())
    target.flush()
    os.fsync(target.fileno())
'
unset web_password_record
echo "CT $ctid created. Copy compose.yaml and voice-home-deploy.sh to /opt/sip-voice-home."
echo 'Web password hash installed. Add compose.web.yaml and TLS files to enable the web UI.'
echo 'Supply config/config.yaml and secrets, log in to the registry, then run update.'
''',
    'deploy/lxc/compose.yaml': r'''services:
  controller:
    image: ${VOICE_HOME_IMAGE:?Set VOICE_HOME_IMAGE}
    restart: unless-stopped
    init: true
    network_mode: host
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    mem_limit: 2g
    cpus: 2
    tmpfs:
      - /tmp:size=128m,mode=1777
    volumes:
      - ./config:/config:ro
      - ./secrets:/run/secrets:ro
      - ./data:/data
    healthcheck:
      test: [CMD, voice-home, health]
      interval: 10s
      timeout: 5s
      start_period: 120s
      retries: 3
    logging:
      driver: none
''',
    'deploy/lxc/compose.web.yaml': r'''# Optional HTTPS editor. /web is separate from the editable configuration.
services:
  controller:
    command: [web]
    environment:
      VOICE_HOME_WEB_BIND: ${VOICE_HOME_WEB_BIND:-0.0.0.0}
      VOICE_HOME_WEB_PORT: "8443"
    volumes: !override
      - ./config:/config
      - ./secrets:/run/secrets:ro
      - ./data:/data
      - ./web:/web
''',
    'deploy/lxc/voice-home-deploy.sh': r'''#!/usr/bin/env bash
# Run inside the LXC. Configuration and secrets are never overwritten.
set -Eeuo pipefail
umask 077
cd /opt/sip-voice-home
exec 9>/run/lock/voice-home-deploy.lock
flock -n 9 || { echo 'Another deployment is running.' >&2; exit 1; }
compose=(docker compose --project-name sip-voice-home --file compose.yaml)
if [[ -f compose.web.yaml ]]; then compose+=(--file compose.web.yaml); fi
case "${1:-}" in
  status) "${compose[@]}" exec -T controller voice-home status; exit ;;
  check) "${compose[@]}" run --rm --no-deps controller validate
         "${compose[@]}" run --rm --no-deps controller doctor; exit ;;
  update|apply|stage) mode=$1 ;;
  *) echo 'Usage: voice-home-deploy.sh {check|status|update [image]|apply|stage [image]}' >&2; exit 2 ;;
esac
test -f config/config.yaml || { echo 'Missing config/config.yaml' >&2; exit 1; }
old_image=$(sed -n 's/^VOICE_HOME_IMAGE=//p' .env 2>/dev/null || true)
image=${2:-$old_image}
[[ "$image" =~ ^[a-zA-Z0-9][a-zA-Z0-9._/:@-]+$ ]] || { echo 'Invalid image reference' >&2; exit 2; }
if [[ "$mode" != apply ]]; then docker pull "$image"; fi
candidate=$(docker image inspect "$image" --format '{{.Id}}')
# Use immutable local image ID for the whole deployment, even if latest moves.
export VOICE_HOME_IMAGE=$candidate
"${compose[@]}" run --rm --no-deps controller validate
"${compose[@]}" run --rm --no-deps controller doctor
if [[ "$mode" == stage ]]; then
  "${compose[@]}" run --rm --no-deps --entrypoint python controller -c '
from voice_home.config import load
assert load("/config/config.yaml").call_control["initial_accepting"] is False, "Staging requires initial_accepting: false"
'
fi
cid=$("${compose[@]}" ps -q controller)
previous=''
if [[ -n "$cid" ]]; then
  previous=$(docker inspect "$cid" --format '{{.Image}}')
  "${compose[@]}" exec -T controller voice-home status | python3 -c '
import json,sys
s=json.load(sys.stdin)
if not s.get("fresh") or s.get("busy"):
    sys.exit("Controller busy or status stale; update postponed.")
# Updates require acceptance disabled to close the race with a new incoming call.
if s.get("accepting"):
    sys.exit("Disable call acceptance before updating, then retry.")
'
fi
wait_healthy() {
  for ((i=0; i<90; i++)); do
    if [[ "$mode" == stage ]]; then
      if "${compose[@]}" exec -T controller voice-home status 2>/dev/null | python3 -c 'import json,sys; s=json.load(sys.stdin); sys.exit(not(s.get("fresh") and s.get("speech_ready") and s.get("accepting") is False))' 2>/dev/null; then return 0; fi
    elif "${compose[@]}" exec -T controller voice-home health >/dev/null 2>&1; then return 0; fi
    sleep 2
  done
  return 1
}
if "${compose[@]}" up -d --no-build --force-recreate && wait_healthy; then
  printf 'VOICE_HOME_IMAGE=%s\n' "$image" > .env.new
  mv .env.new .env
  "${compose[@]}" exec -T controller voice-home status
  if [[ "$mode" == stage ]]; then
    echo 'Staging ready, acceptance OFF. SIP health is NOT required in staging.'
  else
    echo 'Deployment healthy. YAML, secrets and data preserved.'
  fi
else
  echo 'Deployment failed.' >&2
  if [[ -n "$previous" ]]; then
    export VOICE_HOME_IMAGE=$previous
    "${compose[@]}" up -d --no-build --force-recreate
    wait_healthy || { echo 'Rollback unhealthy; inspect configuration and SIP connectivity.' >&2; exit 1; }
    echo 'Previous image restored. Configuration was not reverted.' >&2
  else
    "${compose[@]}" stop
  fi
  exit 1
fi
''',
}
# END BUNDLED FILES
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


def prepare_sources(directory, source_dir=None):
    for filename, content in BUNDLED_FILES.items():
        target = directory / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        if source_dir:
            shutil.copyfile(source_dir / filename, target)
        else:
            target.write_text(content, encoding='utf-8', newline='\n')


def image_reference(image):
    registry_host(image)
    if '@' not in image and ':' not in image.rsplit('/', 1)[-1]:
        image += ':latest'
    return image


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
    parser.add_argument('--repository', help='Optional: OWNER/NAME bestimmt nur den GHCR-Image-Namen')
    parser.add_argument('--image', help='Registry-Image; ohne Tag wird latest verwendet')
    parser.add_argument('--source-dir', type=Path, help='Optional: lokale Vorlagen statt der eingebetteten Dateien')
    args = parser.parse_args()
    if platform.system() != 'Linux' or os.geteuid() != 0 or not Path('/etc/pve').is_dir():
        raise RuntimeError('Als root direkt auf dem Proxmox-Host ausführen.')
    if platform.machine() != 'x86_64' or not sys.stdin.isatty():
        raise RuntimeError('Interaktive amd64-Proxmox-Konsole erforderlich.')
    for tool in ('pct', 'pvesh', 'pveam', 'bash', 'python3'):
        if not shutil.which(tool):
            raise RuntimeError('Erforderliches Programm fehlt: ' + tool)
    repository = args.repository
    if repository and not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Repository als OWNER/NAME angeben.')
    with tempfile.TemporaryDirectory(prefix='voice-home-install-') as temporary:
        directory = Path(temporary)
        prepare_sources(directory, args.source_dir)
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
        image = image_reference(args.image or ask('Container-Image (ohne Tag: latest)', default_image))
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
        # Unexpected failures must not expose credentials or command input.
        print('Installation abgebrochen.' if not isinstance(error, (RuntimeError, ValueError)) else str(error), file=sys.stderr)
        sys.exit(1)

VOICE_HOME_EMBEDDED_PYTHON
python3 "$installer" "$@"
