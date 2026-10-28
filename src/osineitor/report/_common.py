from __future__ import annotations

import json
from typing import Any

from osineitor.models import ScanResult


def fmt_value(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(map(str, value))
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def details(data: dict[str, Any]) -> list[tuple[str, str]]:
    return [(k, fmt_value(v)) for k, v in data.items() if v not in (None, "", [], {})]


def title(result: ScanResult) -> str:
    suffix = f" (scan #{result.scan_id})" if result.scan_id else ""
    return f"OSINEITOR — {result.target.type}: {result.target.value}{suffix}"


def summary(result: ScanResult) -> list[tuple[str, str]]:
    rows = [
        ("Objetivo", f"{result.target.type}: {result.target.value}"),
        ("Inicio", result.started_at.strftime("%Y-%m-%d %H:%M:%S UTC")),
        ("Profundidad", str(result.depth)),
        ("Entidades", str(len(result.entities))),
    ]
    rows += [(f"  {t}", str(len(es))) for t, es in result.by_type().items()]
    return rows
