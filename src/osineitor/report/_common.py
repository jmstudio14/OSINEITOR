from __future__ import annotations

import json
import re
from typing import Any

from osineitor import resolve
from osineitor.models import Entity, ScanResult

# Lo que en Markdown abre HTML, enlaces o imágenes, código o una celda nueva.
_MD_SPECIAL = re.compile(r"([\\`\[\]<>|])")


def md(value: object) -> str:
    """Texto de terceros en Markdown: sin HTML (`<img onerror>`), enlaces (`[x](javascript:)`)
    ni saltos o `|` que cambien la estructura del documento o de la tabla."""
    return _MD_SPECIAL.sub(r"\\\1", " ".join(str(value).splitlines()))


def md_code(value: object) -> str:
    """`value` como código en línea; dentro no valen los escapes, así que el backtick se cambia."""
    return "`" + " ".join(str(value).splitlines()).replace("`", "'").replace("|", "\\|") + "`"


def fmt_value(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(map(str, value))
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def details(data: dict[str, Any]) -> list[tuple[str, str]]:
    return [(k, fmt_value(v)) for k, v in data.items() if v not in (None, "", [], {})]


def seen(entity: Entity) -> str:
    """Cuándo la vio un módulo por última vez (UTC), o vacío si el dato no tiene observaciones."""
    return entity.last_seen.strftime("%Y-%m-%d %H:%M UTC") if entity.last_seen else ""


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
    if found := [e for e in result.entities if e.type == "finding"]:
        order = ("critical", "high", "medium", "low", "info")
        counts = {s: sum(1 for e in found if e.data.get("severity") == s) for s in order}
        rows.append(("Hallazgos", ", ".join(f"{n} {s}" for s, n in counts.items() if n)))
    if result.purpose:
        rows.append(("Propósito", result.purpose))
    if result.scope:
        rows.append(("Alcance", "; ".join(f"{k}: {', '.join(v)}" for k, v in result.scope.items())))
    return rows


EVIDENCE_HEADERS = ("Módulo", "Consulta", "URL", "Fecha (UTC)", "Estado", "Bytes", "SHA-256")
NO_EVIDENCE = "Este scan no guardó evidencias (se hace con --evidence)."


def evidence_rows(result: ScanResult) -> list[tuple[str, ...]]:
    """Una fila por evidencia, en el orden de `EVIDENCE_HEADERS`. Marca las recortadas."""
    return [
        (
            ev.module,
            ev.entity or "",
            ev.url,
            ev.at.strftime("%Y-%m-%d %H:%M:%S"),
            "" if ev.status is None else str(ev.status),
            f"{ev.size} (recortada)" if ev.truncated else str(ev.size),
            ev.sha256,
        )
        for ev in result.evidence
    ]


def evidence_hint(result: ScanResult) -> str:
    """Cómo comprobar el anexo: el informe lleva los hashes, los cuerpos están en la base."""
    scan = result.scan_id if result.scan_id else "N"
    return (
        f"Huella del conjunto: {result.evidence_digest}. Los cuerpos no van en el informe: están "
        f"en la base de datos y `osineitor verify {scan}` recalcula estos hashes "
        f"(`--digest HUELLA` compara con la huella anotada fuera de la base)."
    )


def hypothesis_lines(result: ScanResult) -> list[str]:
    """Sección Markdown de resolución de entidades; vacía si no hay hipótesis."""
    found = resolve.hypotheses(result)
    if not found:
        return []

    lines = [
        "",
        "## Hipótesis de identidad",
        "",
        "Cuentas que podrían ser de la misma persona. Son hipótesis con su evidencia, no una "
        "identidad confirmada: dos cuentas con el mismo username o nombre pueden ser de personas "
        "distintas.",
        "",
        "| Puntuación | Cuentas | Señales |",
        "|---|---|---|",
    ]
    for h in found:
        signals = "; ".join(f"{s['kind']}: {s['value']}" for s in h["signals"])
        lines.append(f"| {h['score']} | {md(', '.join(h['accounts']))} | {md(signals)} |")
    return lines
