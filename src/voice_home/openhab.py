"""Observe before sending; REST acceptance is never device success."""

from dataclasses import dataclass
import json
import queue
import threading
import time

import httpx

from .config import Action, credential
from .actions import ActionExecutor, CommandRejected


@dataclass(frozen=True)
class Feedback:
    at: float
    value: str


def decode_event(data: str, item: str) -> str | None:
    try:
        event = json.loads(data)
        if event.get("type") not in {"ItemStateEvent", "ItemStateChangedEvent"}:
            return None
        if event.get("topic") not in {f"openhab/items/{item}/state", f"openhab/items/{item}/statechanged"}:
            return None
        payload = event["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return str(payload["value"])
    except (ValueError, TypeError, KeyError):
        return None


def decode_command(data, item):
    try:
        event = json.loads(data)
        if event.get('type') != 'ItemCommandEvent' or event.get('topic') != f'openhab/items/{item}/command':
            return None
        payload = event['payload']
        payload = json.loads(payload) if isinstance(payload, str) else payload
        value = payload['value']
        return value if value in ('ON', 'OFF') else None
    except (ValueError, TypeError, KeyError):
        return None


class EventWatch:
    def __init__(self, client: httpx.Client, item: str, commands=False):
        self.commands = commands
        self.client, self.item = client, item
        self.ready = threading.Event()
        self.failed = threading.Event()
        self.stop = threading.Event()
        self.events: queue.Queue[Feedback] = queue.Queue(maxsize=100)
        self.response = None
        self.thread = threading.Thread(target=self._read, daemon=True)

    def _read(self):
        try:
            with self.client.stream("GET", "/rest/events", params={"topics": f"openhab/items/{self.item}/*"}, headers={"Accept": "text/event-stream"}, timeout=httpx.Timeout(4, read=35 if self.commands else None)) as response:
                self.response = response
                response.raise_for_status()
                if "text/event-stream" not in response.headers.get("content-type", ""):
                    raise ValueError("Kein Ereignisstrom")
                self.ready.set()
                data = []
                for line in response.iter_lines():
                    if self.stop.is_set():
                        break
                    if line.startswith("data:"):
                        data.append(line[5:].lstrip())
                    elif not line and data:
                        value = (decode_command if self.commands else decode_event)("\n".join(data), self.item)
                        data = []
                        if value is not None:
                            self.events.put_nowait(Feedback(time.monotonic(), value))
        except Exception:
            self.failed.set()
        finally:
            if not self.stop.is_set():
                self.failed.set()

    def start(self):
        self.thread.start()
        deadline = time.monotonic() + 4
        while not self.ready.wait(0.05):
            if self.failed.is_set() or time.monotonic() >= deadline:
                raise RuntimeError("openHAB-Ereignisstrom nicht verfügbar")

    def close(self):
        self.stop.set()
        if self.response is not None:
            self.response.close()
        if self.thread.ident is not None:
            self.thread.join(timeout=0.2)


class OpenHAB:
    def __init__(self, config: dict, *, client=None, watch_factory=EventWatch):
        headers = {"Accept": "application/json"}
        token = credential(config, "token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = client or httpx.Client(base_url=config["base_url"].rstrip("/"), headers=headers, timeout=4, follow_redirects=False, trust_env=False)
        self.watch_factory = watch_factory

    def close(self):
        self.client.close()

    def check(self, actions: list[Action], control=None) -> dict:
        response = self.client.get("/rest/")
        response.raise_for_status()
        for action in actions:
            if action.enabled:
                for item in (action.command_item, action.feedback_item):
                    self.client.get(f"/rest/items/{item}").raise_for_status()
        if control and control['enabled']:
            for key, expected in [('switch_item', 'Switch'), ('status_item', 'String'), ('call_active_item', 'Switch'), ('heartbeat_item', 'DateTime')]:
                item = self.read_item(control[key])
                if item.get('type') != expected:
                    raise ValueError('Control item type mismatch')
        return {"openhab": "reachable", "enabled_actions": sum(a.enabled for a in actions)}

    def read_item(self, item):
        return self._request('GET', f'/rest/items/{item}', params={'metadata': 'autoupdate'}).json()

    def read_state(self, item):
        return self._request('GET', f'/rest/items/{item}/state', headers={'Accept': 'text/plain'}).text.strip()

    def send_command(self, item, value):
        self._request('POST', f'/rest/items/{item}', content=value, headers={'Content-Type': 'text/plain'})

    def publish_state(self, item, value):
        self._request('PUT', f'/rest/items/{item}/state', content=value, headers={'Content-Type': 'text/plain'})

    def _request(self, method, path, **kwargs):
        try:
            response = self.client.request(method, path, **kwargs)
            if method == 'POST' and 400 <= response.status_code < 500:
                raise CommandRejected('Command rejected')
            response.raise_for_status()
            return response
        except httpx.HTTPError:
            raise RuntimeError('Adapter request failed') from None

    def watch_state(self, item):
        return self.watch_factory(self.client, item)

    def watch_commands(self, item):
        return EventWatch(self.client, item, commands=True)

    def execute(self, action, cancelled):
        # Compatibility for existing consumers; engine uses the neutral executor.
        return ActionExecutor(self).execute(action, cancelled)
