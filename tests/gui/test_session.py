from __future__ import annotations

import json

from osineitor_gui.events import (
    EntityFound,
    ModuleEnd,
    ModuleStart,
    Notice,
    Progress,
    ScanEnd,
    ScanStart,
)
from osineitor_gui.process import CliProcess
from osineitor_gui.session import ScanSession
from tests.gui.fakecli import CLI, driver_env

START = ScanStart(
    "domain",
    "example.com",
    2,
    ["dns", "rdap"],
    [{"module": "shodan", "message": "falta la API key"}],
    {},
)


def entity(type_, value, **data):
    return EntityFound(
        {"type": type_, "value": value, "data": data, "source": "dns", "parent": None}
    )


def started() -> ScanSession:
    session = ScanSession()
    session.begin()
    session.feed(START)
    return session


def test_initial_state_lists_modules_and_skipped_ones():
    session = started()
    assert session.state == "running"
    assert (session.target_type, session.target_value, session.depth) == (
        "domain",
        "example.com",
        2,
    )
    assert session.modules["dns"].status == "pending"
    assert session.modules["shodan"].status == "skipped"
    assert session.modules["shodan"].message == "falta la API key"


def test_module_lifecycle_and_worst_status_wins():
    session = started()
    session.feed(ModuleStart("dns", "domain:example.com"))
    assert session.modules["dns"].status == "running"
    session.feed(
        ModuleEnd("dns", "ok", "domain:example.com", entities=2, requests=3, duration_ms=10)
    )
    session.feed(ModuleStart("dns", "ip:1.1.1.1"))
    session.feed(
        ModuleEnd("dns", "error", "ip:1.1.1.1", message="boom", duration_ms=5, cache_hits=1)
    )
    dns = session.modules["dns"]
    assert dns.status == "error" and dns.runs == 2 and dns.message == "boom"
    assert (dns.entities, dns.requests, dns.cache_hits, dns.duration_ms) == (2, 3, 1, 15)
    assert dns.running == 0


def test_entities_progress_and_notices():
    session = started()
    session.feed(Notice("legal", "aviso"))
    session.feed(entity("ip", "1.1.1.1", asn="AS13335"))
    session.feed(entity("domain", "mail.example.com"))
    session.feed(entity("ip", "9.9.9.9"))
    session.feed(Progress(1, 4, 3, 7))
    assert session.counts_by_type() == {"domain": 1, "ip": 2}
    assert (session.done, session.total, session.requests) == (1, 4, 7)
    assert session.notices[0].code == "legal"


def test_filtering_by_type_and_text():
    session = started()
    session.feed(entity("ip", "1.1.1.1", org="Cloudflare"))
    session.feed(entity("ip", "9.9.9.9", org="Quad9"))
    session.feed(entity("domain", "mail.example.com"))
    assert [e["value"] for e in session.filtered({"ip"})] == ["1.1.1.1", "9.9.9.9"]
    assert [e["value"] for e in session.filtered(text="CLOUDFLARE")] == ["1.1.1.1"]  # en los datos
    assert [e["value"] for e in session.filtered({"domain"}, "mail")] == ["mail.example.com"]
    assert session.filtered({"domain"}, "cloudflare") == []
    assert len(session.filtered()) == 3


def test_end_states():
    for status, incomplete in (("complete", False), ("truncated", True), ("cancelled", True)):
        session = started()
        session.feed(ScanEnd(status, 5, 0))
        assert (session.state, session.finished, session.incomplete) == (status, True, incomplete)
        assert session.scan_id == 5
    odd = started()
    odd.feed(ScanEnd("algo-nuevo", None, 0))
    assert odd.state == "failed"  # un estado desconocido nunca se da por bueno


def test_a_cli_that_dies_without_closing_the_scan_is_a_failure():
    session = started()
    session.process_exited(1, ["Traceback…", "RuntimeError: boom"])
    assert session.state == "failed" and "boom" in session.message
    crashed = started()
    crashed.process_exited(-9)
    assert crashed.state == "failed" and "código -9" in crashed.message
    killed = started()
    killed.process_exited(130)
    assert killed.state == "cancelled"
    # Si el scan ya había terminado, la salida de la CLI no lo cambia.
    done = started()
    done.feed(ScanEnd("complete", 1, 0))
    done.process_exited(3)
    assert done.state == "complete"


def test_live_session_matches_a_saved_one(monkeypatch):
    """La misma vista sirve para un scan en vivo y para uno guardado."""
    from osineitor_gui.api import CliApi
    from osineitor_gui.scan_request import ScanRequest

    monkeypatch.setenv("DRIVER_MODULES", "fast,bad")
    live = ScanSession()
    live.begin()
    proc = CliProcess(
        ScanRequest("example.com", kind="domain").to_args(),
        cli=CLI,
        env=driver_env("fast,bad"),
        on_event=live.feed,
    )
    proc.start()
    proc.wait(30)
    saved = ScanSession()
    saved.load_result(CliApi(cli=CLI).show(live.scan_id))
    assert saved.state == live.state == "complete"
    assert [e["value"] for e in saved.entities] == [e["value"] for e in live.entities]
    for name in ("fast", "bad"):
        assert saved.modules[name].status == live.modules[name].status
        assert saved.modules[name].entities == live.modules[name].entities
    assert saved.modules["bad"].message == "se rompió"
    assert json.dumps(saved.counts_by_type()) == json.dumps(live.counts_by_type())
