"""Caché de respuestas HTTP en SQLite (solo GET con éxito, con caducidad)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import httpx

from osineitor.config import data_dir

MAX_BODY = 2_000_000  # no se cachean respuestas mayores (bytes)

SCHEMA = """
CREATE TABLE IF NOT EXISTS responses (
    key TEXT PRIMARY KEY,
    status INTEGER NOT NULL,
    content_type TEXT,
    body BLOB NOT NULL,
    expires REAL NOT NULL
);
"""


def default_cache_path() -> Path:
    return data_dir() / "cache.db"


def cache_key(url: str, params: Any = None) -> str:
    """Huella de la petición. Solo se guarda el hash: la URL (y una key en ella) no se persiste."""
    final = httpx.URL(url).copy_merge_params(params) if params else httpx.URL(url)
    return hashlib.sha256(json.dumps(str(final)).encode()).hexdigest()


class ResponseCache:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_cache_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.executescript(SCHEMA)

    def get(self, key: str, url: str) -> httpx.Response | None:
        row = self._conn.execute(
            "SELECT status, content_type, body FROM responses WHERE key = ? AND expires > ?",
            (key, time.time()),
        ).fetchone()
        if row is None:
            return None
        status, content_type, body = row
        headers = {"content-type": content_type} if content_type else {}
        return httpx.Response(
            status, content=body, headers=headers, request=httpx.Request("GET", url)
        )

    def put(self, key: str, response: httpx.Response, ttl: int) -> None:
        if not 200 <= response.status_code < 300 or len(response.content) > MAX_BODY:
            return
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO responses VALUES (?, ?, ?, ?, ?)",
                (
                    key,
                    response.status_code,
                    response.headers.get("content-type"),
                    response.content,
                    time.time() + ttl,
                ),
            )

    def clear(self) -> int:
        with self._conn:
            return self._conn.execute("DELETE FROM responses").rowcount

    def info(self) -> tuple[int, int]:
        """(entradas vigentes, bytes de contenido)."""
        count, size = self._conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(LENGTH(body)), 0) FROM responses WHERE expires > ?",
            (time.time(),),
        ).fetchone()
        return count, size

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> ResponseCache:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
