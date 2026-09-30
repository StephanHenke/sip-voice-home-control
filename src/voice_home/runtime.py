"""Volatile status snapshot for CLI/health processes. Never restored."""
import json
from pathlib import Path
import time

STATUS_PATH = Path('/tmp/voice-home/health.json')


def write_status(status, path=None):
    path = path or STATUS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(status), encoding='utf-8')
    temporary.replace(path)


def read_status(path=None):
    try:
        status = json.loads((path or STATUS_PATH).read_text(encoding='utf-8'))
        age = time.time() - status['at']
        status['fresh'] = 0 <= age < 15
        status['age_seconds'] = age
        if not status['fresh']:
            status['status'] = 'UNKNOWN'
            for key in ('accepting', 'call_active', 'busy', 'registered', 'speech_ready', 'adapter_connected'):
                status[key] = None
        return status
    except (OSError, ValueError, TypeError, KeyError):
        return {'fresh': False, 'status': 'UNKNOWN'}


def operating_status(*, stopping, starting, error, busy, accepting):
    if stopping:
        return 'OFFLINE'
    if starting:
        return 'STARTING'
    if error:
        return 'ERROR'
    if busy:
        return 'BUSY'
    return 'READY' if accepting else 'DISABLED'
