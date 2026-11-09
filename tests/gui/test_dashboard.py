"""Datos del panel principal: sin Qt, a partir de salidas de la CLI escritas a mano."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from osineitor_gui.dashboard import (
    DAILY_WINDOW,
    OTHERS,
    RECENT_SCANS,
    TOP_FINDINGS,
    aggregate,
    findings_of,
    parse_time,
    summarize_row,
    worst_severity,
)

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def finding(severity, title="Regla"):
    return {
        "type": "finding",
        "value": f"regla: {severity}",
        "data": {"severity": severity, "title": title},
    }


def row(scan_id, days_ago=0, entities=1, **digest):
    started = NOW - timedelta(days=days_ago, hours=1)
    return {
        "id": scan_id,
        "target": "example.com",
        "target_type": "domain",
        "entities": entities,
        "started_at": started.isoformat(),
        "status": "complete",
        **digest,
    }


def test_a_history_row_is_summarized_without_show():
    summary = summarize_row(
        row(
            1,
            entities=4,
            status="cancelled",
            severity={"high": 2, "critical": 1},
            by_type={"finding": 3, "ip": 1},
            modules={"ok": 1, "error": 1},
        )
    )
    assert summary.by_severity == {"high": 2, "critical": 1}
    assert summary.by_type == {"finding": 3, "ip": 1}
    assert summary.modules == {"ok": 1, "error": 1}
    assert summary.status == "cancelled" and summary.worst == "critical"
    assert (summary.target, summary.target_type, summary.entities) == ("example.com", "domain", 4)


def test_an_unknown_severity_counts_as_info_and_missing_fields_do_not_break():
    summary = summarize_row({"id": 1, "severity": {"rara": 2, "info": 1}})
    assert summary.by_severity == {"info": 3}
    assert summary.target == "" and summary.modules == {} and summary.findings == []


def test_findings_of_keeps_only_findings():
    result = {"entities": [finding("low"), {"type": "ip", "value": "9.9.9.9"}]}
    assert [e["type"] for e in findings_of(result)] == ["finding"]
    assert findings_of({}) == []


def test_worst_severity():
    assert worst_severity({"low": 1, "medium": 0}) == "low"
    assert worst_severity({"high": 1, "low": 3}) == "high"
    assert worst_severity({}) is None


def test_empty_history_gives_an_empty_overview_with_the_whole_window():
    overview = aggregate([], {}, NOW)
    assert overview.scans_total == 0 and overview.urgent == 0 and overview.worst is None
    assert len(overview.daily) == DAILY_WINDOW and sum(c for _d, c in overview.daily) == 0
    assert overview.catalog_total is None  # sin catálogo no se inventa un cero


def test_scans_in_the_last_week_are_compared_with_the_previous_one():
    history = [row(1, 0), row(2, 1), row(3, 6), row(4, 8), row(5, 20)]
    overview = aggregate(history, {}, NOW)
    assert (overview.scans_7d, overview.scans_prev_7d, overview.scans_delta) == (3, 1, 2)
    assert overview.scans_total == 5 and overview.entities_total == 5


def test_a_scan_dated_in_the_future_does_not_count_as_recent():
    assert aggregate([row(1, -2)], {}, NOW).scans_7d == 0


def test_daily_series_buckets_by_local_day_and_ignores_older_scans():
    overview = aggregate([row(1, 0), row(2, 0), row(3, 3), row(4, 30)], {}, NOW)
    counts = dict(overview.daily)
    assert counts[NOW.date()] == 2
    assert counts[NOW.date() - timedelta(days=3)] == 1
    assert sum(counts.values()) == 3
    assert [d for d, _c in overview.daily] == sorted(counts)


def test_a_bad_date_is_skipped_but_the_scan_still_counts():
    history = [{"id": 1, "entities": 4, "started_at": "ayer"}]
    overview = aggregate(history, {}, NOW)
    assert overview.scans_total == 1 and overview.entities_total == 4
    assert overview.scans_7d == 0
    assert parse_time("ayer") is None


def test_only_recent_scans_feed_the_severity_and_they_keep_the_history_order():
    history = [row(i, severity={"high": 1}) for i in range(12, 0, -1)]
    overview = aggregate(history, {}, NOW)
    assert [s.scan_id for s in overview.analyzed] == list(range(12, 2, -1))
    assert overview.severity == {"high": RECENT_SCANS}
    assert overview.urgent == RECENT_SCANS and overview.worst == "high"


def test_figures_do_not_wait_for_the_finding_titles():
    overview = aggregate([row(1, severity={"low": 2}, modules={"ok": 1})], {}, NOW)
    assert overview.severity == {"low": 2} and overview.modules_last == {"ok": 1}
    assert overview.findings == []


def test_types_fold_the_rest_into_others():
    by_type = {f"t{i}": 1 for i in range(10)}
    overview = aggregate([row(1, by_type=by_type)], {}, NOW)
    assert len(overview.types) == 9 and overview.types[-1] == (OTHERS, 2)


def test_findings_are_ranked_by_severity_then_recency_and_limited():
    findings = {
        2: [finding("low", "reciente"), finding("critical", "grave")],
        1: [finding("low", "antiguo")] * 10,
    }
    overview = aggregate([row(2), row(1)], findings, NOW)
    assert len(overview.findings) == TOP_FINDINGS
    assert overview.findings[0]["title"] == "grave" and overview.findings[0]["scan_id"] == 2
    assert overview.findings[1]["title"] == "reciente"


def test_modules_of_the_last_scan_and_the_catalog():
    catalog = [
        {"name": "a", "passive": True},
        {"name": "b", "passive": False},
        {"name": "c", "passive": True, "requires_key": "k", "key_configured": False},
        {"name": "d", "passive": True, "requires_key": "k", "key_configured": True},
    ]
    modules = {"ok": 1, "error": 1, "quota": 1, "skipped": 1}
    overview = aggregate([row(1, modules=modules)], {}, NOW, catalog)
    assert overview.modules_failed == 2
    assert overview.catalog_total == 4
    assert (overview.catalog_active, overview.catalog_missing_key) == (1, 1)
