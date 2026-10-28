"""Interfaz de línea de comandos."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from osineitor import __version__, registry
from osineitor.config import Config, config_dir, config_path
from osineitor.engine import Engine
from osineitor.http import HttpClient
from osineitor.models import Entity, EntityType, ScanResult
from osineitor.modules.base import Context
from osineitor.storage import Storage

LEGAL_NOTICE = (
    "OSINEITOR solo consulta fuentes abiertas. Úsalo sobre objetivos propios o con autorización "
    "expresa. Investigar a personas físicas está sujeto al RGPD y a la legislación local: "
    "tú eres responsable del uso que hagas de la herramienta."
)

app = typer.Typer(help="Herramienta OSINT modular.\n\n" + LEGAL_NOTICE, no_args_is_help=True)
config_app = typer.Typer(help="Gestiona API keys y ajustes.", no_args_is_help=True)
app.add_typer(config_app, name="config")
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


async def _scan(
    seed: Entity, depth: int, active: bool, only: list[str] | None, live: bool
) -> ScanResult:
    config = Config.load()
    async with HttpClient(config) as http:
        ctx = Context(config=config, http=http)
        engine = Engine(
            ctx,
            _select_modules(only),
            depth=depth,
            active=active,
            on_entity=_print_entity if live else None,
        )
        return await engine.run(seed)


def _print_entity(entity: Entity) -> None:
    console.print(f"  [cyan]{entity.type:<13}[/] {entity.value}  [dim]({entity.source})[/]")


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
    for ev in result.events:
        color = "red" if ev.kind == "error" else "dim"
        where = f" [{ev.entity}]" if ev.entity else ""
        console.print(f"[{color}]{ev.kind}: {ev.module}{where}: {ev.message}[/]")


def _run_target(
    etype: EntityType,
    value: str,
    depth: int,
    active: bool,
    only: list[str] | None,
    no_save: bool,
    as_json: bool,
    db: Path | None,
) -> None:
    if not as_json:
        _show_notice_once()
        console.print(f"[bold]Escaneando {etype} {value}[/] (profundidad {depth})")
    seed = Entity(type=etype, value=value.strip())
    result = asyncio.run(_scan(seed, depth, active, only, live=not as_json))
    if not no_save:
        storage = Storage(db)
        storage.save(result)
        storage.close()
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
) -> None:
    """Investiga un dominio: RDAP/WHOIS, DNS, subdominios, histórico web."""
    _run_target(EntityType.DOMAIN, target.lower(), depth, active, module, no_save, json_out, db)


@app.command()
def ip(
    target: str,
    depth: Depth = 1,
    active: Active = False,
    module: Only = None,
    no_save: NoSave = False,
    json_out: AsJson = False,
    db: DbPath = None,
) -> None:
    """Investiga una IP: geolocalización, puertos/servicios, reputación."""
    _run_target(EntityType.IP, target, depth, active, module, no_save, json_out, db)


@app.command()
def email(
    target: str,
    depth: Depth = 1,
    active: Active = False,
    module: Only = None,
    no_save: NoSave = False,
    json_out: AsJson = False,
    db: DbPath = None,
) -> None:
    """Investiga un email: validez, perfiles asociados, filtraciones."""
    _run_target(EntityType.EMAIL, target.lower(), depth, active, module, no_save, json_out, db)


@app.command()
def username(
    target: str,
    depth: Depth = 1,
    active: Active = False,
    module: Only = None,
    no_save: NoSave = False,
    json_out: AsJson = False,
    db: DbPath = None,
) -> None:
    """Busca un nombre de usuario en cientos de sitios."""
    _run_target(EntityType.USERNAME, target, depth, active, module, no_save, json_out, db)


@app.command("modules")
def list_modules() -> None:
    """Lista los módulos disponibles y su estado."""
    config = Config.load()
    table = Table()
    for col in ("Módulo", "Consume", "Produce", "Tipo", "API key", "Descripción"):
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
    storage = Storage(db)
    table = Table("ID", "Tipo", "Objetivo", "Entidades", "Fecha")
    for scan_id, ttype, target, count, started in storage.list_scans(limit):
        table.add_row(str(scan_id), ttype, target, str(count), started[:19])
    storage.close()
    console.print(table)


@app.command()
def show(scan_id: int, db: DbPath = None) -> None:
    """Muestra un scan guardado."""
    storage = Storage(db)
    result = storage.load(scan_id)
    storage.close()
    if result is None:
        raise typer.BadParameter(f"no existe el scan {scan_id}")
    render(result)


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
def version() -> None:
    """Muestra la versión."""
    console.print(f"osineitor {__version__}")


if __name__ == "__main__":
    app()
