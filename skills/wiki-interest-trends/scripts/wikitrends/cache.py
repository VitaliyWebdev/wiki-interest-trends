import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Optional


def default_cache_path() -> Path:
    env = os.environ.get("WIKITRENDS_CACHE")
    if env:
        return Path(env)
    return Path.home() / ".cache" / "wikitrends"


def cache_key(*parts: Any) -> str:
    canonical = json.dumps(parts, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class Cache:
    """SQLite-backed cache. A None ttl_seconds means the entry never expires."""

    def __init__(self, path: Optional[Path] = None, clock: Callable[[], float] = time.time):
        self._path = Path(path) if path is not None else default_cache_path()
        self._path.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._conn = sqlite3.connect(self._path / "cache.sqlite3")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache ("
            "key TEXT PRIMARY KEY, value TEXT NOT NULL, expires_at REAL)"
        )
        self._conn.commit()

    def get(self, key: str) -> Optional[Any]:
        row = self._conn.execute(
            "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        value, expires_at = row
        if expires_at is not None and expires_at < self._clock():
            self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            self._conn.commit()
            return None
        return json.loads(value)

    def set(self, key: str, value: Any, ttl_seconds: Optional[float] = None) -> None:
        expires_at = self._clock() + ttl_seconds if ttl_seconds is not None else None
        self._conn.execute(
            "INSERT INTO cache (key, value, expires_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, expires_at = excluded.expires_at",
            (key, json.dumps(value), expires_at),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
