from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import Lock


class KeyValueStore:
    """Tiny sqlite-backed string key-value store, thread-safe via a Lock."""

    def __init__(self, path: Path):
        self._path = path
        self._lock = Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS key_values (key CHAR PRIMARY KEY, value TEXT)"
        )
        self._conn.commit()

    def get(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM key_values WHERE key=?", (key,)
            ).fetchone()
        return row[0] if row else default

    def put(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO key_values (key, value) VALUES (?, ?)",
                (key, value),
            )
            self._conn.commit()

    def delete(self, key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM key_values WHERE key=?", (key,))
            self._conn.commit()
