#!/bin/sh
# Generated easy-start.sh embeds the Python installer below this header.
set +x
set -eu
umask 077

if [ "${1:-}" = --help ] || [ "${1:-}" = -h ]; then
  cat <<'HELP'
Usage: sh easy-start.sh [--image namespace/image:latest] [--repository OWNER/NAME]
Update: sh easy-start.sh --update CTID [--image namespace/image:latest]
Pipe mode: wget -qO- URL | sh -s -- [options]
No options: environment-aware installation/maintenance menu.
Run interactively as root on an amd64 Proxmox host or installed LXC.
Installs missing Python 3 via APT, then runs the embedded guided installer.
Requires a web password before creating the LXC. Existing containers are preserved.
Additional arguments are forwarded to the embedded Python installer.
HELP
  exit 0
fi

main() {
# The entire function (including the embedded payload) is parsed before execution.
[ "$(id -u)" -eq 0 ] || { echo 'Root-Zugriff erforderlich.' >&2; exit 1; }
[ "$(uname -m)" = x86_64 ] && [ -t 0 ] || { echo 'Interaktive amd64-Proxmox-Konsole erforderlich.' >&2; exit 1; }
if [ -d /etc/pve ]; then
for tool in pct pvesh pveam; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Erforderliches Programm fehlt: $tool" >&2; exit 1; }
done
elif [ -f /opt/sip-voice-home/compose.yaml ] && [ -f /opt/sip-voice-home/voice-home-deploy.sh ]; then
  command -v docker >/dev/null 2>&1 || { echo 'Docker fehlt.' >&2; exit 1; }
else
  echo 'Weder Proxmox-Host noch bestehende Controller-Installation erkannt.' >&2
  exit 1
fi

ensure_python() {
  if ! command -v python3 >/dev/null 2>&1; then
    echo 'Python 3 fehlt und wird aus den vorhandenen APT-Paketquellen installiert.'
    apt-get update || return $?
    apt-get install -y --no-install-recommends python3 || return $?
  fi
}
ensure_python

installer=$(mktemp /tmp/voice-home-installer.XXXXXXXX.py)
trap 'rm -f -- "$installer"' 0
trap 'exit 130' INT
trap 'exit 143' TERM
