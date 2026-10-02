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
