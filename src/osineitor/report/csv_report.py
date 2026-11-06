"""Exportación CSV: entidades, relaciones (padre → hija) y hallazgos, cada uno en su fichero."""

from __future__ import annotations

import csv
import io
import json

from osineitor.models import Entity, ScanResult
from osineitor.report._common import fmt_value

# Excel y LibreOffice ejecutan como fórmula una celda que empieza por estos caracteres, y los
# valores vienen de terceros: se les antepone una comilla para que se lean como texto.
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(FORMULA_START) else text


def _write(header: tuple[str, ...], rows: list[tuple[object, ...]]) -> str:
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(header)
    writer.writerows([_cell(c) for c in row] for row in rows)
    return out.getvalue()


def _seen(entity: Entity) -> str:
    return entity.first_seen.strftime("%Y-%m-%dT%H:%M:%SZ") if entity.first_seen else ""


def to_csv_entities(result: ScanResult) -> str:
    header = ("tipo", "valor", "fuentes", "confianza", "primera_vez", "padre", "datos")
    rows = [
        (
            e.type,
            e.value,
            ";".join(e.sources),
            e.confidence or "",
            _seen(e),
            e.parent or "",
            json.dumps(e.data, ensure_ascii=False, default=str) if e.data else "",
        )
        for e in result.entities
    ]
    return _write(header, rows)


def to_csv_relations(result: ScanResult) -> str:
    """Una fila por relación de pivoteo: la entidad padre que llevó a descubrir la hija."""
    header = ("origen", "destino", "tipo_destino", "fuentes")
    rows = [(e.parent, e.key, e.type, ";".join(e.sources)) for e in result.entities if e.parent]
    return _write(header, rows)


def to_csv_findings(result: ScanResult) -> str:
    header = ("regla", "severidad", "titulo", "afectadas", "evidencia", "recomendacion")
    rows = [
        (
            e.data.get("rule", ""),
            e.data.get("severity", ""),
            e.data.get("title", ""),
            ";".join(e.data.get("affected", [])),
            fmt_value(e.data.get("evidence") or ""),
            " ".join(str(e.data.get("recommendation", "")).split()),
        )
        for e in result.entities
        if e.type == "finding"
    ]
    return _write(header, rows)
