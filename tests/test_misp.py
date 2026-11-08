"""F8.2: exportación a un evento MISP."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from osineitor import report
from osineitor.cli import app
from osineitor.errors import ExportUnavailable
from osineitor.models import Entity, EntityType, ScanResult
from osineitor.storage import Storage

runner = CliRunner()
SEED = Entity(type=EntityType.DOMAIN, value="example.com")


def ent(kind, value, **data) -> Entity:
    return Entity(type=kind, value=value, parent=SEED.key, source="fake", data=data)


def sample() -> ScanResult:
    return ScanResult(
        target=SEED,
        depth=2,
        purpose="auditoría propia",
        entities=[
            ent(EntityType.IP, "203.0.113.7"),
            ent(EntityType.URL, "https://example.com/login"),
            ent(EntityType.EMAIL, "admin@example.com"),
            ent(EntityType.VULNERABILITY, "CVE-2026-0001"),
            ent(EntityType.USERNAME, "maria"),
            ent(EntityType.FINDING, "x: example.com"),
        ],
    )


def event(result: ScanResult) -> dict:
    return json.loads(report.render(result, "misp"))["Event"]


def test_event_has_attributes_for_supported_types_only():
    ev = event(sample())
    pairs = sorted((a["type"], a["value"]) for a in ev["Attribute"] if a["type"] != "comment")
    assert pairs == [
        ("domain", "example.com"),
        ("email-dst", "admin@example.com"),
        ("ip-dst", "203.0.113.7"),
        ("url", "https://example.com/login"),
        ("vulnerability", "CVE-2026-0001"),
    ]


def test_nothing_is_marked_as_a_detection_indicator_and_sharing_is_private():
    result = sample()
    ev = event(result)
    assert all(a["to_ids"] is False for a in ev["Attribute"])
    assert ev["distribution"] == "0"  # solo tu organización: compartir es una decisión posterior
    assert ev["info"] == "OSINEITOR: domain:example.com"
    assert ev["date"] == result.started_at.strftime("%Y-%m-%d")


def test_attribute_comment_names_the_source_and_the_purpose_goes_in_the_event():
    ev = event(sample())
    ip = next(a for a in ev["Attribute"] if a["type"] == "ip-dst")
    assert "fake" in ip["comment"]
    purpose = [a for a in ev["Attribute"] if a["type"] == "comment"]
    assert [a["value"] for a in purpose] == ["auditoría propia"]


def test_ids_are_deterministic():
    result = sample()
    assert report.render(result, "misp") == report.render(result, "misp")


def test_empty_scan_still_has_the_seed():
    ev = event(ScanResult(target=SEED, depth=1))
    assert [a["value"] for a in ev["Attribute"]] == ["example.com"]


def test_missing_library_gives_a_clear_error(monkeypatch):
    import builtins

    real = builtins.__import__

    def deny(name, *args, **kwargs):
        if name == "pymisp" or name.startswith("pymisp."):
            raise ImportError("no hay pymisp")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", deny)
    with pytest.raises(ExportUnavailable, match=r"osineitor\[misp\]"):
        report.render(sample(), "misp")


def test_cli_export_misp(tmp_path):
    db = tmp_path / "m.db"
    with Storage(db) as store:
        store.save(sample())
    out = tmp_path / "evento.json"
    res = runner.invoke(
        app, ["export", "1", "--db", str(db), "--format", "misp", "--output", str(out)]
    )
    assert res.exit_code == 0, res.output
    assert "Event" in json.loads(out.read_text(encoding="utf-8"))
