from __future__ import annotations

from osineitor.models import ScanResult
from osineitor.report._common import details, summary, title


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def to_markdown(result: ScanResult) -> str:
    lines = [f"# {title(result)}", "", "| Campo | Valor |", "|---|---|"]
    lines += [f"| {k} | {_cell(v)} |" for k, v in summary(result)]
    for etype, entities in result.by_type().items():
        lines += [
            "",
            f"## {etype} ({len(entities)})",
            "",
            "| Valor | Fuente | Detalles |",
            "|---|---|---|",
        ]
        for e in entities:
            info = "<br>".join(f"**{k}**: {_cell(v)}" for k, v in details(e.data))
            lines.append(f"| {_cell(e.value)} | {e.source or ''} | {info} |")
    if result.events:
        lines += ["", "## Incidencias", ""]
        lines += [
            f"- **{ev.kind}** `{ev.module}`{f' ({ev.entity})' if ev.entity else ''}: {ev.message}"
            for ev in result.events
        ]
    return "\n".join(lines) + "\n"
