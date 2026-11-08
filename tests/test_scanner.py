"""F8.5: API de librería `Scanner`."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import threading
import time

import pytest

import osineitor
from osineitor import ScanInputError, Scanner, registry
from osineitor.config import Config
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module
from osineitor.scope import Scope
from tests.test_cli import fake_module


@pytest.fixture
def fakes(monkeypatch):
    dns = fake_module("fake_dns", {EntityType.DOMAIN}, EntityType.IP, "93.184.216.34")
    mail = fake_module("fake_mail", {EntityType.EMAIL}, EntityType.DOMAIN, "example.com")
    active = fake_module(
        "fake_active", {EntityType.DOMAIN}, EntityType.RECORD, "http:example.com", passive=False
    )
    monkeypatch.setattr(registry, "discover", lambda: [dns, mail, active])
    return {"dns": dns, "mail": mail, "active": active}


def test_sync_scan_returns_the_result_with_the_detected_type(fakes):
    result = Scanner().scan("example.com")
    assert result.target.key == "domain:example.com"
    assert [e.key for e in result.entities] == ["ip:93.184.216.34"]
    assert result.status == "complete"


async def test_async_scan_runs_inside_a_running_loop(fakes):
    result = await Scanner().ascan("example.com")
    assert [e.value for e in result.entities] == ["93.184.216.34"]


async def test_sync_scan_refuses_to_run_inside_a_loop(fakes):
    with pytest.raises(RuntimeError, match="ascan"):
        Scanner().scan("example.com")


def test_options_reach_the_engine(fakes):
    seen: list[str] = []
    Scanner(
        active=True, only=["fake_dns", "fake_active"], on_entity=lambda e: seen.append(e.key)
    ).scan("example.com")
    assert seen == ["ip:93.184.216.34", "record:http:example.com"]
    quiet = Scanner(only=["fake_active"]).scan("example.com")  # activo sin `active=True`
    assert quiet.entities == [] and any("--active" in e.message for e in quiet.events)


def test_type_can_be_forced_and_events_are_forwarded(fakes):
    events: list[dict] = []
    result = Scanner(only=["fake_mail"], on_event=events.append).scan("a@b.com", EntityType.EMAIL)
    assert result.target.type == EntityType.EMAIL
    assert events[0]["type"] == "scan.start"
    assert {"scan.start", "progress"} <= {e["type"] for e in events}


@pytest.mark.parametrize(
    ("kwargs", "target", "match"),
    [
        ({}, "no es un valor/ válido", "http|IP|dominio|username|válid"),
        ({"only": ["nope"]}, "example.com", "módulos desconocidos: nope"),
        ({"purpose": ""}, "example.com", "propósito"),
        ({"purpose": "x" * 501}, "example.com", "propósito"),
        ({"scope": Scope(domains=("otro.org",))}, "example.com", "fuera del alcance"),
    ],
)
def test_invalid_requests_raise_scan_input_error(fakes, kwargs, target, match):
    with pytest.raises(ScanInputError, match=match):
        Scanner(**kwargs).scan(target)


def test_unknown_type_name_is_an_input_error(fakes):
    with pytest.raises(ScanInputError):
        Scanner().scan("example.com", "no_existe")


def test_people_scans_need_a_purpose_when_the_config_requires_it(fakes):
    config = Config(require_purpose=True)
    with pytest.raises(ScanInputError, match="propósito"):
        Scanner(config=config, only=["fake_mail"]).scan("a@b.com")
    ok = Scanner(config=config, only=["fake_mail"], purpose="auditoría propia").scan("a@b.com")
    assert ok.purpose == "auditoría propia"


def test_cancel_from_another_thread_keeps_what_was_collected(monkeypatch):
    class Slow(Module):
        name = "slow"
        description = "tarda"
        consumes = frozenset({EntityType.DOMAIN})
        timeout = 60.0

        async def run(self, entity):
            await asyncio.sleep(30)
            return []

    fast = fake_module("fast", {EntityType.DOMAIN}, EntityType.IP, "93.184.216.34")
    monkeypatch.setattr(registry, "discover", lambda: [fast, Slow])
    scanner = Scanner()
    threading.Timer(0.5, scanner.cancel).start()
    start = time.monotonic()
    result = scanner.scan("example.com")
    assert time.monotonic() - start < 10
    assert result.status == "cancelled"
    assert [e.value for e in result.entities] == ["93.184.216.34"]


def test_cancel_without_a_running_scan_does_nothing(fakes):
    Scanner().cancel()


def test_two_scans_at_once_on_one_scanner_are_rejected(fakes):
    async def both():
        scanner = Scanner()
        first = asyncio.ensure_future(scanner.ascan("example.com"))
        await asyncio.sleep(0)
        with pytest.raises(RuntimeError, match="ya está ejecutando"):
            await scanner.ascan("example.org")
        await first

    asyncio.run(both())


def test_scanner_is_reusable_after_a_scan(fakes):
    scanner = Scanner()
    assert scanner.scan("example.com").entities and scanner.scan("example.org").entities


def test_public_names_resolve_lazily():
    assert osineitor.Scanner is Scanner and osineitor.Entity is Entity
    assert {"Scanner", "ScanResult", "EntityType"} <= set(osineitor.__all__)
    with pytest.raises(AttributeError):
        osineitor.nope  # noqa: B018


def test_importing_the_package_does_not_load_the_engine():
    code = "import sys, osineitor; print('osineitor.engine' in sys.modules, osineitor.__version__)"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout.split()
    assert out[0] == "False"
