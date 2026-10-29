"""Interfaz de línea de comandos."""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from osineitor import __version__, registry, report
from osineitor.budget import (
    DEFAULT_MAX_ENTITIES,
    DEFAULT_MAX_REQUESTS,
    DEFAULT_MAX_SECONDS,
    Budget,
)
from osineitor.cache import ResponseCache, default_cache_path
from osineitor.config import Config, config_dir, config_path
from osineitor.doctor import run_doctor
from osineitor.engine import Engine
from osineitor.http import HttpClient
from osineitor.models import Entity, EntityType, ScanResult, detect_type
from osineitor.modules.base import Context
from osineitor.storage import Storage, StorageError

LEGAL_NOTICE = (
    "OSINEITOR solo consulta fuentes abiertas. Úsalo sobre objetivos propios o con autorización "
    "expresa. Investigar a personas físicas está sujeto al RGPD y a la legislación local: "
    "tú eres responsable del uso que hagas de la herramienta."
)

app = typer.Typer(help="Herramienta OSINT modular.\n\n" + LEGAL_NOTICE, no_args_is_help=True)
config_app = typer.Typer(help="Gestiona API keys y ajustes.", no_args_is_help=True)
app.add_typer(config_app, name="config")
cache_app = typer.Typer(help="Caché de respuestas HTTP.", no_args_is_help=True)
app.add_typer(cache_app, name="cache")
console = Console()

Depth = Annotated[
    int,
    typer.Option("--depth", "-d", min=1, max=4, help="Niveles de pivoteo (1 = solo el objetivo)."),
]
Active = Annotated[
    bool, typer.Option("--active", help="Permite módulos que contactan al objetivo.")
]
Only = Annotated[
    list[str] | None, typer.Option("--module", "-m", help="Ejecuta solo estos módulos (repetible).")
]
NoSave = Annotated[bool, typer.Option("--no-save", help="No guarda el scan en la base de datos.")]
AsJson = Annotated[bool, typer.Option("--json", help="Imprime el resultado en JSON.")]
DbPath = Annotated[Path | None, typer.Option("--db", help="Ruta de la base de datos SQLite.")]
MaxEntities = Annotated[
    int,
    typer.Option("--max-entities", min=0, help="Tope de entidades (0 = sin límite)."),
]
MaxRequests = Annotated[
    int,
    typer.Option("--max-requests", min=0, help="Tope de peticiones HTTP (0 = sin límite)."),
]
MaxTime = Annotated[
    float,
    typer.Option("--max-time", min=0, help="Tope de segundos del scan (0 = sin límite)."),
]
AllowPrivate = Annotated[
    bool,
    typer.Option(
        "--allow-private",
        help="Permite conectar con IPs privadas, loopback y metadatos cloud (bloqueadas).",
    ),
]
NoCache = Annotated[
    bool, typer.Option("--no-cache", help="No lee ni guarda la caché de respuestas HTTP.")
]
Refresh = Annotated[
    bool, typer.Option("--refresh", help="Ignora lo cacheado y vuelve a consultar las fuentes.")
]


@dataclass
class ScanOptions:
    depth: int
    active: bool
    only: list[str] | None
    max_entities: int
    max_requests: int
    max_time: float
    allow_private: bool
    no_cache: bool = False
    refresh: bool = False


