"""F7.11: exportación CSV de entidades, relaciones y hallazgos."""

from __future__ import annotations

import csv
import io

from typer.testing import CliRunner

from osineitor import report
from osineitor.cli import app
from osineitor.models import Entity, EntityType, Observation, ScanResult
from osineitor.storage import Storage

runner = CliRunner()


def rows(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text)))


def make_result() -> ScanResult:
    seed = Entity(type=EntityType.DOMAIN, value="example.com")
    ip = Entity(
        type=EntityType.IP,
        value="1.1.1.1",
        parent=seed.key,
        observations=[Observation(module="dns", query=seed.key)],
        data={"asn": 13335},
    )
    sub = Entity(
        type=EntityType.RECORD,
        value="=cmd|calc",
        parent=seed.key,
        observations=[Observation(module="crtsh", query=seed.key)],
    )
    finding = Entity(
        type=EntityType.FINDING,
        value="spf-permissive: dns:example.com",
        parent="record:dns:example.com",
        data={
            "rule": "spf-permissive",
            "severity": "high",
            "title": "SPF permisivo",
            "affected": ["record:dns:example.com"],
            "evidence": {"SPF": "v=spf1 +all"},
            "recommendation": "Cierra el\n  registro.",
        },
    )
    return ScanResult(target=seed, depth=2, entities=[ip, sub, finding], scan_id=1)


def test_entities_csv_has_one_row_per_entity_with_sources_and_data():
    [header, ip, *_] = rows(report.render(make_result(), "csv"))
    assert header == ["tipo", "valor", "fuentes", "confianza", "primera_vez", "padre", "datos"]
    assert ip[:3] == ["ip", "1.1.1.1", "dns"] and ip[5] == "domain:example.com"
    assert ip[6] == '{"asn": 13335}'


def test_values_that_look_like_formulas_are_neutralised():
    table = rows(report.render(make_result(), "csv"))
    assert table[2][:2] == ["record", "'=cmd|calc"]


def test_relations_csv_lists_parent_to_child_edges():
    table = rows(report.render(make_result(), "csv-relations"))
    assert table[0] == ["origen", "destino", "tipo_destino", "fuentes"]
    assert ["domain:example.com", "ip:1.1.1.1", "ip", "dns"] in table
    assert len(table) == 4  # cabecera + ip + record + hallazgo


def test_findings_csv_has_only_findings_with_a_one_line_recommendation():
    [header, row] = rows(report.render(make_result(), "csv-findings"))
    assert header[:2] == ["regla", "severidad"]
    assert row[:2] == ["spf-permissive", "high"]
    assert row[3] == "record:dns:example.com" and "v=spf1 +all" in row[4]
    assert row[5] == "Cierra el registro."


def test_empty_scan_still_exports_the_header():
    empty = ScanResult(target=Entity(type=EntityType.DOMAIN, value="a.com"), depth=1)
    assert len(rows(report.render(empty, "csv-findings"))) == 1


def test_export_command_writes_the_csv_with_its_own_extension(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # el informe por defecto va a ./reports
    db = tmp_path / "s.db"
    with Storage(db) as storage:
        scan_id = storage.save(make_result())
    out = tmp_path / "x"
    result = runner.invoke(
        app, ["export", str(scan_id), "-f", "csv-findings", "--db", str(db), "-o", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert rows(out.read_text(encoding="utf-8"))[1][0] == "spf-permissive"
    default = runner.invoke(app, ["export", str(scan_id), "-f", "csv", "--db", str(db), "--json"])
    assert default.exit_code == 0
    assert "entities.csv" in default.stdout
