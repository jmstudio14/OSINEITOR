from __future__ import annotations

from html import escape

from osineitor.models import ScanResult
from osineitor.report._common import details, summary, title

CSS = """
:root { --bg:#fff; --fg:#1d1f23; --muted:#5f6670; --line:#e3e6ea; --head:#f4f6f8; --acc:#0b6bcb; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#14161a; --fg:#e6e8eb; --muted:#9aa1ab; --line:#2a2e35; --head:#1c1f24;
          --acc:#5aa9ff; }
}
body { background:var(--bg); color:var(--fg); margin:0 auto; max-width:1100px; padding:24px 16px;
       font:14px/1.5 system-ui, -apple-system, Segoe UI, sans-serif; }
h1 { font-size:20px; } h2 { font-size:16px; margin-top:32px; }
table { border-collapse:collapse; width:100%; } th, td { border:1px solid var(--line);
  padding:6px 8px; text-align:left; vertical-align:top; overflow-wrap:anywhere; }
th { background:var(--head); } .muted { color:var(--muted); } a { color:var(--acc); }
dl { margin:0; display:grid; grid-template-columns:max-content 1fr; gap:2px 10px; }
dt { color:var(--muted); } dd { margin:0; }
.error { color:#d14343; }
"""


def _value(value: str) -> str:
    if value.startswith(("http://", "https://")):
        return f'<a href="{escape(value)}" rel="noreferrer noopener">{escape(value)}</a>'
    return escape(value)


def to_html(result: ScanResult) -> str:
    out = [
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        f"<title>{escape(title(result))}</title><style>{CSS}</style></head><body>",
        f"<h1>{escape(title(result))}</h1><table>",
    ]
    out += [f"<tr><th>{escape(k)}</th><td>{escape(v)}</td></tr>" for k, v in summary(result)]
    out.append("</table>")
    for etype, entities in result.by_type().items():
        out.append(f"<h2>{escape(etype)} ({len(entities)})</h2>")
        out.append("<table><tr><th>Valor</th><th>Fuente</th><th>Detalles</th></tr>")
        for e in entities:
            info = "".join(f"<dt>{escape(k)}</dt><dd>{escape(v)}</dd>" for k, v in details(e.data))
            out.append(
                f"<tr><td>{_value(e.value)}</td><td class='muted'>{escape(e.source or '')}</td>"
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
    out.append("</body></html>")
    return "\n".join(out)
