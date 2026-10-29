"""Contrato CLI↔GUI: eventos NDJSON, salidas --json, códigos de salida y cancelación."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import jsonschema
import pytest
from typer.testing import CliRunner

from osineitor import cli
from osineitor.cli import app, exit_code_for
from osineitor.control import parse_command
from osineitor.engine import Engine
from osineitor.models import Entity, EntityType, ScanEvent, ScanResult
from osineitor.modules.base import Module
from tests.test_cli import fake_module, use_modules

SCHEMA = json.loads(
    (Path(__file__).parent.parent / "docs" / "cli-contract.schema.json").read_text(encoding="utf-8")
)
runner = CliRunner()


def validate(name: str, data) -> None:
    schema = {"$schema": SCHEMA["$schema"], "$ref": f"#/$defs/{name}", "$defs": SCHEMA["$defs"]}
    jsonschema.Draft202012Validator(schema).validate(data)


def parse_events(stdout: str) -> list[dict]:
    lines = stdout.splitlines()
    assert lines, "stdout vacío"
    events = [json.loads(line) for line in lines]  # cualquier línea que no sea JSON falla aquí
    for ev in events:
        validate("event", ev)
    return events


@pytest.fixture
def modules(monkeypatch):
    mods = [
        fake_module("fake_dns", {EntityType.DOMAIN}, EntityType.IP, "9.9.9.9", via="dns"),
        fake_module("fake_ip", {EntityType.IP}, EntityType.RECORD, "info:9.9.9.9", org="ACMÉ ñ"),
    ]
    use_modules(monkeypatch, mods)
    return mods


# --- NDJSON -----------------------------------------------------------------------------------


def test_ndjson_stream_is_valid_ordered_and_complete(modules):
    result = runner.invoke(app, ["scan", "example.com", "--ndjson", "--no-save"])
    assert result.exit_code == 0
    events = parse_events(result.stdout)
    types = [e["type"] for e in events]
    assert types[0] in ("notice", "scan.start")
    assert types[-1] == "scan.end"
    start = next(e for e in events if e["type"] == "scan.start")
    assert start["target"] == {"type": "domain", "value": "example.com"}
    assert start["modules"] == ["fake_dns", "fake_ip"]
    # Cada módulo que arranca termina, y el progreso nunca supera el total.
    started = [(e["module"], e["entity"]) for e in events if e["type"] == "module.start"]
    ended = [(e["module"], e["entity"]) for e in events if e["type"] == "module.end"]
    assert sorted(started) == sorted(ended) and len(started) == 2
    progress = [e for e in events if e["type"] == "progress"]
    assert progress and all(p["done"] <= p["total"] for p in progress)
    assert (progress[-1]["done"], progress[-1]["total"]) == (2, 2)
    entities = [e["entity"]["value"] for e in events if e["type"] == "entity"]
    assert entities == ["9.9.9.9", "info:9.9.9.9"]
    end = events[-1]
    assert (end["status"], end["exit_code"], end["scan_id"]) == ("complete", 0, None)


def test_entity_carries_its_observations_in_ndjson_and_in_json(modules, tmp_path):
    db = str(tmp_path / "s.db")
    events = parse_events(
        runner.invoke(app, ["domain", "example.com", "--ndjson", "--db", db]).stdout
    )
    ip = next(e["entity"] for e in events if e["type"] == "entity" and e["entity"]["type"] == "ip")
    # El evento se emite al descubrirla: trae la primera observación.
    assert [(o["module"], o["query"]) for o in ip["observations"]] == [
        ("fake_dns", "domain:example.com")
    ]
    shown = json.loads(runner.invoke(app, ["show", "1", "--db", db, "--json"]).stdout)
    validate("scan_result", shown)
    saved = next(e for e in shown["entities"] if e["type"] == "ip")
    assert saved["observations"][0]["module"] == "fake_dns"
    assert saved["observations"][0]["at"]


def test_ndjson_stdout_is_ascii_even_with_non_ascii_data(modules):
    result = runner.invoke(app, ["scan", "example.com", "--ndjson", "--no-save"])
    assert result.stdout.isascii()  # no depende de la codificación de la tubería
    record = next(
        e["entity"]
        for e in parse_events(result.stdout)
        if e["type"] == "entity" and e["entity"]["type"] == "record"
    )
    assert record["data"]["org"] == "ACMÉ ñ"  # y se recupera tal cual al decodificar


def test_ndjson_saves_scan_and_reports_its_id(modules, tmp_path):
    db = str(tmp_path / "s.db")
    result = runner.invoke(app, ["domain", "example.com", "--ndjson", "--db", db])
    assert parse_events(result.stdout)[-1]["scan_id"] == 1
    shown = runner.invoke(app, ["show", "1", "--db", db, "--json"])
    validate("scan_result", json.loads(shown.stdout))


def test_legal_notice_is_an_event_once(modules):
    first = parse_events(
        runner.invoke(app, ["domain", "example.com", "--ndjson", "--no-save"]).stdout
    )
    second = parse_events(
        runner.invoke(app, ["domain", "example.com", "--ndjson", "--no-save"]).stdout
    )
    assert [e["code"] for e in first if e["type"] == "notice"] == ["legal"]
    assert not [e for e in second if e["type"] == "notice"]


def test_ndjson_and_json_are_mutually_exclusive(modules):
    result = runner.invoke(app, ["domain", "example.com", "--ndjson", "--json"])
    assert result.exit_code == 2


def test_quiet_prints_nothing_but_still_exits_with_the_code(modules):
    result = runner.invoke(app, ["domain", "example.com", "--quiet", "--no-save"])
    assert result.exit_code == 0 and result.stdout.strip() == ""


def test_scan_json_validates_and_carries_status(modules):
    result = runner.invoke(app, ["domain", "example.com", "--json", "--no-save"])
    data = json.loads(result.stdout)
    validate("scan_result", data)
    assert data["status"] == "complete"


# --- códigos de salida ---------------------------------------------------------------------------


def test_exit_code_with_module_errors_is_3_and_ndjson_agrees(monkeypatch):
    use_modules(
        monkeypatch,
        [
            fake_module("ok_mod", {EntityType.DOMAIN}, EntityType.IP, "9.9.9.9"),
            fake_module("bad_mod", {EntityType.DOMAIN}, EntityType.IP, "x", error="se rompió"),
        ],
    )
    result = runner.invoke(app, ["domain", "example.com", "--ndjson", "--no-save"])
    assert result.exit_code == 3
    end = parse_events(result.stdout)[-1]
    assert (end["status"], end["exit_code"]) == ("complete", 3)


def test_exit_code_truncated_is_4_and_beats_errors(modules):
    result = runner.invoke(
        app, ["scan", "example.com", "--max-entities", "1", "--ndjson", "--no-save"]
    )
    assert result.exit_code == 4
    end = parse_events(result.stdout)[-1]
    assert (end["status"], end["exit_code"]) == ("truncated", 4)


def test_usage_error_is_2(modules):
    assert runner.invoke(app, ["domain", "no es un dominio ///"]).exit_code == 2
    assert runner.invoke(app, ["domain", "example.com", "-m", "nope"]).exit_code == 2


def test_internal_failure_is_1_and_ndjson_reports_it(monkeypatch):
    async def boom(seed, opts, live, sink=None):
        raise RuntimeError("fallo inesperado")

    monkeypatch.setattr(cli, "_scan", boom)
    result = runner.invoke(app, ["domain", "example.com", "--ndjson", "--no-save"])
    assert result.exit_code == 1
    end = parse_events(result.stdout)[-1]
    assert (end["type"], end["status"], end["exit_code"]) == ("scan.end", "failed", 1)
    assert "fallo inesperado" in end["message"]


def test_exit_code_for_priority():
    seed = Entity(type=EntityType.DOMAIN, value="example.com")
    result = ScanResult(
        target=seed, depth=1, events=[ScanEvent(kind="error", module="m", message="x")]
    )
    assert exit_code_for(result) == 3
    result.truncated = True
    assert exit_code_for(result) == 4
    result.events.append(ScanEvent(kind="cancelled", module="engine", message="x"))
    assert exit_code_for(result) == 130
    assert exit_code_for(ScanResult(target=seed, depth=1)) == 0


# --- salidas --json de las demás órdenes ----------------------------------------------------------


def test_json_outputs_of_every_command_match_the_schema(modules, tmp_path):
    db = str(tmp_path / "s.db")
    runner.invoke(app, ["domain", "example.com", "--db", db, "--quiet"])
    runner.invoke(app, ["config", "set", "shodan", "SECRETVALUE"])
    cases = {
        "modules_output": ["modules", "--json"],
        "history_output": ["history", "--db", db, "--json"],
        "scan_result": ["show", "1", "--db", db, "--json"],
        "config_show_output": ["config", "show", "--json"],
        "version_output": ["version", "--json"],
        "export_output": [
            "export",
            "1",
            "--db",
            db,
            "-f",
            "json",
            "-o",
            str(tmp_path / "r.json"),
            "--json",
        ],
        "doctor_output": ["doctor", "--json"],
        "config_key_output": ["config", "unset", "shodan", "--json"],
    }
    for schema_name, args in cases.items():
        result = runner.invoke(app, args)
        assert result.exit_code == 0, (args, result.output)
        validate(schema_name, json.loads(result.stdout))


def test_config_show_json_never_exposes_key_material():
    runner.invoke(app, ["config", "set", "shodan", "SECRETVALUE"])
    out = runner.invoke(app, ["config", "show", "--json"]).stdout
    assert "SECRETVALUE" not in out and "SECR" not in out
    assert json.loads(out)["keys"] == [{"name": "shodan"}]


def test_modules_json_lists_every_bundled_module():
    from osineitor import registry

    data = json.loads(runner.invoke(app, ["modules", "--json"]).stdout)
    assert [m["name"] for m in data] == [m.name for m in registry.discover()]
    validate("modules_output", data)


def test_schema_rejects_a_malformed_event():
    with pytest.raises(jsonschema.ValidationError):
        validate("event", {"v": 1, "ts": "x", "type": "module.end", "module": "m"})
    with pytest.raises(jsonschema.ValidationError):
        validate("event", {"v": 2, "ts": "x", "type": "notice", "code": "c", "message": "m"})


# --- cancelación dentro del proceso ---------------------------------------------------------------


class Hang(Module):
    name = "hang"
    description = "test"
    consumes = frozenset({EntityType.DOMAIN})

    async def run(self, entity):
        await asyncio.sleep(60)
        return []


class Fast(Module):
    name = "fast"
    description = "test"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.IP})

    async def run(self, entity):
        return [self.emit(entity, EntityType.IP, "9.9.9.9")]


async def test_engine_cancel_keeps_finished_work(ctx):
    seen = []
    engine = Engine(ctx, [Fast, Hang], on_event=seen.append)

    async def cancel_when_fast_done():
        while not any(e["type"] == "module.end" and e["module"] == "fast" for e in seen):
            await asyncio.sleep(0.01)
        engine.cancel()

    canceller = asyncio.create_task(cancel_when_fast_done())
    result = await asyncio.wait_for(engine.run(Entity(type=EntityType.DOMAIN, value="a.com")), 10)
    await canceller
    assert result.cancelled and result.status == "cancelled"
    assert [e.value for e in result.entities] == ["9.9.9.9"]  # lo terminado se conserva
    runs = {r.module: r.status for r in result.runs}
    assert runs == {"fast": "ok", "hang": "skipped"}
    assert exit_code_for(result) == 130
    # Todo module.start tiene su module.end, también el cancelado.
    assert sorted(e["module"] for e in seen if e["type"] == "module.start") == ["fast", "hang"]
    assert sorted(e["module"] for e in seen if e["type"] == "module.end") == ["fast", "hang"]


async def test_engine_cancel_before_start_runs_nothing(ctx):
    engine = Engine(ctx, [Fast])
    engine.cancel()
    result = await engine.run(Entity(type=EntityType.DOMAIN, value="a.com"))
    assert result.cancelled and result.entities == [] and result.runs == []


def test_parse_command():
    assert parse_command(b'{"cmd": "cancel"}') == "cancel"
    assert parse_command(b"not json") is None
    assert parse_command(b'{"nada": 1}') is None
    assert parse_command(b"[1, 2]") is None


# --- cancelación real, con un proceso hijo (lo que hará la GUI) ----------------------------------

DRIVER = textwrap.dedent(
    """
    import asyncio, os, sys
    from osineitor import registry
    from osineitor.models import EntityType
    from osineitor.modules.base import Module

    class Fast(Module):
        name = "fast"; description = "x"
        consumes = frozenset({EntityType.DOMAIN}); produces = frozenset({EntityType.IP})
        async def run(self, entity):
            return [self.emit(entity, EntityType.IP, "9.9.9.9")]

    class Hang(Module):
        name = "hang"; description = "x"; consumes = frozenset({EntityType.DOMAIN})
        async def run(self, entity):
            await asyncio.sleep(120)
            return []

    mods = {"fast": Fast, "hang": Hang}
    chosen = os.environ["DRIVER_MODULES"].split(",")
    registry.discover = lambda: [mods[m] for m in chosen]
    from osineitor.cli import app
    app()
    """
)


class Child:
    """Proceso hijo con un vigilante: si algo se cuelga, la prueba falla en vez de bloquearse."""

    def __init__(self, tmp_path, modules: str, *flags: str):
        env = {**os.environ, "DRIVER_MODULES": modules, "PYTHONUTF8": "1"}
        self.db = tmp_path / "child.db"
        self.proc = subprocess.Popen(
            [
                sys.executable,
                "-c",
                DRIVER,
                "domain",
                "example.com",
                "--ndjson",
                "--db",
                str(self.db),
                *flags,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        self.watchdog = threading.Timer(60, self.proc.kill)
        self.watchdog.start()

    def read_until(self, predicate) -> list[dict]:
        events = []
        for raw in self.proc.stdout:
            events.append(json.loads(raw))
            if predicate(events[-1]):
                return events
        raise AssertionError(f"el hijo terminó sin el evento esperado: {events}")

    def finish(self) -> tuple[int, list[dict]]:
        rest = [json.loads(line) for line in self.proc.stdout]
        code = self.proc.wait(timeout=30)
        self.watchdog.cancel()
        self.proc.stdout.close()
        self.proc.stderr.close()
        return code, rest


def fast_done(ev):
    return ev["type"] == "module.end" and ev["module"] == "fast"


@pytest.mark.parametrize("how", ["command", "eof"])
def test_child_cancel_via_stdin_saves_partial_result(tmp_path, how):
    child = Child(tmp_path, "fast,hang", "--control-stdin")
    seen = child.read_until(fast_done)
    if how == "command":
        child.proc.stdin.write(b'{"cmd": "cancel"}\n')
        child.proc.stdin.flush()
    child.proc.stdin.close()  # con "eof" es lo único que hace: el cliente "murió"
    code, rest = child.finish()
    events = seen + rest
    assert code == 130
    end = events[-1]
    assert (end["type"], end["status"], end["exit_code"]) == ("scan.end", "cancelled", 130)
    assert end["scan_id"] == 1  # el resultado parcial se guardó
    from osineitor.storage import Storage

    with Storage(child.db) as store:
        loaded = store.load(1)
    assert loaded.cancelled
    assert [e.value for e in loaded.entities] == ["9.9.9.9"]


def test_child_exits_normally_even_if_stdin_stays_open(tmp_path):
    """El hilo que vigila stdin no debe impedir que el proceso termine."""
    child = Child(tmp_path, "fast", "--control-stdin")
    events = child.read_until(lambda e: e["type"] == "scan.end")
    code, _ = child.finish()  # stdin sigue abierto: no debe colgarse
    assert code == 0 and events[-1]["status"] == "complete"
    child.proc.stdin.close()


def test_child_ignores_garbage_on_stdin(tmp_path):
    child = Child(tmp_path, "fast,hang", "--control-stdin")
    child.read_until(fast_done)
    child.proc.stdin.write(b'basura\n{"cmd": "otra"}\n')
    child.proc.stdin.flush()
    child.proc.stdin.write(b'{"cmd": "cancel"}\n')
    child.proc.stdin.flush()
    code, rest = child.finish()
    assert code == 130 and rest[-1]["status"] == "cancelled"
    child.proc.stdin.close()


class Slow(Module):
    name = "slow"
    description = "test"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.IP})

    async def run(self, entity):
        await asyncio.sleep(0.4)
        return [self.emit(entity, EntityType.IP, "8.8.8.8")]


async def test_entities_are_streamed_as_each_module_finishes(ctx):
    """Lo del módulo rápido se emite antes de que termine el lento (no al final del nivel)."""
    seen: list[dict] = []
    engine = Engine(ctx, [Fast, Slow], on_event=seen.append)
    await engine.run(Entity(type=EntityType.DOMAIN, value="a.com"))
    labels = [
        (e["type"], e.get("module") or e["entity"]["value"])
        for e in seen
        if e["type"] in ("entity", "module.end")
    ]
    assert labels.index(("entity", "9.9.9.9")) < labels.index(("module.end", "slow"))
    progress = [e for e in seen if e["type"] == "progress"]
    assert [p["done"] for p in progress] == [1, 2]
    assert progress[0]["entities"] == 1 and progress[1]["entities"] == 2
