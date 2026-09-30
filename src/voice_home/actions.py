"""Transport-independent interpretation of observed device feedback."""
import math
import queue
import threading
import time
from .config import Action

class CommandRejected(RuntimeError):
    pass

class ActionExecutor:
    def __init__(self, adapter):
        self.adapter = adapter

    def execute(self, action: Action, cancelled: threading.Event) -> str:
        if not action.enabled:
            return "disabled"
        watcher = self.adapter.watch_state(action.feedback_item)
        sent = False
        try:
            trusted_feedback = True
            same_item = action.command_item == action.feedback_item
            if action.feedback_mode == "rollershutter_opening" or same_item:
                item = self.adapter.read_item(action.feedback_item)
                if action.feedback_mode == "rollershutter_opening" and item.get("type") != "Rollershutter":
                    return "failed"
                if same_item:
                    auto = item.get("metadata", {}).get("autoupdate", {}).get("value")
                    trusted_feedback = str(auto).lower() == "false"
            watcher.start()
            baseline = self.adapter.read_state(action.feedback_item)
            if baseline in {"NULL", "UNDEF"}:
                return "unconfirmed"
            initial_percent = None
            lower, upper = sorted((action.open_position, action.closed_position))
            if action.feedback_mode == "rollershutter_opening":
                initial_percent = float(baseline)
                if not math.isfinite(initial_percent) or not lower <= initial_percent <= upper:
                    return "unconfirmed"
            if cancelled.is_set() or watcher.failed.is_set():
                return "unconfirmed"
            dispatched_at = time.monotonic()
            sent = True  # timeout may occur after openHAB accepted the command
            try:
                self.adapter.send_command(action.command_item, action.command)
            except CommandRejected:
                return "failed"
            if not trusted_feedback:
                # autoupdate can predict the target position immediately.
                # The command was sent, but this cannot prove physical movement.
                return "unconfirmed"
            deadline = dispatched_at + action.timeout_seconds
            success_values = action.resolved_success_values
            failure_values = action.resolved_failure_values
            while time.monotonic() < deadline and not cancelled.is_set():
                if watcher.failed.is_set():
                    return "unconfirmed"
                try:
                    event = watcher.events.get(timeout=min(0.1, max(0.001, deadline - time.monotonic())))
                except queue.Empty:
                    continue
                if event.at < dispatched_at:
                    continue
                if event.value in failure_values:
                    return "failed"
                if initial_percent is not None:
                    try:
                        current = float(event.value)
                    except ValueError:
                        continue
                    if math.isfinite(current) and lower <= current <= upper and abs(current - action.open_position) < abs(initial_percent - action.open_position):
                        return "ok"
                    continue
                # Reject a pre-existing success state echoed by polling/autoupdate.
                changed = event.value != baseline
                if action.state_values:
                    changed = action.state_for(event.value) != action.state_for(baseline)
                if event.value in success_values and changed:
                    return "ok"
            return "unconfirmed"
        except (RuntimeError, ValueError):
            return "unconfirmed" if sent else "failed"
        finally:
            watcher.close()
