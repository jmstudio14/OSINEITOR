"""Persistencia de scans en SQLite."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from osineitor.config import data_dir
from osineitor.models import Entity, Evidence, ModuleRun, ScanEvent, ScanResult

# Migraciones por `PRAGMA user_version`: la posición en la lista (empezando en 1) es la versión.
# Nunca se edita una ya publicada: los cambios van en una migración nueva al final.
MIGRATIONS = [
    # 1: esquema de la v0.1.0 (una BD de esa versión tiene user_version 0 pero ya estas tablas).
    """
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
    """,
    # 2: estado de cada módulo en cada scan.
    """
    CREATE TABLE module_runs (
        scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
        module TEXT NOT NULL,
        status TEXT NOT NULL,
        entity TEXT,
        entities INTEGER NOT NULL,
        requests INTEGER NOT NULL,
        cache_hits INTEGER NOT NULL,
        duration_ms INTEGER NOT NULL,
        message TEXT NOT NULL
    );
    """,
    # 3: todas las fuentes que vieron cada entidad (JSON; las filas antiguas quedan en `[]`).
    "ALTER TABLE entities ADD COLUMN observations TEXT NOT NULL DEFAULT '[]'",
    # 4: respuesta original de cada fuente con su SHA-256 (`--evidence`).
    """
    CREATE TABLE evidence (
        scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
        module TEXT NOT NULL,
        entity TEXT,
        kind TEXT NOT NULL,
        url TEXT NOT NULL,
        method TEXT NOT NULL,
        status INTEGER,
        at TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        size INTEGER NOT NULL,
        truncated INTEGER NOT NULL,
        body BLOB NOT NULL
    );
    """,
    # 5: confianza de cada entidad (las filas antiguas quedan sin valor).
    "ALTER TABLE entities ADD COLUMN confidence TEXT",
    # 6: alcance declarado del scan (JSON; NULL si no hubo).
    "ALTER TABLE scans ADD COLUMN scope TEXT",
    # 7: propósito declarado del scan (NULL si no se indicó).
    "ALTER TABLE scans ADD COLUMN purpose TEXT",
]


class StorageError(Exception):
    """La base de datos no se puede usar con esta versión de OSINEITOR."""


def default_db_path() -> Path:
    return data_dir() / "osineitor.db"


class Storage:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    def _migrate(self) -> None:
        current = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if current > len(MIGRATIONS):
            self._conn.close()
            raise StorageError(
                f"la base de datos {self.path} es de una versión más nueva de OSINEITOR "
                f"(esquema {current}, esta versión llega a {len(MIGRATIONS)})"
            )
        for version in range(current + 1, len(MIGRATIONS) + 1):
            # Cada migración y su número de versión se confirman juntos: o entera o ninguna.
            with self._conn:
                self._conn.execute("BEGIN")  # el DDL de sqlite3 no abre transacción por sí solo
                for statement in MIGRATIONS[version - 1].split(";"):
                    if statement.strip():
                        self._conn.execute(statement)
                self._conn.execute(f"PRAGMA user_version = {version}")

    def save(self, result: ScanResult) -> int:
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO scans (target_type, target, depth, started_at, finished_at, scope,"
                " purpose) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    result.target.type,
                    result.target.value,
                    result.depth,
                    result.started_at.isoformat(),
                    result.finished_at.isoformat() if result.finished_at else None,
                    json.dumps(result.scope) if result.scope else None,
                    result.purpose,
                ),
            )
            scan_id = cur.lastrowid
            self._conn.executemany(
                "INSERT INTO entities (scan_id, type, value, source, parent, data, observations,"
                " confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        scan_id,
                        e.type,
                        e.value,
                        e.source,
                        e.parent,
                        json.dumps(e.data, default=str),
                        json.dumps([o.model_dump(mode="json") for o in e.observations]),
                        e.confidence,
                    )
                    for e in result.entities
                ],
            )
            self._conn.executemany(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?)",
                [(scan_id, ev.kind, ev.module, ev.entity, ev.message) for ev in result.events],
            )
            self._conn.executemany(
                "INSERT INTO module_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        scan_id,
                        r.module,
                        r.status,
                        r.entity,
                        r.entities,
                        r.requests,
                        r.cache_hits,
                        r.duration_ms,
                        r.message,
                    )
                    for r in result.runs
                ],
            )
            self._conn.executemany(
                "INSERT INTO evidence (scan_id, module, entity, kind, url, method, status, at,"
                " sha256, size, truncated, body) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        scan_id,
                        v.module,
                        v.entity,
                        v.kind,
                        v.url,
                        v.method,
                        v.status,
                        v.at.isoformat(),
                        v.sha256,
                        v.size,
                        int(v.truncated),
                        v.body,
                    )
                    for v in result.evidence
                ],
            )
        result.scan_id = scan_id
        return scan_id

    def load(self, scan_id: int) -> ScanResult | None:
        row = self._conn.execute(
            "SELECT target_type, target, depth, started_at, finished_at, scope,"
            " purpose FROM scans WHERE id = ?",
            (scan_id,),
        ).fetchone()
        if row is None:
            return None
        target_type, target, depth, started_at, finished_at, scope, purpose = row
        entities = [
            Entity(
                type=t,
                value=v,
                source=s,
                parent=p,
                data=json.loads(d),
                observations=json.loads(o),
                confidence=c,
            )
            for t, v, s, p, d, o, c in self._conn.execute(
                "SELECT type, value, source, parent, data, observations, confidence FROM entities"
                " WHERE scan_id = ? ORDER BY rowid",
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
        runs = [
            ModuleRun(
                module=m,
                status=st,
                entity=e,
                entities=n,
                requests=rq,
                cache_hits=ch,
                duration_ms=ms,
                message=msg,
            )
            for m, st, e, n, rq, ch, ms, msg in self._conn.execute(
                "SELECT module, status, entity, entities, requests, cache_hits, duration_ms,"
                " message FROM module_runs WHERE scan_id = ? ORDER BY rowid",
                (scan_id,),
            )
        ]
        evidence = [
            Evidence(
                module=m,
                entity=e,
                kind=k,
                url=u,
                method=me,
                status=st,
                at=datetime.fromisoformat(at),
                sha256=h,
                size=sz,
                truncated=bool(tr),
                body=b,
            )
            for m, e, k, u, me, st, at, h, sz, tr, b in self._conn.execute(
                "SELECT module, entity, kind, url, method, status, at, sha256, size, truncated,"
                " body FROM evidence WHERE scan_id = ? ORDER BY rowid",
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
            runs=runs,
            evidence=evidence,
            scope=json.loads(scope) if scope else None,
            purpose=purpose,
            truncated=any(ev.kind == "budget" for ev in events),
        )

    def list_scans(self, limit: int = 20) -> list[tuple[int, str, str, int, str]]:
        return self._conn.execute(
            "SELECT s.id, s.target_type, s.target, COUNT(e.rowid), s.started_at FROM scans s"
            " LEFT JOIN entities e ON e.scan_id = s.id GROUP BY s.id ORDER BY s.id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Storage:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
