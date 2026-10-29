"""Genera docs/RDAP_COBERTURA.md a partir del bootstrap RDAP de IANA (F0.6).

Uso:
    python scripts/rdap_coverage.py                       # descarga dns.json de IANA
    python scripts/rdap_coverage.py --input dns.json      # usa una copia local
    python scripts/rdap_coverage.py --output docs/RDAP_COBERTURA.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

IANA_URL = "https://data.iana.org/rdap/dns.json"

# TLD frecuentes que se muestran siempre en la tabla principal, con y sin RDAP.
COMMON_TLDS = [
    "com",
    "net",
    "org",
    "info",
    "biz",
    "eu",
    "es",
    "io",
    "de",
    "fr",
    "uk",
    "it",
    "nl",
    "pt",
    "be",
    "ch",
    "at",
    "se",
    "no",
    "dk",
    "fi",
    "pl",
    "cz",
    "gr",
    "ie",
    "us",
    "ca",
    "mx",
    "br",
    "ar",
    "cl",
    "co",
    "pe",
    "ve",
    "uy",
    "ec",
    "au",
    "nz",
    "jp",
    "cn",
    "in",
    "ru",
    "tr",
    "xyz",
    "app",
    "dev",
    "online",
    "site",
    "shop",
    "me",
    "tv",
    "cc",
    "ai",
]


def load(source: str | Path | None) -> dict:
    if source:
        return json.loads(Path(source).read_text(encoding="utf-8"))
    response = httpx.get(IANA_URL, timeout=30, follow_redirects=True)
    response.raise_for_status()
    return response.json()


def tld_servers(data: dict) -> dict[str, list[str]]:
    """TLD (sin punto, minúsculas) → URLs del servidor RDAP."""
    servers: dict[str, list[str]] = {}
    for tlds, urls in data["services"]:
        for tld in tlds:
            servers[tld.lower()] = urls
    return servers


def render(data: dict, source: str) -> str:
    servers = tld_servers(data)
    published = data.get("publication", "desconocida")
    lines = [
        "# Cobertura RDAP por TLD",
        "",
        "Generado con `scripts/rdap_coverage.py` (entregable F0.6 del [roadmap](../ROADMAP.md)).",
        "",
        f"- **Fuente:** {source}",
        f"- **Publicación del bootstrap:** {published}",
        f"- **TLD con servidor RDAP:** {len(servers)}",
        "",
        "El módulo `rdap` consulta rdap.org, que redirige al servidor RDAP del TLD según este "
        "bootstrap. **Si el TLD no aparece aquí, el módulo no puede obtener datos de registro** "
        "y hoy devuelve un resultado vacío sin avisar. Se corrige en F1.18, y el WHOIS de "
        "respaldo para esos TLD llega con F4.11.",
        "",
        "## TLD frecuentes",
        "",
        "| TLD | RDAP | Servidor |",
        "|---|---|---|",
    ]
    for tld in COMMON_TLDS:
        urls = servers.get(tld)
        lines.append(f"| `.{tld}` | {'sí' if urls else '**no**'} | {urls[0] if urls else '-'} |")

    missing = [t for t in COMMON_TLDS if t not in servers]
    lines += [
        "",
        f"Sin RDAP entre los {len(COMMON_TLDS)} TLD de la tabla: {len(missing)} "
        f"({', '.join(f'`.{t}`' for t in missing) or 'ninguno'}).",
        "",
        "<details>",
        f"<summary>Los {len(servers)} TLD con RDAP</summary>",
        "",
        ", ".join(f"`{t}`" for t in sorted(servers)),
        "",
        "</details>",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", help="copia local de dns.json (por defecto, descarga de IANA)")
    parser.add_argument("--output", help="fichero de salida (por defecto, stdout)")
    args = parser.parse_args(argv)

    data = load(args.input)
    source = IANA_URL + (f" (copia local `{Path(args.input).name}`)" if args.input else "")
    text = render(data, source)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Escrito {args.output}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
