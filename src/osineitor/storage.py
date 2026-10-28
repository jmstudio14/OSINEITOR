"""Persistencia de scans en SQLite."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from osineitor.config import data_dir
from osineitor.models import Entity, ScanEvent, ScanResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT NOT NULL,
    target TEXT NOT NULL,
    depth INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS entities (
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    value TEXT NOT NULL,
    source TEXT,
    parent TEXT,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    module TEXT NOT NULL,
    entity TEXT,
    message TEXT NOT NULL
);
"""


def default_db_path() -> Path:
    return data_dir() / "osineitor.db"


class Storage:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)

    def save(self, result: ScanResult) -> int:
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO scans (target_type, target, depth, started_at, finished_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    result.target.type,
                    result.target.value,
                    result.depth,
                    result.started_at.isoformat(),
                    result.finished_at.isoformat() if result.finished_at else None,
                ),
            )
            scan_id = cur.lastrowid
            self._conn.executemany(
                "INSERT INTO entities VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (scan_id, e.type, e.value, e.source, e.parent, json.dumps(e.data, default=str))
                    for e in result.entities
                ],
            )
            self._conn.executemany(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?)",
                [(scan_id, ev.kind, ev.module, ev.entity, ev.message) for ev in result.events],
            )
        result.scan_id = scan_id
        return scan_id

    def load(self, scan_id: int) -> ScanResult | None:
        row = self._conn.execute(
            "SELECT target_type, target, depth, started_at, finished_at FROM scans WHERE id = ?",
            (scan_id,),
        ).fetchone()
        if row is None:
            return None
        target_type, target, depth, started_at, finished_at = row
        entities = [
            Entity(type=t, value=v, source=s, parent=p, data=json.loads(d))
            for t, v, s, p, d in self._conn.execute(
                "SELECT type, value, source, parent, data FROM entities WHERE scan_id = ?"
                " ORDER BY rowid",
                (scan_id,),
            )
        ]
        events = [
            ScanEvent(kind=k, module=m, entity=e, message=msg)
            for k, m, e, msg in self._conn.execute(
                "SELECT kind, module, entity, message FROM events WHERE scan_id = ? ORDER BY rowid",
                (scan_id,),
            )
        ]
        return ScanResult(
            scan_id=scan_id,
            target=Entity(type=target_type, value=target),
            depth=depth,
            started_at=datetime.fromisoformat(started_at),
            finished_at=datetime.fromisoformat(finished_at) if finished_at else None,
            entities=entities,
            events=events,
        )

    def list_scans(self, limit: int = 20) -> list[tuple[int, str, str, int, str]]:
        return self._conn.execute(
            "SELECT s.id, s.target_type, s.target, COUNT(e.rowid), s.started_at FROM scans s"
            " LEFT JOIN entities e ON e.scan_id = s.id GROUP BY s.id ORDER BY s.id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def close(self) -> None:
        self._conn.close()
