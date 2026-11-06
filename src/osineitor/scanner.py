"""API de librería: lanzar un scan desde Python sin pasar por la CLI.

    from osineitor import Scanner

    result = Scanner(depth=2).scan("example.com")          # síncrona
    result = await Scanner(depth=2).ascan("example.com")   # asíncrona (dentro de un bucle asyncio)

Es la misma maquinaria que usa `osineitor scan`: módulos incluidos y de plugins, guardia de red,
presupuesto, caché, alcance y evidencias. Un scan no se guarda en la base de datos: el
`ScanResult` que devuelve se puede guardar con `osineitor.storage.Storage` o exportar con
`osineitor.report.render`. Ver `docs/API.md`.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Iterable
from typing import Any

from pydantic import ValidationError

from osineitor import registry
from osineitor.budget import (
    DEFAULT_MAX_ENTITIES,
    DEFAULT_MAX_REQUESTS,
    DEFAULT_MAX_SECONDS,
    Budget,
)
from osineitor.cache import ResponseCache
from osineitor.config import Config
from osineitor.engine import Engine
from osineitor.errors import InvalidEntityValue
from osineitor.http import HttpClient
from osineitor.models import Entity, EntityType, ScanResult, decompose, detect_type
from osineitor.modules.base import Context
from osineitor.scope import Scope

MAX_PURPOSE = 500
# Tipos que identifican a una persona: con `require_purpose` activo exigen declarar el propósito.
PURPOSE_REQUIRED_FOR = (
    EntityType.EMAIL,
    EntityType.USERNAME,
    EntityType.PERSON,
    EntityType.PHONE,
)


class ScanInputError(ValueError):
    """La petición no es válida (objetivo, módulos, alcance o propósito): no se llegó a escanear."""


class Scanner:
    """Configura un scan y lo ejecuta. Un `Scanner` se puede reutilizar, pero no ejecutar dos
    scans a la vez; para escanear en paralelo, crea un `Scanner` por scan.

    Los límites (`max_*`) valen `None` para «sin límite». `only` restringe a esos módulos por
    nombre. `on_entity` recibe cada entidad nueva y `on_event`, los eventos del contrato de la CLI
    (`osineitor.events`); ambos se llaman en el hilo del scan.
    """

    def __init__(
        self,
        *,
        depth: int = 1,
        active: bool = False,
        only: Iterable[str] | None = None,
        max_entities: int | None = DEFAULT_MAX_ENTITIES,
        max_requests: int | None = DEFAULT_MAX_REQUESTS,
        max_seconds: float | None = DEFAULT_MAX_SECONDS,
        allow_private: bool = False,
        use_cache: bool = True,
        refresh: bool = False,
        proxy: str | None = None,
        evidence: bool = False,
        scope: Scope | None = None,
        purpose: str | None = None,
        config: Config | None = None,
        on_entity: Callable[[Entity], None] | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        if purpose is not None and (
            not purpose or len(purpose) > MAX_PURPOSE or any(c in purpose for c in "\r\n\x00")
        ):
            raise ScanInputError(
                f"el propósito debe tener entre 1 y {MAX_PURPOSE} caracteres, sin saltos de línea"
            )
        self.depth = depth
        self.active = active
        self.only = list(only) if only is not None else None
        self.max_entities = max_entities
        self.max_requests = max_requests
        self.max_seconds = max_seconds
        self.allow_private = allow_private
        self.use_cache = use_cache
        self.refresh = refresh
        self.proxy = proxy
        self.evidence = evidence
        self.scope = scope
        self.purpose = purpose
        self.config = config
        self.on_entity = on_entity
        self.on_event = on_event
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._engine: Engine | None = None

    def scan(self, target: str, type: EntityType | str | None = None) -> ScanResult:
        """Escanea `target` y devuelve el resultado. No se puede llamar desde un bucle asyncio en
        marcha (usa `ascan`)."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.ascan(target, type))
        raise RuntimeError("hay un bucle asyncio en marcha: usa `await scanner.ascan(...)`")

    async def ascan(self, target: str, type: EntityType | str | None = None) -> ScanResult:
        """Como `scan`, para llamarla con `await`. Sin `type`, se deduce de `target`."""
        seed = self._seed(target, type)
        config = self.config or Config.load()
        classes = self._modules()
        if seed.type in PURPOSE_REQUIRED_FOR and not self.purpose and config.purpose_required():
            raise ScanInputError(f"los scans de {seed.type} exigen un propósito (require_purpose)")
        if self.scope and not self.scope.allows(seed):
            raise ScanInputError(f"el objetivo {seed.key} está fuera del alcance declarado")
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("este Scanner ya está ejecutando un scan")
        try:
            budget = Budget(
                max_entities=self.max_entities,
                max_requests=self.max_requests,
                max_seconds=self.max_seconds,
            )
            # Una evidencia es una captura fresca: una respuesta cacheada no tiene fecha original.
            cache = ResponseCache() if self.use_cache and not self.evidence else None
            async with HttpClient(
                config,
                allow_private=self.allow_private,
                budget=budget,
                cache=cache,
                refresh=self.refresh,
                proxy=self.proxy,
            ) as http:
                engine = Engine(
                    Context(config=config, http=http),
                    classes,
                    depth=self.depth,
                    active=self.active,
                    on_entity=self.on_entity,
                    budget=budget,
                    on_event=self.on_event,
                    evidence=self.evidence,
                    scope=self.scope,
                    purpose=self.purpose,
                )
                self._loop, self._engine = asyncio.get_running_loop(), engine
                return await engine.run(seed)
        finally:
            self._loop = self._engine = None
            self._lock.release()

    def cancel(self) -> None:
        """Detiene el scan en curso conservando lo ya recogido (`result.status == "cancelled"`).
        Se puede llamar desde otro hilo; sin scan en curso no hace nada."""
        loop, engine = self._loop, self._engine
        if loop is not None and engine is not None:
            loop.call_soon_threadsafe(engine.cancel)

    def _seed(self, target: str, type: EntityType | str | None) -> Entity:
        try:
            kind = EntityType(type) if type is not None else detect_type(target)
            seed = Entity(type=kind, value=target.strip())
            decompose(seed)  # de una URL se investiga su host: que sea válido
        except ValidationError as exc:
            reason = exc.errors()[0]["msg"].removeprefix("Value error, ")
            raise ScanInputError(reason) from exc
        except (InvalidEntityValue, ValueError) as exc:
            raise ScanInputError(str(exc)) from exc
        return seed

    def _modules(self) -> list[type]:
        classes = registry.discover()
        if self.only is None:
            return classes
        unknown = set(self.only) - {m.name for m in classes}
        if unknown:
            raise ScanInputError(f"módulos desconocidos: {', '.join(sorted(unknown))}")
        return [m for m in classes if m.name in self.only]
