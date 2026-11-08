from __future__ import annotations

from osineitor.models import ScanResult
from osineitor.report._common import (
    EVIDENCE_HEADERS,
    NO_EVIDENCE,
    details,
    evidence_hint,
    evidence_rows,
    hypothesis_lines,
    md,
    md_code,
    seen,
    summary,
    title,
)


def to_markdown(result: ScanResult) -> str:
    lines = [f"# {md(title(result))}", "", "| Campo | Valor |", "|---|---|"]
    lines += [f"| {k} | {md(v)} |" for k, v in summary(result)]
    for etype, entities in result.by_type().items():
        lines += [
            "",
            f"## {etype} ({len(entities)})",
            "",
            "| Valor | Fuente | Confianza | Visto | Detalles |",
            "|---|---|---|---|---|",
        ]
        for e in entities:
            info = "<br>".join(f"**{k}**: {md(v)}" for k, v in details(e.data))
            sources = md(", ".join(e.sources))
            level = e.confidence or ""
            lines.append(f"| {md(e.value)} | {sources} | {level} | {seen(e)} | {info} |")
    if result.events:
        lines += ["", "## Incidencias", ""]
        lines += [
            f"- **{ev.kind}** `{ev.module}`{f' ({md(ev.entity)})' if ev.entity else ''}: "
            + md(ev.message)
            for ev in result.events
        ]
    lines += hypothesis_lines(result)
    lines += ["", "## Evidencias", ""]
    if result.evidence:
        lines += [
            evidence_hint(result),
            "",
            "| " + " | ".join(EVIDENCE_HEADERS) + " |",
            "|" + "---|" * len(EVIDENCE_HEADERS),
        ]
        for row in evidence_rows(result):
            cells = [md_code(c) if i in (2, 6) else md(c) for i, c in enumerate(row)]
            lines.append("| " + " | ".join(cells) + " |")
    else:
        lines.append(NO_EVIDENCE)
    return "\n".join(lines) + "\n"
