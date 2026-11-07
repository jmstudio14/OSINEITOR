"""F7.4: línea temporal con las fechas de los datos."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from osineitor import timeline
from osineitor.cli import app
from osineitor.models import Entity, EntityType, ScanResult
from osineitor.storage import Storage

runner = CliRunner()
STARTED = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def entity(kind: EntityType, value: str, **data) -> Entity:
    return Entity(type=kind, value=value, data=data, source="fake")


def result(*entities: Entity) -> ScanResult:
    return ScanResult(
        target=Entity(type=EntityType.DOMAIN, value="example.com"),
        depth=1,
        started_at=STARTED,
        entities=list(entities),
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-01-02", datetime(2026, 1, 2, tzinfo=UTC)),
        ("2026-01-02T03:04:05Z", datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)),
        ("2026-01-02T03:04:05+02:00", datetime(2026, 1, 2, 1, 4, 5, tzinfo=UTC)),
        ("2026-01-02T03:04:05", datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)),
        ("20260102030405", datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)),
    ],
)
def test_parse_moment_accepts_iso_and_wayback_stamps(text, expected):
    assert timeline.parse_moment(text) == expected.astimezone(UTC)


@pytest.mark.parametrize("bad", ["ayer", "", "   ", None, 12345, "2026-13-40", ["2026-01-01"]])
def test_parse_moment_rejects_everything_else(bad):
    assert timeline.parse_moment(bad) is None


def test_events_come_ordered_with_label_and_origin():
    events = timeline.build(
        result(
            entity(
                EntityType.RECORD, "rdap:example.com", created="1995-08-14", expires="2027-08-13"
            ),
            entity(
                EntityType.CERTIFICATE, "ab" * 32, not_before="2026-10-01", not_after="2027-01-01"
            ),
            entity(EntityType.RECORD, "wayback:example.com", first_seen="20010203040506"),
            entity(EntityType.BREACH, "hibp:Adobe", date="2013-10-04"),
        )
    )
    assert [(e["at"][:10], e["event"]) for e in events] == [
        ("1995-08-14", "Alta o creación"),
        ("2001-02-03", "Primera vez visto por la fuente"),
        ("2013-10-04", "Fecha de la filtración"),
        ("2026-10-01", "Certificado válido desde"),
        ("2027-01-01", "Certificado caduca"),
        ("2027-08-13", "Caducidad"),
    ]
    assert events[0]["entity"] == "record:rdap:example.com" and events[0]["source"] == "fake"


def test_future_dates_are_flagged_relative_to_the_scan():
    events = timeline.build(
        result(
            entity(
                EntityType.RECORD, "rdap:example.com", created="2020-01-01", expires="2027-01-01"
            )
        )
    )
    assert [(e["field"], e["future"]) for e in events] == [("created", False), ("expires", True)]


def test_date_only_counts_in_a_breach_and_unparseable_values_are_skipped():
    events = timeline.build(
        result(
            entity(EntityType.RECORD, "x:y", date="2020-01-01", created="no es una fecha"),
            entity(EntityType.SERVICE, "1.1.1.1:80", port=80, last_update=None),
        )
    )
    assert events == []


def test_the_seed_counts_too():
    seed = Entity(type=EntityType.DOMAIN, value="example.com", data={"created": "2000-01-01"})
    res = ScanResult(target=seed, depth=1, started_at=STARTED)
    assert [e["entity"] for e in timeline.build(res)] == ["domain:example.com"]


def test_cli_timeline_json_and_table(tmp_path):
    db = tmp_path / "t.db"
    with Storage(db) as store:
        store.save(result(entity(EntityType.RECORD, "rdap:example.com", created="1995-08-14")))
    out = runner.invoke(app, ["timeline", "1", "--db", str(db), "--json"])
    data = json.loads(out.stdout)
    assert data["scan_id"] == 1 and data["target"] == "domain:example.com"
    assert data["events"][0]["event"] == "Alta o creación"
    table = runner.invoke(app, ["timeline", "1", "--db", str(db)])
    assert table.exit_code == 0 and "1995-08-14" in table.stdout
    assert runner.invoke(app, ["timeline", "9", "--db", str(db)]).exit_code != 0
    empty = Storage(db)
    empty.save(result())
    empty.close()
    assert "Sin fechas" in runner.invoke(app, ["timeline", "2", "--db", str(db)]).stdout
