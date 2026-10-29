"""Línea base de falsos positivos de `username_sites` (F0.5).

Busca usernames aleatorios que no existen en ningún sitio y cuenta cuántos sitios "los
encuentran" igualmente. Cada resultado positivo es un falso positivo. Hace unas
2.000 peticiones a sitios de terceros: ejecútalo desde tu propia red.

Uso:
    python scripts/fp_baseline.py                  # 5 usernames
    python scripts/fp_baseline.py -n 10 --output reports/fp_baseline.md
"""

from __future__ import annotations

import argparse
import asyncio
import re
import secrets
import string
import sys
from collections import Counter
from pathlib import Path

from osineitor.config import Config
from osineitor.http import HttpClient
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Context
from osineitor.modules.username.sites import UsernameSites, load_sites

ALPHABET = string.ascii_lowercase + string.digits


def random_username(length: int = 14) -> str:
    """Empieza por letra para pasar los `regexCheck` más habituales."""
    return secrets.choice(string.ascii_lowercase) + "".join(
        secrets.choice(ALPHABET) for _ in range(length - 1)
    )


def evaluable_sites(username: str) -> list[str]:
    """Sitios cuya firma admite este username (no los descarta su `regexCheck`)."""
    return [
        name
        for name, site in load_sites().items()
        if not site.get("regexCheck") or re.search(site["regexCheck"], username)
    ]


def summarize(found_by_user: dict[str, list[str]], evaluable: dict[str, int]) -> dict:
    """Agrega los resultados: tasa global y sitios que fallan de forma sistemática."""
    total_checks = sum(evaluable.values())
    total_found = sum(len(sites) for sites in found_by_user.values())
    per_site = Counter(site for sites in found_by_user.values() for site in sites)
    runs = len(found_by_user)
    return {
        "usernames": runs,
        "checks": total_checks,
        "false_positives": total_found,
        "rate": total_found / total_checks if total_checks else 0.0,
        "per_username": {user: len(sites) for user, sites in found_by_user.items()},
        "systematic": sorted(site for site, n in per_site.items() if n == runs and runs > 1),
        "by_site": per_site.most_common(),
    }


def render(summary: dict) -> str:
    lines = [
        "# Línea base de falsos positivos de `username_sites`",
        "",
        f"- **Usernames inexistentes probados:** {summary['usernames']}",
        f"- **Comprobaciones evaluables:** {summary['checks']}",
        f"- **Falsos positivos:** {summary['false_positives']}",
        f"- **Tasa:** {summary['rate']:.2%}",
        "",
        "## Por username",
        "",
        "| Username | Falsos positivos |",
        "|---|---|",
    ]
    lines += [f"| `{u}` | {n} |" for u, n in summary["per_username"].items()]
    lines += ["", "## Sitios con falsos positivos", ""]
    if summary["by_site"]:
        lines += ["| Sitio | Veces |", "|---|---|"]
        lines += [f"| {site} | {n} |" for site, n in summary["by_site"]]
        if summary["systematic"]:
            lines += [
                "",
                "Fallan con **todos** los usernames (error sistemático de la firma): "
                + ", ".join(summary["systematic"]),
            ]
    else:
        lines.append("Ninguno.")
    return "\n".join(lines) + "\n"


async def measure(count: int) -> dict:
    config = Config.load()
    found_by_user: dict[str, list[str]] = {}
    evaluable: dict[str, int] = {}
    async with HttpClient(config) as http:
        module = UsernameSites(Context(config=config, http=http))
        for _ in range(count):
            username = random_username()
            entity = Entity(type=EntityType.USERNAME, value=username)
            profiles = await module.run(entity)
            found_by_user[username] = sorted(p.data["site"] for p in profiles)
            evaluable[username] = len(evaluable_sites(username))
            print(f"{username}: {len(profiles)} falsos positivos", file=sys.stderr)
    return summarize(found_by_user, evaluable)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-n", "--count", type=int, default=5, help="usernames aleatorios")
    parser.add_argument("--output", help="fichero Markdown de salida (por defecto, stdout)")
    args = parser.parse_args(argv)

    text = render(asyncio.run(measure(args.count)))
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"Escrito {path}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
