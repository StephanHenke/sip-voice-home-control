"""Adapter contract and nonblocking controller status/control bridge."""
from datetime import datetime, timezone
import logging
import queue
import threading
import time
from typing import Protocol

log = logging.getLogger(__name__)


class SmartHomeAdapter(Protocol):
    def read_item(self, item: str) -> dict: ...
    def read_state(self, item: str) -> str: ...
    def send_command(self, item: str, value: str) -> None: ...
    def publish_state(self, item: str, value: str) -> None: ...
    def watch_state(self, item: str): ...
    def watch_commands(self, item: str): ...
    def check(self, actions, control=None) -> dict: ...
    def close(self) -> None: ...


def create_adapter(config):
    if config.smarthome.get('adapter', 'openhab') == 'openhab':
        from .openhab import OpenHAB
        return OpenHAB(config.openhab)
    raise ValueError('Unknown smart-home adapter')


class ControlBridge:
    """Own background adapter; status snapshots coalesce, commands stay ordered."""
    def __init__(self, adapter, config):
        self.adapter, self.config = adapter, config
        self.commands = queue.Queue(maxsize=100)
        self.connected = False
        self.snapshot = None
        self.updated_at = 0
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()

    def update(self, status):
        with self.lock:
            self.snapshot = dict(status)
            self.updated_at = time.monotonic()
        self.wake.set()

    def _publish(self, status):
        values = {
            'switch_item': 'ON' if status['accepting'] else 'OFF',
            'status_item': status['status'],
            'call_active_item': 'ON' if status['call_active'] else 'OFF',
            'heartbeat_item': datetime.now(timezone.utc).isoformat(),
        }
        for key, value in values.items():
            self.adapter.publish_state(self.config[key], value)

    def _run(self):
        delay = 1
        try:
            while not self.stop.is_set():
                watcher = None
                try:
                    watcher = self.adapter.watch_commands(self.config['switch_item'])
                    watcher.start()
                    self.connected = True
                    log.info('adapter_connected')
                    last, sent = 0, None
                    while not self.stop.is_set():
                        if watcher.failed.is_set():
                            raise RuntimeError('Event connection lost')
                        # Commands take priority over publication; never read the item's stored state.
                        for _ in range(100):
                            try:
                                command = watcher.events.get_nowait()
                            except queue.Empty:
                                break
                            self.commands.put_nowait(command.value == 'ON')
                        with self.lock:
                            snapshot = self.snapshot if time.monotonic() - self.updated_at < 15 else None
                        if snapshot is not None and (snapshot != sent or time.monotonic() - last >= self.config['heartbeat_interval_seconds']):
                            self._publish(snapshot)
                            sent, last = snapshot, time.monotonic()
                            delay = 1
                        self.wake.wait(0.05)
                        self.wake.clear()
                except Exception:
                    log.warning('adapter_disconnected')
                finally:
                    self.connected = False
                    if watcher:
                        watcher.close()
                if not self.stop.wait(delay):
                    delay = min(delay * 2, 30)
        finally:
            # Best effort only; caller never waits indefinitely on a failed network.
            with self.lock:
                final = self.snapshot
            if final and final['status'] == 'OFFLINE':
                try:
                    self._publish(final)
                except Exception:
                    pass
            self.adapter.close()

    def close(self):
        self.stop.set()
        self.wake.set()
        self.thread.join(timeout=1)


class NotificationBridge:
    """Best-effort action messages: bounded RAM queue, no replay or retries."""
    def __init__(self, adapter, item):
        self.adapter, self.item = adapter, item
        self.events = queue.Queue(maxsize=32)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()

    def result(self, action, caller, result):
        if result != 'ok' or not action.notification_text:
            return
        message = action.notification_text.replace('{name}', caller.name)
        try:
            self.events.put_nowait((time.monotonic(), message))
        except queue.Full:
            log.warning('notification_dropped reason=queue_full')

    def _run(self):
        try:
            while not self.stop.is_set():
                try:
                    at, message = self.events.get(timeout=.1)
                except queue.Empty:
                    continue
                if time.monotonic() - at > 30:
                    log.warning('notification_dropped reason=expired')
                    continue
                try:
                    self.adapter.send_command(self.item, message)
                except Exception:
                    # No retry: a timeout can mean the event was already delivered.
                    log.warning('notification_dropped reason=adapter_error')
        finally:
            self.adapter.close()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=1)
