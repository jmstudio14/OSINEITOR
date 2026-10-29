"""Cuerpo del issue del health check semanal (F1.3) a partir de `osineitor doctor --json`.

Uso:
    python scripts/doctor_issue.py doctor.json > cuerpo.md

Imprime el cuerpo solo si alguna fuente falla; si todas responden no imprime nada.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

NOTE = (
    "Comprobado desde un runner de GitHub Actions: algunas fuentes bloquean los rangos de IP de "
    "centros de datos, así que un fallo puede ser un falso positivo. Solo se prueban los módulos "
    "pasivos y sin API key. Reproduce con `osineitor doctor -m <módulo>` desde tu red."
)


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render(checks: list[dict]) -> str:
    failed = [c for c in checks if c["verdict"] == "fail"]
    if not failed:
        return ""
    rows = [f"| `{_cell(c['module'])}` | {_cell(c['detail'])} |" for c in failed]
    return "\n".join(
        [
            f"`osineitor doctor` informa de {len(failed)} fuente(s) con fallo:",
            "",
            "| Módulo | Detalle |",
            "|---|---|",
            *rows,
            "",
            NOTE,
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    checks = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    sys.stdout.write(render(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
