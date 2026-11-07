"""Informes en Markdown pensados para leerse, no para consultarse: superficie de ataque (F7.12) y
ejecutivo (F7.7). Parten de los hallazgos (F7.8) y de la puntuación de riesgo (F7.9)."""

from __future__ import annotations

from typing import Any

from osineitor import risk
from osineitor.models import Entity, EntityType, ScanResult
from osineitor.report._common import evidence_hint, hypothesis_lines, title

SEVERITY_ORDER = ("critical", "high", "medium", "low", "info")
KEY_SEVERITIES = ("critical", "high", "medium")
MAX_KEY_FINDINGS = 10
TOP_ASSETS = 5


def _cell(value: object) -> str:
    """Texto de una celda de tabla: los datos son de terceros, así que sin `|` ni saltos."""
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def _table(headers: tuple[str, ...], rows: list[tuple[object, ...]]) -> list[str]:
    if not rows:
        return ["_Sin datos._"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return lines


def _findings(result: ScanResult) -> list[Entity]:
    """Hallazgos de mayor a menor severidad y, a igual severidad, por valor (orden estable)."""
    found = [e for e in result.entities if e.type == EntityType.FINDING]

    def rank(e: Entity) -> tuple[int, str]:
        severity = str(e.data.get("severity", "info"))
        return (SEVERITY_ORDER.index(severity) if severity in SEVERITY_ORDER else 99, e.value)

    return sorted(found, key=rank)


def _asset_of(finding: Entity, index: dict[str, Entity]) -> str:
    affected = finding.data.get("affected") or []
    return str(index[affected[0]].value) if affected and affected[0] in index else finding.value


def _by_severity(findings: list[Entity]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in findings:
        severity = str(f.data.get("severity", "info"))
        counts[severity] = counts.get(severity, 0) + 1
    return {s: counts[s] for s in SEVERITY_ORDER if s in counts}


def _limits(result: ScanResult) -> list[str]:
    notes = []
    if result.status != "complete":
        notes.append(f"El scan quedó **{result.status}**: puede faltar información.")
    failed = sorted({r.module for r in result.runs if r.status in ("error", "quota")})
    if failed:
        notes.append(
            "Fuentes con errores o sin cuota: " + ", ".join(f"`{m}`" for m in failed) + "."
        )
    skipped = sorted({r.module for r in result.runs if r.status == "skipped"})
    if skipped:
        notes.append("Fuentes omitidas: " + ", ".join(f"`{m}`" for m in skipped) + ".")
    return notes or ["Todas las fuentes consultadas respondieron."]


def to_attack_surface(result: ScanResult) -> str:
    """Inventario de dominios, IP, servicios, tecnologías y certificados, con los hallazgos
    priorizados."""
    index = {e.key: e for e in result.entities}
    by_type = result.by_type()
    findings = _findings(result)
    scores = {r["asset"]: r for r in risk.score(result)}

    def of(kind: EntityType) -> list[Entity]:
        return sorted(by_type.get(kind, []), key=lambda e: e.value)

    seed = [result.target] if result.target.type == EntityType.DOMAIN else []
    domains = seed + [e for e in of(EntityType.DOMAIN) if e.key != result.target.key]
    lines = [f"# Superficie de ataque — {title(result)}", ""]
    lines += [
        f"Objetivo: `{_cell(result.target.value)}` · Inicio: "
        f"{result.started_at.strftime('%Y-%m-%d %H:%M UTC')} · Estado: {result.status}",
    ]
    if result.purpose:
        lines.append(f"Propósito: {_cell(result.purpose)}")
    lines += ["", "## Resumen", ""]
    lines += _table(
        ("Concepto", "Total"),
        [
            ("Dominios y subdominios", len(domains)),
            ("Direcciones IP", len(of(EntityType.IP))),
            ("Servicios expuestos", len(of(EntityType.SERVICE))),
            ("Vulnerabilidades (CVE)", len(of(EntityType.VULNERABILITY))),
            ("Tecnologías", len(of(EntityType.TECHNOLOGY))),
            ("Certificados", len(of(EntityType.CERTIFICATE))),
            ("Hallazgos", ", ".join(f"{n} {s}" for s, n in _by_severity(findings).items()) or "0"),
        ],
    )

    lines += ["", "## Hallazgos priorizados", ""]
    lines += _table(
        ("Severidad", "Hallazgo", "Activo", "Recomendación"),
        [
            (
                f.data.get("severity", "info"),
                f.data.get("title", f.value),
                _asset_of(f, index),
                f.data.get("recommendation", ""),
            )
            for f in findings
        ],
    )

    lines += ["", "## Dominios y subdominios", ""]
    lines += _table(
        ("Dominio", "Confianza", "Riesgo"),
        [(e.value, e.confidence or "", scores.get(e.key, {}).get("score", "")) for e in domains],
    )
    lines += ["", "## Direcciones IP y servicios", ""]
    services: dict[str, list[Entity]] = {}
    for s in of(EntityType.SERVICE):
        services.setdefault(s.parent or "", []).append(s)
    lines += _table(
        ("IP", "Servicios", "Riesgo"),
        [
            (
                e.value,
                ", ".join(
                    f"{s.data.get('port', s.value)}"
                    + (f" ({s.data['product']})" if s.data.get("product") else "")
                    for s in services.get(e.key, [])
                ),
                scores.get(e.key, {}).get("score", ""),
            )
            for e in of(EntityType.IP)
        ],
    )
    lines += ["", "## Tecnologías", ""]
    lines += _table(
        ("Tecnología", "Versión", "Categoría"),
        [
            (e.value, e.data.get("version") or "", e.data.get("category") or "")
            for e in of(EntityType.TECHNOLOGY)
        ],
    )
    lines += ["", "## Certificados", ""]
    lines += _table(
        ("Huella (SHA-256)", "Emisor", "Caduca", "Estado"),
        [
            (
                e.value[:16] + "…",
                e.data.get("issuer") or "",
                e.data.get("not_after") or "",
                e.data.get("status") or "",
            )
            for e in of(EntityType.CERTIFICATE)
        ],
    )
    lines += ["", "## Límites de este inventario", ""]
    lines += [f"- {n}" for n in _limits(result)]
    lines += [
        "- Solo lista lo que las fuentes consultadas devolvieron: un activo que no aparece "
        "no es necesariamente un activo que no existe.",
    ]
    return "\n".join(lines) + "\n"


def _confidence_line(result: ScanResult) -> str:
    rated = [e for e in result.entities if e.confidence]
    if not rated:
        return "Ningún dato de este scan tiene nivel de confianza asignado."
    counts = {
        lvl: sum(1 for e in rated if e.confidence == lvl) for lvl in ("alto", "medio", "bajo")
    }
    single = sum(1 for e in rated if len(e.sources) < 2)
    return (
        f"De {len(rated)} datos valorados, {counts['alto']} tienen confianza alta, "
        f"{counts['medio']} media y {counts['bajo']} baja; {single} proceden de una sola fuente."
    )


def to_executive(result: ScanResult) -> str:
    """Resumen para quien decide: qué se encontró, qué importa, cuánto fiarse y qué no se sabe."""
    index = {e.key: e for e in result.entities}
    findings = _findings(result)
    counts = _by_severity(findings)
    urgent = counts.get("critical", 0) + counts.get("high", 0)
    assets = risk.score(result)

    lines = [f"# Informe ejecutivo — {title(result)}", ""]
    lines.append(
        f"Análisis de fuentes abiertas sobre `{_cell(result.target.value)}` realizado el "
        f"{result.started_at.strftime('%d/%m/%Y')}."
        + (f" Propósito: {_cell(result.purpose)}." if result.purpose else "")
    )
    lines += ["", "## Resumen", ""]
    lines.append(
        f"Se han identificado {len(result.entities)} datos relacionados con el objetivo y "
        f"{len(findings)} hallazgo(s)"
        + (f", de los cuales {urgent} de severidad alta o crítica." if findings else ".")
        + (
            " Conviene atender primero los marcados como críticos o altos."
            if urgent
            else " No hay hallazgos de severidad alta o crítica."
            if findings
            else ""
        )
    )
    lines += ["", "## Hallazgos clave", ""]
    key = [f for f in findings if f.data.get("severity") in KEY_SEVERITIES][:MAX_KEY_FINDINGS]
    lines += _table(
        ("Severidad", "Qué se ha visto", "Dónde", "Qué hacer"),
        [
            (
                f.data.get("severity"),
                f.data.get("title", f.value),
                _asset_of(f, index),
                f.data.get("recommendation", ""),
            )
            for f in key
        ],
    )
    hidden = sum(1 for f in findings if f.data.get("severity") in KEY_SEVERITIES) - len(key)
    if hidden > 0:
        lines.append(f"\nY {hidden} más; están en el informe completo.")
    lines += ["", "## Activos con más riesgo", ""]
    lines += _table(
        ("Activo", "Riesgo (0–100)", "Nivel", "Por qué"),
        [
            (a["asset"], a["score"], a["level"], "; ".join(a["reasons"]))
            for a in assets[:TOP_ASSETS]
        ],
    )
    lines += [
        "",
        "La nota de riesgo es una heurística para ordenar qué mirar primero, no una medida "
        "contrastada.",
        "",
        "## Nivel de confianza",
        "",
        _confidence_line(result),
    ]
    lines += hypothesis_lines(result)
    lines += ["", "## Límites del análisis", ""]
    lines += [f"- {n}" for n in _limits(result)]
    lines += [
        "- Un hallazgo es una pista a revisar, no una conclusión: confirmadlo antes de actuar.",
        "",
        "## Anexo A · Fuentes consultadas",
        "",
    ]
    runs: dict[str, dict[str, Any]] = {}
    for r in result.runs:
        row = runs.setdefault(r.module, {"ok": 0, "other": 0})
        row["ok" if r.status in ("ok", "empty") else "other"] += 1
    lines += _table(
        ("Fuente", "Consultas correctas", "Con incidencias u omitidas"),
        [(m, v["ok"], v["other"]) for m, v in sorted(runs.items())],
    )
    lines += ["", "## Anexo B · Evidencias", ""]
    lines.append(
        evidence_hint(result)
        if result.evidence
        else "Este scan no guardó evidencias (se hace con `--evidence`)."
    )
    return "\n".join(lines) + "\n"
