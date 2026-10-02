#!/usr/bin/env bash
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
# Proxmox's unprivileged extractor must traverse the root-owned mount directories.
# Keep the private default for password/config files, but use normal PVE directory modes.
(umask 022; pct create "$ctid" "$template" --hostname sip-voice-home --unprivileged 1 \
  --features nesting=1,keyctl=1 --cores 2 --memory 3072 --swap 0 \
  --rootfs "$storage:12" --net0 "name=eth0,bridge=$bridge,ip=dhcp,type=veth" \
  --onboot 1 --tags sip-controller)
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
