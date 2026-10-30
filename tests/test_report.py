from __future__ import annotations

import hashlib
import json

import pytest
from typer.testing import CliRunner

from osineitor import report
from osineitor.cli import app
from osineitor.models import Entity, EntityType, Evidence, Observation, ScanEvent, ScanResult
from osineitor.storage import Storage

SEED = Entity(type=EntityType.DOMAIN, value="example.com")
RESULT = ScanResult(
    target=SEED,
    depth=1,
    entities=[
        Entity(
            type=EntityType.URL,
            value="https://example.com/a|b<script>",
            source="wayback",
            parent=SEED.key,
            data={"archived": True},
        ),
        Entity(
            type=EntityType.RECORD,
            value="dns:example.com",
            source="dns",
            data={"A": ["1.2.3.4"], "SPF": None},
        ),
    ],
    events=[ScanEvent(kind="error", module="crtsh", message="timeout <x>", entity=SEED.key)],
)


def test_json_roundtrip():
    assert ScanResult.model_validate(json.loads(report.render(RESULT, "json"))) == RESULT


def test_markdown_escapes_pipes():
    md = report.render(RESULT, "md")
    assert "## url (1)" in md
    assert "a\\|b" in md
    assert "**A**: 1.2.3.4" in md
    assert "SPF" not in md  # vacíos omitidos


SEEN_BY_TWO = ScanResult(
    target=SEED,
    depth=1,
    entities=[
        Entity(
            type=EntityType.IP,
            value="1.2.3.4",
            source="dns",
            parent=SEED.key,
            confidence="alto",
            observations=[
                Observation(module="dns", query=SEED.key),
                Observation(module="crtsh", query=SEED.key),
            ],
        )
    ],
)


def test_reports_list_every_source_that_saw_an_entity():
    assert "| dns, crtsh |" in report.render(SEEN_BY_TWO, "md")
    assert "<td class='muted'>dns, crtsh</td>" in report.render(SEEN_BY_TWO, "html")


def test_reports_show_when_each_entity_was_last_seen():
    seen = SEEN_BY_TWO.entities[0].last_seen.strftime("%Y-%m-%d %H:%M UTC")
    assert f"| dns, crtsh | alto | {seen} |" in report.render(SEEN_BY_TWO, "md")
    assert "<td>alto</td>" in report.render(SEEN_BY_TWO, "html")
    assert f"<td class='muted'>{seen}</td>" in report.render(SEEN_BY_TWO, "html")
    # sin observaciones (scan antiguo) la celda queda vacía
    assert "| wayback |  |  |" in report.render(RESULT, "md")


def test_reports_show_the_source_of_data_saved_before_observations_existed():
    assert "| wayback |" in report.render(RESULT, "md")
    assert "<td class='muted'>wayback</td>" in report.render(RESULT, "html")


def test_show_lists_every_source_in_the_table(tmp_path):
    db = tmp_path / "db.sqlite"
    storage = Storage(db)
    scan_id = storage.save(SEEN_BY_TWO.model_copy(deep=True))
    storage.close()
    res = CliRunner().invoke(app, ["show", str(scan_id), "--db", str(db)])
    assert res.exit_code == 0, res.output
    assert "dns," in res.output and "crtsh" in res.output  # Rich parte la celda estrecha


def test_html_escapes_content():
    html = report.render(RESULT, "html")
    assert "<script>" not in html.split("</style>", 1)[1]
    assert "&lt;script&gt;" in html
    assert "timeout &lt;x&gt;" in html


def test_export_command(tmp_path):
    db = tmp_path / "db.sqlite"
    storage = Storage(db)
    scan_id = storage.save(RESULT.model_copy(deep=True))
    storage.close()
    out = tmp_path / "r.md"
    res = CliRunner().invoke(
        app, ["export", str(scan_id), "-f", "md", "-o", str(out), "--db", str(db)]
    )
    assert res.exit_code == 0, res.output
    assert out.read_text(encoding="utf-8").startswith(
        f"# OSINEITOR — domain: example.com (scan #{scan_id})"
    )


# --- anexo de evidencias (F2.7) -----------------------------------------------------------------

BODY = b"respuesta original"
EVIDENCED = ScanResult(
    target=SEED,
    depth=1,
    evidence=[
        Evidence(
            module="crtsh",
            entity=SEED.key,
            kind="http",
            url="https://crt.sh/?q=%25.example.com&x=<script>alert(1)</script>|y",
            method="GET",
            status=200,
            sha256=hashlib.sha256(BODY).hexdigest(),
            size=len(BODY),
            body=BODY,
        ),
        Evidence(
            module="dns",
            entity=SEED.key,
            kind="dns",
            url="dns://example.com/A",
            method="DNS",
            sha256=hashlib.sha256(b"a").hexdigest(),
            size=1,
            truncated=True,
            body=b"a",
        ),
    ],
)


@pytest.mark.parametrize("fmt", ["html", "md"])
def test_reports_annex_lists_each_evidence_with_its_full_hash_and_the_digest(fmt):
    text = report.render(EVIDENCED, fmt)
    assert "Evidencias" in text
    for ev in EVIDENCED.evidence:
        assert ev.sha256 in text  # completo, no recortado
    assert EVIDENCED.evidence_digest in text
    assert "osineitor verify" in text
    assert "(recortada)" in text and "crtsh" in text and "200" in text


def test_html_annex_escapes_the_url_of_the_evidence():
    html = report.render(EVIDENCED, "html")
    assert "<script>alert" not in html.split("</style>", 1)[1]
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_markdown_annex_escapes_pipes_in_the_url():
    md = report.render(EVIDENCED, "md")
    assert r"\|y`" in md  # el | de la URL no rompe la tabla


@pytest.mark.parametrize("fmt", ["html", "md"])
def test_reports_without_evidence_say_so_instead_of_an_empty_table(fmt):
    text = report.render(RESULT, fmt)
    assert "no guardó evidencias" in text
    assert "SHA-256" not in text


def test_the_annex_names_the_scan_to_verify_once_it_is_saved(tmp_path):
    db = tmp_path / "db.sqlite"
    with Storage(db) as storage:
        scan_id = storage.save(EVIDENCED.model_copy(deep=True))
    out = tmp_path / "r.html"
    res = CliRunner().invoke(
        app, ["export", str(scan_id), "-f", "html", "-o", str(out), "--db", str(db)]
    )
    assert res.exit_code == 0, res.output
    assert f"osineitor verify {scan_id}" in out.read_text(encoding="utf-8")


def test_the_digest_in_the_report_is_the_one_verify_computes(tmp_path):
    db = tmp_path / "db.sqlite"
    with Storage(db) as storage:
        scan_id = storage.save(EVIDENCED.model_copy(deep=True))
    runner = CliRunner()
    verified = runner.invoke(app, ["verify", str(scan_id), "--db", str(db), "--json"])
    assert verified.exit_code == 0, verified.output
    digest = json.loads(verified.stdout)["evidence_digest"]
    assert digest == EVIDENCED.evidence_digest
    assert digest in report.render(EVIDENCED, "html")
