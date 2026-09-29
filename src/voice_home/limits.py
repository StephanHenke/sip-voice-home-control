"""Atomic, persistent callback budgets; failed calls count as attempts."""

import sqlite3
import time
from contextlib import closing
from pathlib import Path


class CallbackLimits:
    def __init__(self, path: Path, cooldown: float, hourly: int):
        self.path, self.cooldown, self.hourly = path, cooldown, hourly
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS attempts (number TEXT NOT NULL, at REAL NOT NULL)")

    def reserve(self, number: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            # Preserve future entries if wall-clock time moves backwards.
            db.execute("DELETE FROM attempts WHERE at < ?", (now - 86400,))
            latest = db.execute("SELECT MAX(at) FROM attempts WHERE number=? AND at>=?", (number, now - max(3600, self.cooldown))).fetchone()[0]
            hourly = db.execute("SELECT COUNT(*) FROM attempts WHERE number=? AND at>=?", (number, now - 3600)).fetchone()[0]
            if (latest is not None and now - latest < self.cooldown) or hourly >= self.hourly:
                return False
            db.execute("INSERT INTO attempts VALUES (?, ?)", (number, now))
            return True
