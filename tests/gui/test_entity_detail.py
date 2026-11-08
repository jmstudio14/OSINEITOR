"""Panel de detalle de entidad: fuente, origen y campos de `data`."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from osineitor_gui.ui.entity_detail import EntityDetail  # noqa: E402


def rows(detail: EntityDetail) -> list[tuple[str, str]]:
    table = detail.table
    return [(table.item(r, 0).text(), table.item(r, 1).text()) for r in range(table.rowCount())]


def make_detail(qtbot) -> EntityDetail:
    detail = EntityDetail()
    qtbot.addWidget(detail)
    detail.show()
    return detail


def test_without_entity_it_shows_the_hint(qtbot):
    detail = make_detail(qtbot)
    assert detail.placeholder.isVisible() and not detail.table.isVisible()


def test_it_lists_source_origin_and_data(qtbot):
    detail = make_detail(qtbot)
    detail.show_entity(
        {
            "type": "ip",
            "value": "9.9.9.9",
            "source": "rdap",
            "parent": "example.com",
            "data": {"org": "ACMÉ ñ", "asn": 64500, "ports": [80, 443], "geo": {"cc": "ES"}},
        }
    )
    assert not detail.placeholder.isVisible() and detail.table.isVisible()
    assert rows(detail) == [
        ("Fuente", "rdap"),
        ("Origen", "example.com"),
        ("org", "ACMÉ ñ"),
        ("asn", "64500"),
        ("ports", "[80, 443]"),
        ("geo", '{"cc": "ES"}'),
    ]


def test_missing_fields_show_empty_not_none(qtbot):
    detail = make_detail(qtbot)
    detail.show_entity({"type": "ip", "value": "9.9.9.9", "source": None, "parent": None})
    assert rows(detail) == [("Fuente", ""), ("Origen", "")]


def test_selecting_nothing_clears_the_previous_entity(qtbot):
    detail = make_detail(qtbot)
    detail.show_entity({"type": "ip", "value": "1.1.1.1", "data": {"a": "b"}})
    detail.show_entity(None)
    assert detail.table.rowCount() == 0 and detail.placeholder.isVisible()
