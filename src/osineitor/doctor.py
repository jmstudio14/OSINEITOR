"""`osineitor doctor`: comprueba que cada módulo funciona contra su fuente real."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from osineitor.config import Config
from osineitor.engine import Engine
from osineitor.http import HttpClient
from osineitor.models import Entity, detect_type
from osineitor.modules.base import Context, Module

# ok: respondió con datos · empty: respondió sin datos · fail: error o cuota
# skipped: no se probó (activo sin --active, falta la key) · unchecked: sin prueba posible
VERDICTS = ("ok", "empty", "fail", "skipped", "unchecked")


@dataclass
class Check:
    module: str
    verdict: str
    detail: str = ""
    duration_ms: int = 0
    requests: int = 0


async def _probe(http: HttpClient, cls: type[Module]) -> Check:
    """Sin valor de prueba seguro: solo se comprueba que la fuente responde."""
    try:
        response = await http.get(cls.probe_url)
    except (httpx.HTTPError, ValueError) as exc:
        return Check(cls.name, "fail", f"{cls.probe_url}: {type(exc).__name__}", requests=1)
    if response.status_code >= 500:
        return Check(cls.name, "fail", f"{cls.probe_url} respondió {response.status_code}")
    return Check(cls.name, "ok", f"alcanzable ({response.status_code}); sin prueba de datos")


async def check_module(
    cls: type[Module], config: Config, http: HttpClient, *, active: bool
) -> Check:
    if not cls.passive and not active:
        return Check(cls.name, "skipped", "módulo activo (usa --active)")
    if cls.requires_key and not config.key(cls.requires_key):
        return Check(cls.name, "skipped", f"falta la API key '{cls.requires_key}'")
    if cls.canary is None:
        if cls.probe_url:
            return await _probe(http, cls)
        return Check(cls.name, "unchecked", "sin valor de prueba")
    seed = Entity(type=detect_type(cls.canary), value=cls.canary)
    # Sin presupuesto ni caché: la prueba debe tocar la fuente real.
    engine = Engine(Context(config=config, http=http), [cls], active=active)
    result = await engine.run(seed)
    run = next((r for r in result.runs if r.entity), None)
    if run is None:
        return Check(cls.name, "skipped", result.runs[0].message if result.runs else "")
    verdict = {"ok": "ok", "empty": "empty", "skipped": "skipped"}.get(run.status, "fail")
    detail = run.message or f"{run.entities} entidades"
    return Check(cls.name, verdict, detail, run.duration_ms, run.requests)


async def run_doctor(
    config: Config,
    classes: list[type[Module]],
    *,
    active: bool = False,
    allow_private: bool = False,
    proxy: str | None = None,
) -> list[Check]:
    # Sin caché ni presupuesto: cada comprobación tiene que llegar a la fuente real.
    async with HttpClient(
        config, allow_private=allow_private, retries=1, backoff=0.5, proxy=proxy
    ) as http:
        return [await check_module(cls, config, http, active=active) for cls in classes]
