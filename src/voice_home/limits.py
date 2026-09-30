"""Process-local callback budgets; reservations include failed attempts."""
from collections import deque
import threading
import time

class CallbackLimits:
    def __init__(self, cooldown: float, hourly: int):
        self.cooldown, self.hourly = cooldown, hourly
        self.attempts = {}
        self.lock = threading.Lock()

    def reserve(self, number: str, now=None) -> bool:
        now = time.monotonic() if now is None else now
        with self.lock:
            for key in list(self.attempts):
                entries = self.attempts[key]
                while entries and entries[0] <= now - max(3600 if self.hourly else 0, self.cooldown):
                    entries.popleft()
                if not entries:
                    del self.attempts[key]
            entries = self.attempts.get(number, deque())
            if entries and self.cooldown and now - entries[-1] < self.cooldown:
                return False
            if self.hourly and sum(at > now - 3600 for at in entries) >= self.hourly:
                return False
            if self.hourly or self.cooldown:
                if not self.hourly:
                    entries.clear()
                entries.append(now)
                self.attempts[number] = entries
            return True
