#!/usr/bin/env bash
# Run on a Proxmox node. Creates a new CT only; never overwrites an existing CT.
set -Eeuo pipefail
ctid=${1:?Usage: provision-lxc.sh CTID TEMPLATE STORAGE BRIDGE}
template=${2:?Provide a downloaded local:vztmpl/... template}
storage=${3:?Provide rootfs storage}
bridge=${4:?Provide bridge}
[[ "$ctid" =~ ^[0-9]+$ ]] || exit 2
if pvesh get /cluster/resources --type vm --output-format json | python3 -c 'import json,sys; sys.exit(not any(x["vmid"]==int(sys.argv[1]) for x in json.load(sys.stdin)))' "$ctid"; then
  echo 'CT/VM ID already in use; refusing to replace it.' >&2; exit 1
fi
pct create "$ctid" "$template" --hostname sip-voice-home --unprivileged 1 \
  --features nesting=1,keyctl=1 --cores 2 --memory 3072 --swap 0 \
  --rootfs "$storage:12" --net0 "name=eth0,bridge=$bridge,ip=dhcp,type=veth" \
  --onboot 1 --tags sip-controller
pct start "$ctid"
pct exec "$ctid" -- bash -s <<'INSTALL'
set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y curl ca-certificates python3
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
install -d -o 10001 -g 10001 -m 0750 /opt/sip-voice-home/{config,secrets,data}
docker compose version
INSTALL
echo "CT $ctid created. Copy compose.yaml and voice-home-deploy.sh to /opt/sip-voice-home."
echo 'Supply config/config.yaml and secrets, log in to the registry, then run update.'
