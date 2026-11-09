"""Persistencia de scans en SQLite."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from osineitor.config import data_dir, private_file
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
    # 8: estado de `osineitor watch`: última ejecución de cada objetivo y qué entidades conoce ya
    # (para alertar solo de lo nuevo).
    """
    CREATE TABLE watch_targets (
        target TEXT PRIMARY KEY,
        last_at TEXT NOT NULL,
        last_scan INTEGER REFERENCES scans(id) ON DELETE SET NULL,
        status TEXT NOT NULL
    );
    CREATE TABLE watch_seen (
        target TEXT NOT NULL,
        key TEXT NOT NULL,
        first_at TEXT NOT NULL,
        PRIMARY KEY (target, key)
    );
    """,
    # 9: entidades nuevas que la vigilancia aún no da por conocidas porque esperan confirmación
    # en otra ejecución (`confirm`); `count` es las veces seguidas que se han visto.
    """
    CREATE TABLE watch_pending (
        target TEXT NOT NULL,
        key TEXT NOT NULL,
        count INTEGER NOT NULL,
        PRIMARY KEY (target, key)
    );
    """,
    # 10: casos (varios scans de una misma investigación, con notas y etiquetas) y un índice por
    # valor para buscar un dato en todos los scans.
    """
    CREATE TABLE cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE COLLATE NOCASE,
        description TEXT NOT NULL DEFAULT '',
        tags TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL
    );
    CREATE TABLE case_scans (
        case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
        scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
        added_at TEXT NOT NULL,
        PRIMARY KEY (case_id, scan_id)
    );
    CREATE INDEX idx_case_scans_scan ON case_scans(scan_id);
    CREATE TABLE case_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
        at TEXT NOT NULL,
        text TEXT NOT NULL
    );
    CREATE INDEX idx_entities_value ON entities(lower(value));
    """,
    # 11: índices para resumir los scans sin recorrer las tablas enteras (`history --json`).
    """
    CREATE INDEX idx_entities_scan_type ON entities(scan_id, type);
    CREATE INDEX idx_events_scan ON events(scan_id);
    CREATE INDEX idx_module_runs_scan ON module_runs(scan_id);
    """,
]

# Tipos cuya coincidencia entre casos dice algo: identifican a alguien o algo concreto. Se dejan
# fuera `technology`, `service`, `record`, `finding`, `asn` o `netblock`: coinciden en casi todo.
CORRELATION_TYPES = (
    "ip",
    "domain",
    "email",
    "username",
    "profile",
    "phone",
    "crypto_address",
    "certificate",
    "person",
    "organization",
    "file",
)
# Cada fila es una entidad guardada; la semilla de un scan solo está en `scans`, así que se une.
_ALL_ENTITIES = (
    "WITH ent(scan_id, type, value, source, confidence) AS ("
    " SELECT scan_id, type, value, source, confidence FROM entities"
    " UNION ALL SELECT id, target_type, target, NULL, NULL FROM scans)"
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class StorageError(Exception):
    """La base de datos no se puede usar con esta versión de OSINEITOR."""


def default_db_path() -> Path:
    return data_dir() / "osineitor.db"


class Storage:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        private_file(self.path)
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

    def scan_digests(self, limit: int = 20) -> list[dict[str, Any]]:
        """Los últimos scans con su estado y recuentos, sin cargar cada uno entero."""
        recent = "(SELECT id FROM scans ORDER BY id DESC LIMIT ?)"
        digests = {
            scan_id: {
                "id": scan_id,
                "target_type": target_type,
                "target": target,
                "entities": entities,
                "started_at": started_at,
                "status": "complete",
                "severity": {},
                "by_type": {},
                "modules": {},
            }
            for scan_id, target_type, target, entities, started_at in self.list_scans(limit)
        }
        # Mismo orden de prioridad que `ScanResult.status`: cancelado manda sobre agotado.
        for scan_id, kind in self._conn.execute(
            f"SELECT scan_id, kind FROM events WHERE scan_id IN {recent}"
            " AND kind IN ('cancelled', 'budget') ORDER BY kind = 'cancelled'",
            (limit,),
        ):
            digests[scan_id]["status"] = "cancelled" if kind == "cancelled" else "truncated"
        for field, query in (
            (
                "by_type",
                f"SELECT scan_id, type, COUNT(*) FROM entities WHERE scan_id IN {recent}"
                " GROUP BY scan_id, type",
            ),
            (
                "severity",
                "SELECT scan_id, json_extract(data, '$.severity'), COUNT(*) FROM entities"
                f" WHERE scan_id IN {recent} AND type = 'finding' GROUP BY 1, 2",
            ),
            (
                "modules",
                f"SELECT scan_id, status, COUNT(*) FROM module_runs WHERE scan_id IN {recent}"
                " GROUP BY scan_id, status",
            ),
        ):
            for scan_id, key, count in self._conn.execute(query, (limit,)):
                digests[scan_id][field][key or "info"] = count
        return list(digests.values())

    def watch_last(self, target: str) -> tuple[str, int | None, str] | None:
        """Última ejecución vigilada de `target`: (fecha ISO, id del scan, estado) o `None`."""
        return self._conn.execute(
            "SELECT last_at, last_scan, status FROM watch_targets WHERE target = ?", (target,)
        ).fetchone()

    def watch_seen(self, target: str) -> set[str]:
        """Claves de las entidades que la vigilancia de `target` ya conoce."""
        rows = self._conn.execute("SELECT key FROM watch_seen WHERE target = ?", (target,))
        return {key for (key,) in rows}

    def watch_pending(self, target: str) -> dict[str, int]:
        """Entidades nuevas de `target` pendientes de confirmar, con las veces que se han visto."""
        rows = self._conn.execute(
            "SELECT key, count FROM watch_pending WHERE target = ?", (target,)
        )
        return dict(rows.fetchall())

    def watch_record(
        self,
        target: str,
        *,
        at: str,
        scan_id: int | None,
        status: str,
        add: Iterable[str],
        remove: Iterable[str] = (),
        pending: dict[str, int] | None = None,
    ) -> None:
        """Anota una ejecución: cuándo fue, qué entidades ya se conocen y cuáles desaparecieron.

        `pending`, si se indica, sustituye a todo lo pendiente de confirmar de `target`.
        """
        with self._conn:
            self._conn.execute(
                "INSERT INTO watch_targets (target, last_at, last_scan, status) VALUES (?, ?, ?, ?)"
                " ON CONFLICT(target) DO UPDATE SET last_at = excluded.last_at,"
                " last_scan = excluded.last_scan, status = excluded.status",
                (target, at, scan_id, status),
            )
            self._conn.executemany(
                "INSERT OR IGNORE INTO watch_seen (target, key, first_at) VALUES (?, ?, ?)",
                [(target, key, at) for key in add],
            )
            self._conn.executemany(
                "DELETE FROM watch_seen WHERE target = ? AND key = ?",
                [(target, key) for key in remove],
            )
            if pending is not None:
                self._conn.execute("DELETE FROM watch_pending WHERE target = ?", (target,))
                self._conn.executemany(
                    "INSERT INTO watch_pending (target, key, count) VALUES (?, ?, ?)",
                    [(target, key, n) for key, n in pending.items()],
                )

    # --- casos (F7.2), búsqueda global (F7.5) y correlación (F7.6) ---

    def case_create(self, name: str, description: str = "", tags: Iterable[str] = ()) -> int:
        try:
            with self._conn:
                cur = self._conn.execute(
                    "INSERT INTO cases (name, description, tags, created_at) VALUES (?, ?, ?, ?)",
                    (name, description, json.dumps(sorted(set(tags))), _now()),
                )
        except sqlite3.IntegrityError as exc:
            raise StorageError(f"ya existe el caso {name!r}") from exc
        assert cur.lastrowid is not None
        return cur.lastrowid

    def case_id(self, name: str) -> int | None:
        row = self._conn.execute("SELECT id FROM cases WHERE name = ?", (name,)).fetchone()
        return row[0] if row else None

    def case_add_scan(self, case_id: int, scan_id: int) -> bool:
        """Añade el scan al caso; `False` si ya estaba. `StorageError` si el scan no existe."""
        if not self._conn.execute("SELECT 1 FROM scans WHERE id = ?", (scan_id,)).fetchone():
            raise StorageError(f"no existe el scan {scan_id}")
        with self._conn:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO case_scans (case_id, scan_id, added_at) VALUES (?, ?, ?)",
                (case_id, scan_id, _now()),
            )
        return cur.rowcount == 1

    def case_add_note(self, case_id: int, text: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO case_notes (case_id, at, text) VALUES (?, ?, ?)",
                (case_id, _now(), text),
            )

    def case_get(self, name: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, name, description, tags, created_at FROM cases WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return None
        case_id, real_name, description, tags, created = row
        scans = [
            {"id": i, "target_type": t, "target": v, "started_at": s, "entities": n}
            for i, t, v, s, n in self._conn.execute(
                "SELECT s.id, s.target_type, s.target, s.started_at,"
                " (SELECT COUNT(*) FROM entities e WHERE e.scan_id = s.id)"
                " FROM case_scans cs JOIN scans s ON s.id = cs.scan_id"
                " WHERE cs.case_id = ? ORDER BY s.id",
                (case_id,),
            )
        ]
        notes = [
            {"at": at, "text": text}
            for at, text in self._conn.execute(
                "SELECT at, text FROM case_notes WHERE case_id = ? ORDER BY id", (case_id,)
            )
        ]
        return {
            "id": case_id,
            "name": real_name,
            "description": description,
            "tags": json.loads(tags),
            "created_at": created,
            "scans": scans,
            "notes": notes,
        }

    def case_list(self) -> list[dict]:
        return [
            {
                "name": n,
                "description": d,
                "tags": json.loads(t),
                "created_at": c,
                "scans": count,
            }
            for n, d, t, c, count in self._conn.execute(
                "SELECT c.name, c.description, c.tags, c.created_at,"
                " (SELECT COUNT(*) FROM case_scans cs WHERE cs.case_id = c.id)"
                " FROM cases c ORDER BY c.name"
            )
        ]

    def search(
        self, value: str, *, contains: bool = False, types: Iterable[str] = (), limit: int = 500
    ) -> list[dict]:
        """Scans (y casos) donde aparece `value`, por igualdad sin distinguir mayúsculas o, con
        `contains`, por subcadena. Incluye la semilla de cada scan."""
        needle = value.strip().lower()
        wanted = tuple(types)
        where = "instr(lower(value), ?) > 0" if contains else "lower(value) = ?"
        params: list[object] = [needle]
        if wanted:
            where += f" AND type IN ({','.join('?' * len(wanted))})"
            params += wanted
        rows = self._conn.execute(
            f"{_ALL_ENTITIES} SELECT ent.scan_id, ent.type, ent.value, ent.source, ent.confidence,"
            " s.target_type, s.target, s.started_at FROM ent JOIN scans s ON s.id = ent.scan_id"
            f" WHERE {where} ORDER BY ent.scan_id DESC, ent.type, ent.value LIMIT ?",
            (*params, limit),
        ).fetchall()
        cases_of = self._cases_by_scan({r[0] for r in rows})
        return [
            {
                "scan_id": sid,
                "type": typ,
                "value": val,
                "source": src,
                "confidence": conf,
                "target": f"{ttype}:{target}",
                "started_at": started,
                "cases": cases_of.get(sid, []),
            }
            for sid, typ, val, src, conf, ttype, target, started in rows
        ]

    def _cases_by_scan(self, scan_ids: set[int]) -> dict[int, list[str]]:
        found: dict[int, list[str]] = {}
        for scan_id in scan_ids:
            found[scan_id] = [
                name
                for (name,) in self._conn.execute(
                    "SELECT c.name FROM case_scans cs JOIN cases c ON c.id = cs.case_id"
                    " WHERE cs.scan_id = ? ORDER BY c.name",
                    (scan_id,),
                )
            ]
        return found

    def correlations(self, case_id: int) -> list[dict]:
        """Entidades identificadoras del caso que también aparecen en scans de **otros** casos."""
        marks = ",".join("?" * len(CORRELATION_TYPES))
        rows = self._conn.execute(
            f"{_ALL_ENTITIES} SELECT DISTINCT a.type, lower(a.value), c2.name, b.scan_id"
            " FROM ent a"
            " JOIN case_scans m ON m.scan_id = a.scan_id AND m.case_id = ?"
            " JOIN ent b ON b.type = a.type AND lower(b.value) = lower(a.value)"
            " JOIN case_scans m2 ON m2.scan_id = b.scan_id AND m2.case_id != ?"
            " JOIN cases c2 ON c2.id = m2.case_id"
            f" WHERE a.type IN ({marks}) ORDER BY a.type, lower(a.value), c2.name, b.scan_id",
            (case_id, case_id, *CORRELATION_TYPES),
        ).fetchall()
        grouped: dict[tuple[str, str], dict] = {}
        for typ, val, case_name, scan_id in rows:
            item = grouped.setdefault(
                (typ, val), {"type": typ, "value": val, "cases": [], "scans": []}
            )
            if case_name not in item["cases"]:
                item["cases"].append(case_name)
            if scan_id not in item["scans"]:
                item["scans"].append(scan_id)
        return list(grouped.values())

    def purge(self, before: str, *, dry_run: bool = False) -> int:
        """Borra los scans iniciados antes de `before` (fecha ISO) y devuelve cuántos eran."""
        (count,) = self._conn.execute(
            "SELECT COUNT(*) FROM scans WHERE started_at < ?", (before,)
        ).fetchone()
        if count and not dry_run:
            with self._conn:
                self._conn.execute("DELETE FROM scans WHERE started_at < ?", (before,))
        return count

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Storage:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
