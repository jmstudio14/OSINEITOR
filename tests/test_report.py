from __future__ import annotations

import json

from typer.testing import CliRunner

from osineitor import report
from osineitor.cli import app
from osineitor.models import Entity, EntityType, ScanEvent, ScanResult
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
