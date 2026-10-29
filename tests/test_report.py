from __future__ import annotations

import json

from typer.testing import CliRunner

from osineitor import report
from osineitor.cli import app
from osineitor.models import Entity, EntityType, Observation, ScanEvent, ScanResult
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
