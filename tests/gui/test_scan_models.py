"""Modelos de tabla de la vista de scan, alimentados a mano con una `ScanSession`."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402

from osineitor_gui.events import EntityFound, ModuleEnd, ModuleStart, ScanStart  # noqa: E402
from osineitor_gui.session import ScanSession  # noqa: E402
from osineitor_gui.ui.models import EntityTableModel, ModuleActivityModel  # noqa: E402


def entity(kind: str, value: str, source: str = "dns") -> EntityFound:
    return EntityFound({"type": kind, "value": value, "source": source, "data": {}})


def start(session: ScanSession, modules: list[str]) -> None:
    session.begin()
    session.feed(ScanStart("domain", "example.com", 1, modules, [], {}))


def cell(model, row: int, column: int, role=Qt.ItemDataRole.DisplayRole):
    return model.data(model.index(row, column), role)


def test_entities_are_listed_with_type_value_and_source():
    session = ScanSession()
    model = EntityTableModel(session)
    session.feed(entity("ip", "9.9.9.9", "rdap"))
    model.refresh()
    assert model.rowCount() == 1
    assert [cell(model, 0, c) for c in range(3)] == ["ip", "9.9.9.9", "rdap"]


def test_new_entities_are_inserted_without_resetting_the_model():
    session = ScanSession()
    model = EntityTableModel(session)
    session.feed(entity("ip", "9.9.9.9"))
    model.refresh()
    resets, inserts = [], []
    model.modelReset.connect(lambda: resets.append(1))
    model.rowsInserted.connect(lambda _p, first, last: inserts.append((first, last)))
    session.feed(entity("ip", "8.8.8.8"))
    session.feed(entity("host", "a.example.com"))
    model.refresh()
    assert model.rowCount() == 3 and not resets and inserts == [(1, 2)]


def test_refresh_without_news_emits_nothing():
    session = ScanSession()
    model = EntityTableModel(session)
    session.feed(entity("ip", "9.9.9.9"))
    model.refresh()
    changes = []
    model.rowsInserted.connect(lambda *_: changes.append(1))
    model.modelReset.connect(lambda: changes.append(1))
    model.refresh()
    assert not changes


def test_filter_by_type_and_text():
    session = ScanSession()
    model = EntityTableModel(session)
    for item in (
        entity("ip", "9.9.9.9"),
        entity("host", "mail.example.com"),
        entity("ip", "1.1.1.1"),
    ):
        session.feed(item)
    model.set_filter({"ip"}, "")
    assert model.rowCount() == 2
    model.set_filter({"ip"}, "1.1")
    assert cell(model, 0, 1) == "1.1.1.1" and model.rowCount() == 1
    model.set_filter(None, "MAIL")
    assert model.rowCount() == 1


def test_a_filtered_model_only_receives_matching_new_entities():
    session = ScanSession()
    model = EntityTableModel(session)
    model.set_filter({"ip"}, "")
    session.feed(entity("host", "a.example.com"))
    session.feed(entity("ip", "9.9.9.9"))
    model.refresh()
    assert model.rowCount() == 1 and cell(model, 0, 1) == "9.9.9.9"


def test_a_session_restart_resets_the_model():
    session = ScanSession()
    model = EntityTableModel(session)
    session.feed(entity("ip", "9.9.9.9"))
    model.refresh()
    session.begin()
    model.refresh()
    assert model.rowCount() == 0


def test_modules_show_their_status_and_numbers():
    session = ScanSession()
    model = ModuleActivityModel(session)
    start(session, ["dns", "bad"])
    session.feed(ModuleStart("dns", "example.com"))
    model.refresh()
    assert [cell(model, r, 1) for r in range(2)] == ["en curso", "pendiente"]

    session.feed(ModuleEnd("dns", "ok", "example.com", 3, 2, 1, 1500))
    session.feed(ModuleStart("bad", "example.com"))
    session.feed(ModuleEnd("bad", "error", "example.com", message="se rompió"))
    model.refresh()
    assert [cell(model, 0, c) for c in range(7)] == ["dns", "ok", 3, 2, 1, "1.5 s", ""]
    assert cell(model, 1, 1) == "error" and cell(model, 1, 6) == "se rompió"


def test_error_and_quota_stand_out_by_color():
    session = ScanSession()
    model = ModuleActivityModel(session)
    start(session, ["dns", "bad", "limited"])
    for name, status in (("dns", "ok"), ("bad", "error"), ("limited", "quota")):
        session.feed(ModuleStart(name, "example.com"))
        session.feed(ModuleEnd(name, status, "example.com"))
    model.refresh()
    role = Qt.ItemDataRole.ForegroundRole
    ok, error, quota = (cell(model, r, 1, role) for r in range(3))
    assert ok is None
    assert error is not None and quota is not None and error.color() != quota.color()
    assert cell(model, 1, 0, role) is None  # solo se colorea la columna de estado


def test_module_status_updates_emit_data_changed():
    session = ScanSession()
    model = ModuleActivityModel(session)
    start(session, ["dns"])
    model.refresh()
    changed = []
    model.dataChanged.connect(lambda *_: changed.append(1))
    session.feed(ModuleStart("dns", "example.com"))
    model.refresh()
    assert changed
