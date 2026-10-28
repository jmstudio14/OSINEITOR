"""Orquestador: ejecuta los módulos que consumen cada entidad y pivotea por niveles."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from datetime import UTC, datetime

from osineitor.models import Entity, ScanEvent, ScanResult
from osineitor.modules.base import Context, Module, ModuleError


class Engine:
    def __init__(
        self,
        ctx: Context,
        module_classes: Iterable[type[Module]],
        *,
        depth: int = 1,
        active: bool = False,
        concurrency: int = 10,
        on_entity: Callable[[Entity], None] | None = None,
    ) -> None:
        self.depth = max(depth, 1)
        self.on_entity = on_entity
        self._sem = asyncio.Semaphore(concurrency)
        self.modules: list[Module] = []
        self.skipped: list[ScanEvent] = []
        for cls in module_classes:
            if not cls.passive and not active:
                self.skipped.append(
                    ScanEvent(
                        kind="skipped", module=cls.name, message="módulo activo (usa --active)"
                    )
                )
            elif cls.requires_key and not ctx.config.key(cls.requires_key):
                self.skipped.append(
                    ScanEvent(
                        kind="skipped",
                        module=cls.name,
                        message=f"falta la API key '{cls.requires_key}'",
                    )
                )
            else:
                self.modules.append(cls(ctx))

    async def run(self, seed: Entity) -> ScanResult:
        result = ScanResult(target=seed, depth=self.depth, events=list(self.skipped))
        index: dict[str, Entity] = {seed.key: seed}
        layer = [seed]
        for _ in range(self.depth):
            jobs = [(m, e) for e in layer for m in self.modules if m.accepts(e)]
            outputs = await asyncio.gather(*(self._run_one(m, e, result) for m, e in jobs))
            layer = []
            for produced in outputs:
                for entity in produced:
                    existing = index.get(entity.key)
                    if existing is not None:
                        # Misma entidad desde otra fuente: completa los datos que falten.
                        for k, v in entity.data.items():
                            if existing.data.get(k) in (None, "", [], {}):
                                existing.data[k] = v
                        continue
                    index[entity.key] = entity
                    result.entities.append(entity)
                    layer.append(entity)
                    if self.on_entity:
                        self.on_entity(entity)
            if not layer:
                break
        result.finished_at = datetime.now(UTC)
        return result

    async def _run_one(self, module: Module, entity: Entity, result: ScanResult) -> list[Entity]:
        async with self._sem:
            try:
                return await module.run(entity)
            except ModuleError as exc:
                message = str(exc)
            except Exception as exc:  # un módulo roto no debe tumbar el scan
                message = f"{type(exc).__name__}: {exc}"
        result.events.append(
            ScanEvent(kind="error", module=module.name, message=message, entity=entity.key)
        )
        return []
