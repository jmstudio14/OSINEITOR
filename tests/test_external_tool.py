"""F3.4: adaptadores de herramientas externas (`ExternalToolModule`).

El «ejecutable» de los tests es el propio intérprete de Python, así que corren igual en cualquier
sistema y sin instalar nada.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

import pytest

from osineitor.config import Config
from osineitor.doctor import run_doctor
from osineitor.engine import Engine
from osineitor.http import HttpClient
from osineitor.models import Entity, EntityType
from osineitor.modules._external import ExternalToolModule, json_documents
from osineitor.modules.base import Context

SEED = Entity(type=EntityType.DOMAIN, value="example.com")

NDJSON = (
    "import json, sys\n"
    "for host in ('a', 'b'):\n"
    "    print(json.dumps({'host': host + '.' + sys.argv[1]}))\n"
)


def adapter(script: str = NDJSON, **attrs) -> type[ExternalToolModule]:
    """Adaptador de prueba: ejecuta `script` y vuelca cada documento como un dominio."""

    def args(self, entity):
        return ["-c", script, entity.value]

    def parse(self, entity, documents):
        return [self.emit(entity, EntityType.DOMAIN, d["host"]) for d in documents]

    namespace = {
        "name": "ext_test",
        "description": "herramienta de prueba",
        "consumes": frozenset({EntityType.DOMAIN}),
        "produces": frozenset({EntityType.DOMAIN}),
        "binary": sys.executable,
        "canary": "example.com",
        "args": args,
        "parse": parse,
        **attrs,
    }
    return type("Ext", (ExternalToolModule,), namespace)


async def scan(ctx, cls, seed=SEED):
    return await Engine(ctx, [cls]).run(seed)


async def test_it_runs_the_tool_and_parses_its_json_lines(ctx):
    result = await scan(ctx, adapter())
    assert [e.value for e in result.entities] == ["a.example.com", "b.example.com"]
    [run] = result.runs
    assert run.status == "ok" and run.requests == 0  # no pasa por ctx.http


async def test_it_also_parses_a_single_json_document(ctx):
    script = (
        "import json; print(json.dumps([{'host': 'x.example.com'}, {'host': 'y.example.com'}]))"
    )

    class One(adapter(script)):
        def parse(self, entity, documents):
            return [self.emit(entity, EntityType.DOMAIN, d["host"]) for d in documents[0]]

    result = await scan(ctx, One)
    assert [e.value for e in result.entities] == ["x.example.com", "y.example.com"]


def test_json_documents():
    assert json_documents('{"a": 1}') == [{"a": 1}]
    assert json_documents('{"a": 1}\n\n{"a": 2}\n') == [{"a": 1}, {"a": 2}]
    assert json_documents("") == []


async def test_a_tool_that_is_not_installed_is_skipped_not_an_error(ctx):
    result = await scan(ctx, adapter(binary="osineitor-no-such-tool"))
    [run] = result.runs
    assert run.status == "skipped" and "no está instalado" in run.message
    assert not [e for e in result.events if e.kind == "error"]


async def test_a_too_old_tool_is_skipped(ctx):
    result = await scan(ctx, adapter(min_version=(99, 0)))
    [run] = result.runs
    assert run.status == "skipped" and "anterior a la mínima 99.0" in run.message


async def test_a_new_enough_tool_runs(ctx):
    result = await scan(ctx, adapter(min_version=(3,)))
    assert [r.status for r in result.runs] == ["ok"]


async def test_a_version_that_cannot_be_read_is_skipped(ctx):
    cls = adapter(min_version=(1,), version_args=("-c", "print('sin número')"))
    [run] = (await scan(ctx, cls)).runs
    assert run.status == "skipped" and "no se pudo leer la versión" in run.message


async def test_the_arguments_never_go_through_a_shell(ctx, tmp_path):
    marker = tmp_path / "hacked"
    nasty = f"; echo hola > {marker} & `touch {marker}` $(touch {marker}) | cat"
    script = "import json, sys; print(json.dumps({'host': sys.argv[1]}))"

    class Nasty(adapter(script)):
        def args(self, entity):
            return ["-c", script, nasty]

        def parse(self, entity, documents):
            return [self.emit(entity, EntityType.RECORD, documents[0]["host"])]

    result = await scan(ctx, Nasty)
    assert [e.value for e in result.entities] == [nasty]  # llegó tal cual, como un solo argumento
    assert not marker.exists()


async def test_a_value_that_looks_like_an_option_is_not_passed_to_the_tool(ctx):
    cls = adapter(consumes=frozenset({EntityType.USERNAME}))
    result = await scan(ctx, cls, Entity(type=EntityType.USERNAME, value="-oX"))
    [run] = result.runs
    assert run.status == "skipped" and "opción" in run.message


async def test_a_failing_tool_is_a_module_error_with_its_message(ctx):
    script = "import sys; sys.stderr.write('línea 1\\nboom\\n'); sys.exit(3)"
    [run] = (await scan(ctx, adapter(script))).runs
    assert run.status == "error"
    assert "código 3" in run.message and run.message.endswith("boom")


async def test_output_that_is_not_json_is_a_module_error(ctx):
    [run] = (await scan(ctx, adapter("print('hola, no soy JSON')"))).runs
    assert run.status == "error" and "JSON" in run.message


async def test_the_api_keys_of_osineitor_are_not_passed_to_the_tool(ctx, monkeypatch):
    monkeypatch.setenv("OSINEITOR_SHODAN_KEY", "secreta")
    monkeypatch.setenv("OTRA_VARIABLE", "visible")
    script = (
        "import json, os; print(json.dumps({'host': "
        "str(sorted(k for k in os.environ if k in ('OSINEITOR_SHODAN_KEY', 'OTRA_VARIABLE')))}))"
    )

    class Env(adapter(script)):
        def parse(self, entity, documents):
            return [self.emit(entity, EntityType.RECORD, documents[0]["host"])]

    [found] = (await scan(ctx, Env)).entities
    assert found.value == "['OTRA_VARIABLE']"


async def test_a_timeout_kills_the_process(ctx, tmp_path):
    flag = tmp_path / "terminó"
    script = f"import time; time.sleep(1.0); open({str(flag)!r}, 'w').close(); print('{{}}')"
    started = time.monotonic()
    [run] = (await scan(ctx, adapter(script, timeout=0.3))).runs
    assert run.status == "error" and "sin respuesta" in run.message
    assert time.monotonic() - started < 0.9
    await asyncio.sleep(1.5)
    assert not flag.exists()  # el proceso murió: nunca llegó a escribirlo


async def test_with_a_proxy_the_tool_is_skipped(config):
    http = HttpClient(config, proxy="socks5://127.0.0.1:9")
    result = await Engine(Context(config=config, http=http), [adapter()]).run(SEED)
    await http.aclose()
    [run] = result.runs
    assert run.status == "skipped" and "no se enruta por --proxy" in run.message


async def test_doctor_reports_a_missing_tool_as_skipped():
    [check] = await run_doctor(Config(), [adapter(binary="osineitor-no-such-tool")])
    assert check.verdict == "skipped" and "no está instalado" in check.detail


async def test_doctor_runs_the_canary_of_an_installed_tool():
    [check] = await run_doctor(Config(), [adapter()])
    assert check.verdict == "ok" and check.detail == "2 entidades"


def test_it_is_abstract_without_args_and_parse():
    class Incomplete(ExternalToolModule):
        name = "x"
        description = "x"
        consumes = frozenset()
        binary = "x"

    with pytest.raises(TypeError):
        Incomplete(None)


def test_the_discovery_does_not_pick_up_the_base_class():
    from osineitor import registry

    assert "ExternalToolModule" not in {m.__name__ for m in registry.discover()}
    assert json.dumps(sorted(m.name for m in registry.discover()))  # y no falla al importarlo