def _force_utf8() -> None:
    """Salida siempre en UTF-8.

    En Windows, si la salida va a una tubería (otro programa que lanza la CLI) Python usa la
    codificación local (cp1252) y un solo carácter como `✓` o una letra cirílica en un perfil
    provoca un `UnicodeEncodeError`. Los caracteres no representables se sustituyen.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


@app.callback()
def main() -> None:
    # Se ejecuta antes de cada orden. Sin docstring: el texto de ayuda está en `typer.Typer`.
    _force_utf8()


def _open_storage(db: Path | None) -> Storage:
    try:
        return Storage(db)
    except StorageError as exc:
        raise typer.BadParameter(str(exc)) from exc


def _show_notice_once() -> None:
    marker = config_dir() / ".notice_shown"
    if marker.exists():
        return
    console.print(f"[yellow]Aviso:[/] {LEGAL_NOTICE}\n")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()


def _select_modules(only: list[str] | None) -> list[type]:
    classes = registry.discover()
    if not only:
        return classes
    names = {m.name for m in classes}
    unknown = set(only) - names
    if unknown:
        raise typer.BadParameter(f"módulos desconocidos: {', '.join(sorted(unknown))}")
    return [m for m in classes if m.name in only]


async def _scan(seed: Entity, opts: ScanOptions, live: bool) -> ScanResult:
    config = Config.load()
    budget = Budget.from_limits(opts.max_entities, opts.max_requests, opts.max_time)
    cache = None if opts.no_cache else ResponseCache()
    async with HttpClient(
        config, allow_private=opts.allow_private, budget=budget, cache=cache, refresh=opts.refresh
    ) as http:
        ctx = Context(config=config, http=http)
        engine = Engine(
            ctx,
            _select_modules(opts.only),
            depth=opts.depth,
            active=opts.active,
            on_entity=_print_entity if live else None,
            budget=budget,
        )
        return await engine.run(seed)


def _print_entity(entity: Entity) -> None:
    console.print(f"  [cyan]{entity.type:<13}[/] {escape(entity.value)}  [dim]({entity.source})[/]")


def _summarize(entity: Entity) -> str:
    parts = []
    for key, value in entity.data.items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, list):
            value = ", ".join(map(str, value[:8])) + (" …" if len(value) > 8 else "")
        elif isinstance(value, dict):
            value = json.dumps(value, ensure_ascii=False)[:120]
        parts.append(f"{key}={value}")
    return "; ".join(parts)[:300]


def render(result: ScanResult) -> None:
    title = f"{result.target.type}: {result.target.value}"
    if result.scan_id:
        title += f"  (scan #{result.scan_id})"
    console.rule(title)
    for etype, entities in result.by_type().items():
        table = Table(title=f"{etype} ({len(entities)})", title_justify="left", expand=True)
        table.add_column("Valor", overflow="fold", ratio=2)
        table.add_column("Fuente", ratio=1)
        table.add_column("Detalles", overflow="fold", ratio=4)
        for e in entities:
            table.add_row(e.value, e.source or "", _summarize(e))
        console.print(table)
    if not result.entities:
        console.print("[dim]Sin resultados.[/]")
    _render_runs(result)
    for ev in result.events:
        color = {"error": "red", "budget": "yellow"}.get(ev.kind, "dim")
        where = f" ({ev.entity})" if ev.entity else ""
        console.print(f"[{color}]{ev.kind}: {ev.module}{where}: {escape(ev.message)}[/]")
    if result.truncated:
        console.print(
            "[yellow]Resultado incompleto: el scan se detuvo al agotar su presupuesto.[/]"
        )


def _render_runs(result: ScanResult) -> None:
    """Una línea por módulo: distingue «sin datos» de «falló» y muestra el coste."""
    if not result.runs:
        return
    by_module: dict[str, list] = {}
    for run in result.runs:
        by_module.setdefault(run.module, []).append(run)
    table = Table(title="Módulos", title_justify="left")
    table.add_column("Módulo", no_wrap=True)
    table.add_column("Estado")
    for col in ("Entidades", "Peticiones", "Caché", "Tiempo"):
        table.add_column(col, justify="right")
    for module, runs in sorted(by_module.items()):
        counts: dict[str, int] = {}
        for run in runs:
            counts[run.status] = counts.get(run.status, 0) + 1
        status = " ".join(f"{_STATUS_STYLE.get(k, '')}{k}[/]×{n}" for k, n in counts.items())
        table.add_row(
            module,
            status,
            str(sum(r.entities for r in runs)),
            str(sum(r.requests for r in runs)),
            str(sum(r.cache_hits for r in runs)),
            f"{sum(r.duration_ms for r in runs) / 1000:.1f} s",
        )
    console.print(table)


_STATUS_STYLE = {
    "ok": "[green]",
    "empty": "[dim]",
    "error": "[red]",
    "quota": "[yellow]",
    "skipped": "[dim]",
}


def _make_seed(etype: EntityType, value: str) -> Entity:
    """Crea la entidad semilla; un valor no válido es un error de uso, no un traceback."""
    try:
        return Entity(type=etype, value=value.strip())
    except ValidationError as exc:
        reason = exc.errors()[0]["msg"].removeprefix("Value error, ")
        raise typer.BadParameter(reason) from exc


def _run_target(
    etype: EntityType,
    value: str,
    opts: ScanOptions,
    no_save: bool,
    as_json: bool,
    db: Path | None,
) -> None:
    seed = _make_seed(etype, value)
    if not as_json:
        _show_notice_once()
        console.print(f"[bold]Escaneando {etype} {seed.value}[/] (profundidad {opts.depth})")
    result = asyncio.run(_scan(seed, opts, live=not as_json))
    if not no_save:
        with _open_storage(db) as storage:
            storage.save(result)
    if as_json:
        print(result.model_dump_json(indent=2))
    else:
        render(result)


@app.command()
def domain(
    target: str,
    depth: Depth = 1,
    active: Active = False,
    module: Only = None,
    no_save: NoSave = False,
    json_out: AsJson = False,
    db: DbPath = None,
    max_entities: MaxEntities = DEFAULT_MAX_ENTITIES,
    max_requests: MaxRequests = DEFAULT_MAX_REQUESTS,
    max_time: MaxTime = DEFAULT_MAX_SECONDS,
    allow_private: AllowPrivate = False,
    no_cache: NoCache = False,
    refresh: Refresh = False,
) -> None:
    """Investiga un dominio: RDAP/WHOIS, DNS, subdominios, histórico web."""
    opts = ScanOptions(
        depth,
        active,
        module,
        max_entities,
        max_requests,
        max_time,
        allow_private,
        no_cache,
        refresh,
    )
    _run_target(EntityType.DOMAIN, target, opts, no_save, json_out, db)


@app.command()
def ip(
    target: str,
    depth: Depth = 1,
    active: Active = False,
    module: Only = None,
    no_save: NoSave = False,
    json_out: AsJson = False,
    db: DbPath = None,
    max_entities: MaxEntities = DEFAULT_MAX_ENTITIES,
    max_requests: MaxRequests = DEFAULT_MAX_REQUESTS,
    max_time: MaxTime = DEFAULT_MAX_SECONDS,
    allow_private: AllowPrivate = False,
    no_cache: NoCache = False,
    refresh: Refresh = False,
) -> None:
    """Investiga una IP: geolocalización, puertos/servicios, reputación."""
    opts = ScanOptions(
        depth,
        active,
        module,
        max_entities,
        max_requests,
        max_time,
        allow_private,
        no_cache,
        refresh,
    )
    _run_target(EntityType.IP, target, opts, no_save, json_out, db)


@app.command()
def email(
    target: str,
    depth: Depth = 1,
    active: Active = False,
    module: Only = None,
    no_save: NoSave = False,
    json_out: AsJson = False,
    db: DbPath = None,
    max_entities: MaxEntities = DEFAULT_MAX_ENTITIES,
    max_requests: MaxRequests = DEFAULT_MAX_REQUESTS,
    max_time: MaxTime = DEFAULT_MAX_SECONDS,
    allow_private: AllowPrivate = False,
    no_cache: NoCache = False,
    refresh: Refresh = False,
) -> None:
    """Investiga un email: validez, perfiles asociados, filtraciones."""
    opts = ScanOptions(
        depth,
        active,
        module,
        max_entities,
        max_requests,
        max_time,
        allow_private,
        no_cache,
        refresh,
    )
    _run_target(EntityType.EMAIL, target, opts, no_save, json_out, db)


@app.command()
def username(
    target: str,
    depth: Depth = 1,
    active: Active = False,
    module: Only = None,
    no_save: NoSave = False,
    json_out: AsJson = False,
    db: DbPath = None,
    max_entities: MaxEntities = DEFAULT_MAX_ENTITIES,
    max_requests: MaxRequests = DEFAULT_MAX_REQUESTS,
    max_time: MaxTime = DEFAULT_MAX_SECONDS,
    allow_private: AllowPrivate = False,
    no_cache: NoCache = False,
    refresh: Refresh = False,
) -> None:
    """Busca un nombre de usuario en cientos de sitios."""
    opts = ScanOptions(
        depth,
        active,
        module,
        max_entities,
        max_requests,
        max_time,
        allow_private,
        no_cache,
        refresh,
    )
    _run_target(EntityType.USERNAME, target, opts, no_save, json_out, db)


@app.command()
def scan(
    target: str,
    depth: Depth = 2,
    active: Active = False,
    module: Only = None,
    no_save: NoSave = False,
    json_out: AsJson = False,
    db: DbPath = None,
    max_entities: MaxEntities = DEFAULT_MAX_ENTITIES,
    max_requests: MaxRequests = DEFAULT_MAX_REQUESTS,
    max_time: MaxTime = DEFAULT_MAX_SECONDS,
    allow_private: AllowPrivate = False,
    no_cache: NoCache = False,
    refresh: Refresh = False,
) -> None:
    """Detecta el tipo de objetivo y pivota entre frentes (profundidad 2 por defecto)."""
    opts = ScanOptions(
        depth,
        active,
        module,
        max_entities,
        max_requests,
        max_time,
        allow_private,
        no_cache,
        refresh,
    )
    _run_target(detect_type(target), target, opts, no_save, json_out, db)


@app.command("modules")
def list_modules() -> None:
    """Lista los módulos disponibles y su estado."""
    config = Config.load()
    table = Table()
    table.add_column("Módulo", no_wrap=True)
    for col in ("Consume", "Produce", "Tipo", "API key", "Descripción"):
        table.add_column(col, overflow="fold")
    for m in registry.discover():
        if m.requires_key:
            key = (
                f"[green]{m.requires_key} ✓[/]"
                if config.key(m.requires_key)
                else f"[red]{m.requires_key} ✗[/]"
            )
        else:
            key = "-"
        table.add_row(
            m.name,
            ", ".join(sorted(m.consumes)),
            ", ".join(sorted(m.produces)),
            "pasivo" if m.passive else "[yellow]activo[/]",
            key,
            m.description,
        )
    console.print(table)


@app.command()
def history(limit: int = 20, db: DbPath = None) -> None:
    """Muestra los últimos scans guardados."""
    table = Table("ID", "Tipo", "Objetivo", "Entidades", "Fecha")
    with _open_storage(db) as storage:
        for scan_id, ttype, target, count, started in storage.list_scans(limit):
            table.add_row(str(scan_id), ttype, target, str(count), started[:19])
    console.print(table)


@app.command()
def show(scan_id: int, db: DbPath = None) -> None:
    """Muestra un scan guardado."""
    with _open_storage(db) as storage:
        result = storage.load(scan_id)
    if result is None:
        raise typer.BadParameter(f"no existe el scan {scan_id}")
    render(result)


@app.command()
def export(
    scan_id: int,
    fmt: Annotated[str, typer.Option("--format", "-f", help="json, md o html.")] = "html",
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Fichero de salida.")
    ] = None,
    db: DbPath = None,
) -> None:
    """Exporta un scan guardado a JSON, Markdown o HTML."""
    if fmt not in report.FORMATS:
        raise typer.BadParameter(f"formato no soportado: {fmt}")
    with _open_storage(db) as storage:
        result = storage.load(scan_id)
    if result is None:
        raise typer.BadParameter(f"no existe el scan {scan_id}")
    ext = report.FORMATS[fmt][0]
    output = output or Path("reports") / f"osineitor-{scan_id}-{result.target.value}.{ext}"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.render(result, fmt), encoding="utf-8")
    console.print(f"Informe guardado en {output}")


@config_app.command("set")
def config_set(name: str, value: str) -> None:
    """Guarda una API key (p. ej. `osineitor config set shodan TU_KEY`)."""
    config = Config.load()
    config.keys[name.lower()] = value
    path = config.save()
    console.print(f"Key '{name.lower()}' guardada en {path}")


@config_app.command("show")
def config_show() -> None:
    """Muestra las keys configuradas (enmascaradas)."""
    config = Config.load()
    console.print(f"Fichero: {config_path()}")
    if not config.keys:
        console.print(
            "[dim]No hay keys en el fichero (también puedes usar OSINEITOR_<NOMBRE>_KEY).[/]"
        )
    for name, value in sorted(config.keys.items()):
        console.print(f"  {name} = {value[:4]}{'*' * max(len(value) - 4, 0)}")


@app.command()
def doctor(
    module: Only = None,
    active: Active = False,
    allow_private: AllowPrivate = False,
) -> None:
    """Prueba cada módulo contra su fuente real con un valor de prueba seguro."""
    classes = _select_modules(module)
    checks = asyncio.run(
        run_doctor(Config.load(), classes, active=active, allow_private=allow_private)
    )
    styles = {
        "ok": "[green]ok[/]",
        "empty": "[yellow]sin datos[/]",
        "fail": "[red]FALLO[/]",
        "skipped": "[dim]omitido[/]",
        "unchecked": "[dim]sin prueba[/]",
    }
    table = Table()
    for col in ("Módulo", "Estado", "Detalle"):
        table.add_column(col, overflow="fold")
    table.add_column("Tiempo", justify="right")
    for c in checks:
        table.add_row(
            c.module, styles[c.verdict], escape(c.detail), f"{c.duration_ms / 1000:.1f} s"
        )
    console.print(table)
    failed = [c.module for c in checks if c.verdict == "fail"]
    if failed:
        console.print(f"[red]Fallan: {', '.join(failed)}[/]")
        raise typer.Exit(2)


@cache_app.command("clear")
def cache_clear() -> None:
    """Borra todas las respuestas cacheadas."""
    if not default_cache_path().exists():
        console.print("La caché está vacía.")
        return
    with ResponseCache() as cache:
        console.print(f"Borradas {cache.clear()} respuestas de {cache.path}")


@cache_app.command("info")
def cache_info() -> None:
    """Muestra cuántas respuestas vigentes hay en la caché."""
    if not default_cache_path().exists():
        console.print("La caché está vacía.")
        return
    with ResponseCache() as cache:
        count, size = cache.info()
        console.print(f"{count} respuestas vigentes ({size / 1024:.0f} KiB) en {cache.path}")


@app.command()
def version() -> None:
    """Muestra la versión."""
    console.print(f"osineitor {__version__}")


if __name__ == "__main__":
    app()
