"""Datos del panel principal, calculados solo con lo que devuelve la CLI (sin Qt).

`history --json` da los recuentos de cada scan; `show --json` solo hace falta para los títulos de
los hallazgos. Las cifras por scan cubren los últimos (`RECENT_SCANS`), y lo dicen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

RECENT_SCANS = 10
HISTORY_LIMIT = 500
DAILY_WINDOW = 14
TOP_TYPES = 8
TOP_FINDINGS = 8

SEVERITIES = ("critical", "high", "medium", "low", "info")
SEVERITY_LABELS = {
    "critical": "crítica",
    "high": "alta",
    "medium": "media",
    "low": "baja",
    "info": "informativa",
}
OTHERS = "otros"


@dataclass
class ScanSummary:
    scan_id: int
    target: str
    target_type: str
    started_at: str
    status: str
    entities: int
    by_severity: dict[str, int]
    by_type: dict[str, int]
    modules: dict[str, int]
    findings: list[dict[str, Any]]

    @property
    def worst(self) -> str | None:
        return worst_severity(self.by_severity)


@dataclass
class Overview:
    scans_total: int = 0
    scans_7d: int = 0
    scans_prev_7d: int = 0
    entities_total: int = 0
    daily: list[tuple[date, int]] = field(default_factory=list)
    analyzed: list[ScanSummary] = field(default_factory=list)  # del más reciente al más antiguo
    severity: dict[str, int] = field(default_factory=dict)
    types: list[tuple[str, int]] = field(default_factory=list)
    modules_last: dict[str, int] = field(default_factory=dict)  # estado → módulos, último scan
    findings: list[dict[str, Any]] = field(default_factory=list)  # los más graves
    catalog_total: int | None = None  # `None`: el catálogo no se ha podido cargar
    catalog_missing_key: int = 0
    catalog_active: int = 0

    @property
    def scans_delta(self) -> int:
        return self.scans_7d - self.scans_prev_7d

    @property
    def urgent(self) -> int:
        return self.severity.get("critical", 0) + self.severity.get("high", 0)

    @property
    def worst(self) -> str | None:
        return worst_severity(self.severity)

    @property
    def modules_failed(self) -> int:
        return self.modules_last.get("error", 0) + self.modules_last.get("quota", 0)


def worst_severity(counts: dict[str, int]) -> str | None:
    return next((s for s in SEVERITIES if counts.get(s)), None)


def parse_time(value: object) -> datetime | None:
    """Fecha ISO de la CLI, siempre con zona (una sin zona se toma como UTC); `None` si no vale."""
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _severity(entity: dict[str, Any]) -> str:
    value = (entity.get("data") or {}).get("severity")
    return value if value in SEVERITIES else "info"


def findings_of(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Los hallazgos de la salida de `show --json`: lo único que `history --json` no resume."""
    return [e for e in result.get("entities") or [] if e.get("type") == "finding"]


def summarize_row(row: dict[str, Any], findings: list[dict[str, Any]] | None = None) -> ScanSummary:
    """Resume una fila de `history --json`; `findings` se añaden cuando llegan de `show`."""
    by_severity: dict[str, int] = {}
    for severity, count in (row.get("severity") or {}).items():
        key = severity if severity in SEVERITIES else "info"
        by_severity[key] = by_severity.get(key, 0) + int(count)
    return ScanSummary(
        scan_id=row["id"],
        target=str(row.get("target", "")),
        target_type=str(row.get("target_type", "")),
        started_at=str(row.get("started_at", "")),
        status=str(row.get("status", "")),
        entities=int(row.get("entities") or 0),
        by_severity=by_severity,
        by_type=dict(row.get("by_type") or {}),
        modules=dict(row.get("modules") or {}),
        findings=findings or [],
    )


def _top_types(summaries: list[ScanSummary]) -> list[tuple[str, int]]:
    totals: dict[str, int] = {}
    for summary in summaries:
        for kind, count in summary.by_type.items():
            totals[kind] = totals.get(kind, 0) + count
    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    rest = sum(count for _kind, count in ranked[TOP_TYPES:])
    return ranked[:TOP_TYPES] + ([(OTHERS, rest)] if rest else [])


def _top_findings(summaries: list[ScanSummary]) -> list[dict[str, Any]]:
    """Los hallazgos más graves; a igual gravedad, los del scan más reciente."""
    rows = [
        {
            "severity": _severity(entity),
            "title": str((entity.get("data") or {}).get("title") or entity.get("value", "")),
            "value": str(entity.get("value", "")),
            "scan_id": summary.scan_id,
            "target": summary.target,
            "started_at": summary.started_at,
        }
        for summary in summaries
        for entity in summary.findings
    ]
    rows.sort(key=lambda row: SEVERITIES.index(row["severity"]))  # estable: respeta la recencia
    return rows[:TOP_FINDINGS]


def aggregate(
    history: list[dict[str, Any]],
    findings: dict[int, list[dict[str, Any]]],
    now: datetime,
    catalog: list[dict[str, Any]] | None = None,
) -> Overview:
    """Une `history --json` (del más reciente al más antiguo), `show` y `modules --json`."""
    overview = Overview(scans_total=len(history))
    today = now.date()
    days = [today - timedelta(days=i) for i in range(DAILY_WINDOW - 1, -1, -1)]
    per_day = dict.fromkeys(days, 0)
    for row in history:
        overview.entities_total += int(row.get("entities") or 0)
        started = parse_time(row.get("started_at"))
        if started is None:
            continue
        age = now - started
        if timedelta(0) <= age < timedelta(days=7):
            overview.scans_7d += 1
        elif timedelta(days=7) <= age < timedelta(days=14):
            overview.scans_prev_7d += 1
        day = started.astimezone(now.tzinfo).date()
        if day in per_day:
            per_day[day] += 1
    overview.daily = list(per_day.items())

    recent = [summarize_row(row, findings.get(row["id"])) for row in history[:RECENT_SCANS]]
    overview.analyzed = recent
    for summary in recent:
        for severity, count in summary.by_severity.items():
            overview.severity[severity] = overview.severity.get(severity, 0) + count
    overview.types = _top_types(recent)
    overview.findings = _top_findings(recent)
    if recent:
        overview.modules_last = dict(recent[0].modules)

    if catalog is not None:
        overview.catalog_total = len(catalog)
        overview.catalog_active = sum(1 for m in catalog if not m.get("passive", True))
        overview.catalog_missing_key = sum(
            1 for m in catalog if m.get("requires_key") and not m.get("key_configured")
        )
    return overview
