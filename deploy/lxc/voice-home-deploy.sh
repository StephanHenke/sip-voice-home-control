#!/usr/bin/env bash
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
