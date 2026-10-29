from __future__ import annotations

import json

import pytest

from osineitor import events as core_events
from osineitor_gui import events as gui_events
from osineitor_gui.events import (
    EntityFound,
    FutureVersion,
    ModuleEnd,
    ModuleStart,
    Notice,
    Progress,
    RawLine,
    ScanEnd,
    ScanStart,
    UnknownEvent,
    parse_event,
)


def line(type_: str, **fields) -> str:
    return json.dumps({"v": 1, "ts": "2026-10-29T10:00:00+00:00", "type": type_, **fields})


def test_parses_every_known_event():
    start = parse_event(
        line(
            "scan.start",
            target={"type": "domain", "value": "example.com"},
            depth=2,
            modules=["dns", "rdap"],
            skipped=[{"module": "shodan", "message": "falta la API key"}],
            budget={"max_entities": 2000},
        )
    )
    assert start == ScanStart(
        "domain",
        "example.com",
        2,
        ["dns", "rdap"],
        [{"module": "shodan", "message": "falta la API key"}],
        {"max_entities": 2000},
        "2026-10-29T10:00:00+00:00",
    )
    assert parse_event(line("module.start", module="dns", entity="domain:example.com")) == (
        ModuleStart("dns", "domain:example.com", "2026-10-29T10:00:00+00:00")
    )
    end = parse_event(
        line(
            "module.end",
            module="dns",
            status="ok",
            entity="domain:example.com",
            entities=2,
            requests=1,
            cache_hits=0,
            duration_ms=12,
            message="",
        )
    )
    assert isinstance(end, ModuleEnd) and (end.entities, end.duration_ms) == (2, 12)
    assert isinstance(
        parse_event(line("entity", entity={"type": "ip", "value": "1.1.1.1"})), EntityFound
    )
    assert parse_event(line("progress", done=1, total=3, entities=2, requests=4)) == Progress(
        1, 3, 2, 4, "2026-10-29T10:00:00+00:00"
    )
    assert parse_event(line("notice", code="legal", message="hola")) == Notice(
        "legal", "hola", "2026-10-29T10:00:00+00:00"
    )
    done = parse_event(line("scan.end", status="cancelled", scan_id=7, exit_code=130, entities=3))
    assert done == ScanEnd("cancelled", 7, 130, 3, "", "2026-10-29T10:00:00+00:00")


def test_unknown_things_are_ignored_not_fatal():
    assert isinstance(parse_event(line("brand.new", x=1)), UnknownEvent)
    # Un campo nuevo en un evento conocido no molesta.
    notice = parse_event(line("notice", code="c", message="m", future_field=[1, 2]))
    assert isinstance(notice, Notice)
    assert isinstance(parse_event("esto no es JSON"), RawLine)
    assert isinstance(parse_event("[1, 2, 3]"), RawLine)
    assert isinstance(parse_event('{"sin": "tipo"}'), RawLine)
    assert parse_event("   \r\n") is None


def test_future_contract_version_is_flagged():
    future = parse_event(json.dumps({"v": 2, "type": "scan.start"}))
    assert isinstance(future, FutureVersion) and future.version == 2


def test_missing_fields_get_defaults_instead_of_raising():
    assert parse_event(line("scan.end")) == ScanEnd("", None, 0, 0, "", "2026-10-29T10:00:00+00:00")
    assert isinstance(parse_event(line("module.end")), ModuleEnd)
    assert isinstance(
        parse_event(line("entity")), UnknownEvent
    )  # sin entidad no hay nada que pintar


def test_bytes_and_invalid_utf8():
    assert isinstance(parse_event(line("notice", code="c", message="ñ").encode()), Notice)
    assert isinstance(parse_event(b"\xff\xfe no es utf-8"), RawLine)


def test_exit_codes_match_the_cli():
    for name in ("EXIT_OK", "EXIT_INTERNAL", "EXIT_USAGE", "EXIT_MODULE_ERRORS", "EXIT_TRUNCATED"):
        assert getattr(gui_events, name) == getattr(core_events, name)
    assert gui_events.EXIT_CANCELLED == core_events.EXIT_CANCELLED
    assert gui_events.SUPPORTED_VERSION == core_events.VERSION


@pytest.mark.parametrize("kind", ["scan.start", "module.end", "scan.end"])
def test_parser_accepts_what_the_schema_allows(kind):
    """Un ejemplo mínimo válido del esquema también se interpreta sin caer en UnknownEvent."""
    examples = {
        "scan.start": {
            "target": {"type": "ip", "value": "1.1.1.1"},
            "depth": 1,
            "modules": [],
            "skipped": [],
            "budget": {},
        },
        "module.end": {
            "module": "m",
            "status": "ok",
            "entity": "ip:1.1.1.1",
            "entities": 0,
            "requests": 0,
            "cache_hits": 0,
            "duration_ms": 1,
            "message": "",
        },
        "scan.end": {"status": "complete", "scan_id": None, "exit_code": 0},
    }
    from tests.test_contract import validate

    payload = json.loads(line(kind, **examples[kind]))
    validate("event", payload)
    assert not isinstance(parse_event(json.dumps(payload)), UnknownEvent | RawLine)
