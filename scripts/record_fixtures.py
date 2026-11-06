"""Graba las respuestas reales de un módulo como fixtures para los tests (F0.2).

Ejecuta UN módulo contra UN objetivo público y guarda cada respuesta HTTP (y cada respuesta del
resolvedor DNS) en `tests/fixtures/<módulo>/<caso>.json`. Hace peticiones reales: usa solo
objetivos públicos de prueba (`github.com`, `1.1.1.1`, `test@example.com`), nunca datos tuyos.

Se anonimiza al grabar: de cada respuesta se conservan el método, la URL, el estado, el cuerpo y
las cabeceras de respuesta (`http_fingerprint` las necesita) salvo las cookies y las que describen
la codificación del cuerpo; no se guardan cabeceras de petición ni ningún otro dato del equipo.

Uso:
    python scripts/record_fixtures.py rdap github.com
    python scripts/record_fixtures.py username_sites octocat --sites GitHub,GitLab --name existe
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from dns.asyncresolver import Resolver

from osineitor import registry
from osineitor.config import Config
from osineitor.http import HttpClient
from osineitor.models import Entity, detect_type
from osineitor.modules.base import Context

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
DROP_HEADERS = {"set-cookie", "content-encoding", "content-length", "transfer-encoding"}
MAX_BODY = 512 * 1024


class RecordingTransport(httpx.AsyncBaseTransport):
    """Reenvía la petición a la red y se queda con una copia anonimizada de la respuesta."""

    def __init__(self, inner: httpx.AsyncBaseTransport | None = None) -> None:
        self._inner = inner or httpx.AsyncHTTPTransport()
        self.calls: list[dict[str, Any]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        body = await response.aread()
        if len(body) > MAX_BODY:
            raise ValueError(
                f"{request.url}: respuesta de {len(body)} bytes; elige un objetivo menor"
            )
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"{request.url}: el cuerpo no es UTF-8, no se puede grabar") from exc
        headers = {k: v for k, v in response.headers.items() if k.lower() not in DROP_HEADERS}
        self.calls.append(
            {
                "method": request.method,
                "url": str(request.url),
                "status": response.status_code,
                "headers": headers,
                "body": text,
            }
        )
        # La copia no lleva `content-encoding`: el cuerpo ya está descomprimido.
        return httpx.Response(response.status_code, headers=headers, content=body, request=request)


class RecordingResolver:
    """Envuelve al resolvedor real y guarda los valores de cada respuesta afirmativa."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.calls: list[dict[str, Any]] = []

    async def resolve(self, name: str, rtype: str, lifetime: float | None = None) -> Any:
        answer = await self._inner.resolve(name, rtype, lifetime=lifetime)
        values = [
            b"".join(rdata.strings).decode(errors="replace") if rtype == "TXT" else rdata.to_text()
            for rdata in answer
        ]
        self.calls.append({"name": name, "type": rtype, "values": values})
        return answer


def pick_module(name: str, sites: list[str] | None):
    for cls in registry.discover():
        if cls.name == name:
            break
    else:
        raise SystemExit(f"módulo desconocido: {name}")
    if cls.requires_key:
        raise SystemExit(f"{name} necesita API key: no se graba sin ella")
    if not sites:
        return cls

    class Subset(cls):  # type: ignore[misc, valid-type]
        def sites(self) -> dict[str, Any]:
            every = super().sites()
            missing = [s for s in sites if s not in every]
            if missing:
                raise SystemExit(f"sitios que no están en las firmas: {', '.join(missing)}")
            return {s: every[s] for s in sites}

    return Subset


async def record(module_name: str, target: str, sites: list[str] | None) -> dict[str, Any]:
    config = Config.load()
    transport = RecordingTransport()
    async with HttpClient(config, transport=transport) as http:
        resolver = RecordingResolver(Resolver())
        module = pick_module(module_name, sites)(
            Context(config=config, http=http, resolver=resolver)
        )
        entity = Entity(type=detect_type(target), value=target)
        if not module.accepts(entity):
            raise SystemExit(f"{module_name} no acepta {target!r} ({entity.type.value})")
        out = await module.run(entity)
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for call in transport.calls:
        unique.setdefault((call["method"], call["url"]), call)
    return {
        "module": module_name,
        "target": target,
        "recorded": date.today().isoformat(),
        "entities": len(out),
        "sites": sites or None,
        "http": list(unique.values()),
        "dns": resolver.calls,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("module")
    parser.add_argument("target")
    parser.add_argument("--name", default="real", help="nombre del caso (por defecto, «real»)")
    parser.add_argument("--sites", help="solo username_sites: sitios separados por comas")
    args = parser.parse_args(argv)

    sites = [s.strip() for s in args.sites.split(",")] if args.sites else None
    fixture = asyncio.run(record(args.module, args.target, sites))
    path = FIXTURES / args.module / f"{args.name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"Escrito {path} ({len(fixture['http'])} peticiones HTTP, "
        f"{len(fixture['dns'])} consultas DNS, {fixture['entities']} entidades)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
