"""Observe before sending; REST acceptance is never device success."""

from dataclasses import dataclass
import json
import math
import queue
import threading
import time

import httpx

from .config import Action, secret


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


class EventWatch:
    def __init__(self, client: httpx.Client, item: str):
        self.client, self.item = client, item
        self.ready = threading.Event()
        self.failed = threading.Event()
        self.stop = threading.Event()
        self.events: queue.Queue[Feedback] = queue.Queue(maxsize=100)
        self.response = None
        self.thread = threading.Thread(target=self._read, daemon=True)

    def _read(self):
        try:
            with self.client.stream("GET", "/rest/events", params={"topics": f"openhab/items/{self.item}/*"}, headers={"Accept": "text/event-stream"}, timeout=httpx.Timeout(4, read=None)) as response:
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
                        value = decode_event("\n".join(data), self.item)
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
        if config.get("token_file"):
            headers["Authorization"] = f"Bearer {secret(config['token_file'])}"
        self.client = client or httpx.Client(base_url=config["base_url"].rstrip("/"), headers=headers, timeout=4, follow_redirects=False, trust_env=False)
        self.watch_factory = watch_factory

    def close(self):
        self.client.close()

    def check(self, actions: list[Action]) -> dict:
        response = self.client.get("/rest/")
        response.raise_for_status()
        for action in actions:
            if action.enabled:
                for item in (action.command_item, action.feedback_item):
                    self.client.get(f"/rest/items/{item}").raise_for_status()
        return {"openhab": "reachable", "enabled_actions": sum(a.enabled for a in actions)}

    def execute(self, action: Action, cancelled: threading.Event) -> str:
        if not action.enabled:
            return "disabled"
        watcher = self.watch_factory(self.client, action.feedback_item)
        sent = False
        try:
            trusted_feedback = True
            if action.feedback_mode == "rollershutter_opening":
                item_response = self.client.get(f"/rest/items/{action.feedback_item}", params={"metadata": "autoupdate"})
                item_response.raise_for_status()
                item = item_response.json()
                if item.get("type") != "Rollershutter":
                    return "failed"
                if action.command_item == action.feedback_item:
                    auto = item.get("metadata", {}).get("autoupdate", {}).get("value")
                    trusted_feedback = str(auto).lower() == "false"
            watcher.start()
            baseline = self.client.get(f"/rest/items/{action.feedback_item}/state", headers={"Accept": "text/plain"})
            baseline.raise_for_status()
            if baseline.text.strip() in {"NULL", "UNDEF"}:
                return "unconfirmed"
            initial_percent = None
            if action.feedback_mode == "rollershutter_opening":
                initial_percent = float(baseline.text.strip())
                if not math.isfinite(initial_percent) or not 0 <= initial_percent <= 100:
                    return "unconfirmed"
            if cancelled.is_set() or watcher.failed.is_set():
                return "unconfirmed"
            dispatched_at = time.monotonic()
            sent = True  # timeout may occur after openHAB accepted the command
            response = self.client.post(f"/rest/items/{action.command_item}", content=action.command, headers={"Content-Type": "text/plain"})
            if 400 <= response.status_code < 500:
                return "failed"
            response.raise_for_status()
            if not trusted_feedback:
                # An UP command can make autoupdate predict 0 immediately.
                # The command was sent, but this cannot prove physical movement.
                return "unconfirmed"
            deadline = dispatched_at + action.timeout_seconds
            while time.monotonic() < deadline and not cancelled.is_set():
                if watcher.failed.is_set():
                    return "unconfirmed"
                try:
                    event = watcher.events.get(timeout=min(0.1, max(0.001, deadline - time.monotonic())))
                except queue.Empty:
                    continue
                if event.at < dispatched_at:
                    continue
                if event.value in action.failure_values:
                    return "failed"
                if initial_percent is not None:
                    try:
                        current = float(event.value)
                    except ValueError:
                        continue
                    if math.isfinite(current) and 0 <= current < initial_percent:
                        return "ok"
                    continue
                # Reject a pre-existing success state echoed by polling/autoupdate.
                if event.value in action.success_values and event.value != baseline.text.strip():
                    return "ok"
            return "unconfirmed"
        except (httpx.HTTPError, RuntimeError, ValueError):
            return "unconfirmed" if sent else "failed"
        finally:
            watcher.close()
