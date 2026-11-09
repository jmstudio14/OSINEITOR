from __future__ import annotations

from html import escape

from osineitor.models import ScanResult
from osineitor.report._common import (
    EVIDENCE_HEADERS,
    NO_EVIDENCE,
    details,
    evidence_hint,
    evidence_rows,
    seen,
    summary,
    title,
)
from osineitor.report.graph import CSS as GRAPH_CSS
from osineitor.report.graph import render_graph

CSS = """
:root { --bg:#f1f5f9; --panel:#fff; --fg:#0f172a; --muted:#475569; --line:#e2e8f0;
        --head:#f8fafc; --acc:#0369a1; --err:#b91c1c; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#0b1120; --panel:#151f32; --fg:#f1f5f9; --muted:#94a3b8; --line:#263449;
          --head:#1c2940; --acc:#38bdf8; --err:#fca5a5; }
}
body { background:var(--bg); color:var(--fg); margin:0 auto; max-width:1180px; padding:24px 16px;
       font:14px/1.5 Inter, Segoe UI, system-ui, -apple-system, sans-serif; }
h1 { font-size:20px; font-weight:600; } h2 { font-size:15px; font-weight:600; margin-top:28px; }
table { border-collapse:collapse; width:100%; background:var(--panel); }
th, td { border:1px solid var(--line);
  padding:6px 8px; text-align:left; vertical-align:top; overflow-wrap:anywhere; }
th { background:var(--head); color:var(--muted); font-size:12px; font-weight:600; }
.muted { color:var(--muted); } a { color:var(--acc); }
dl { margin:0; display:grid; grid-template-columns:max-content 1fr; gap:2px 10px; }
dt { color:var(--muted); } dd { margin:0; }
.error { color:var(--err); }
"""


def _value(value: str) -> str:
    if value.startswith(("http://", "https://")):
        return f'<a href="{escape(value)}" rel="noreferrer noopener">{escape(value)}</a>'
    return escape(value)


def to_html(result: ScanResult) -> str:
    out = [
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        f"<title>{escape(title(result))}</title><style>{CSS}{GRAPH_CSS}</style></head><body>",
        f"<h1>{escape(title(result))}</h1><table>",
    ]
    out += [f"<tr><th>{escape(k)}</th><td>{escape(v)}</td></tr>" for k, v in summary(result)]
    out.append("</table>")
    out.append(render_graph(result))
    for etype, entities in result.by_type().items():
        out.append(f"<h2>{escape(etype)} ({len(entities)})</h2>")
        out.append(
            "<table><tr><th>Valor</th><th>Fuente</th><th>Confianza</th><th>Visto</th><th>Detalles</th></tr>"
        )
        for e in entities:
            info = "".join(f"<dt>{escape(k)}</dt><dd>{escape(v)}</dd>" for k, v in details(e.data))
            sources = escape(", ".join(e.sources))
            out.append(
                f"<tr><td>{_value(e.value)}</td><td class='muted'>{sources}</td>"
                f"<td>{escape(e.confidence or '')}</td><td class='muted'>{seen(e)}</td>"
                f"<td><dl>{info}</dl></td></tr>"
            )
        out.append("</table>")
    if result.events:
        out.append("<h2>Incidencias</h2><ul>")
        for ev in result.events:
            cls = "error" if ev.kind == "error" else "muted"
            where = f" ({escape(ev.entity)})" if ev.entity else ""
            out.append(
                f"<li class='{cls}'>{escape(ev.kind)} <code>{escape(ev.module)}</code>"
                f"{where}: {escape(ev.message)}</li>"
            )
        out.append("</ul>")
    out.append("<h2>Evidencias</h2>")
    if result.evidence:
        out.append(f"<p class='muted'>{escape(evidence_hint(result))}</p><table><tr>")
        out += [f"<th>{escape(h)}</th>" for h in EVIDENCE_HEADERS]
        out.append("</tr>")
        for row in evidence_rows(result):
            cells = [
                f"<td><code>{escape(c)}</code></td>" if i in (2, 6) else f"<td>{escape(c)}</td>"
                for i, c in enumerate(row)
            ]
            out.append(f"<tr>{''.join(cells)}</tr>")
        out.append("</table>")
    else:
        out.append(f"<p class='muted'>{escape(NO_EVIDENCE)}</p>")
    out.append("</body></html>")
    return "\n".join(out)
