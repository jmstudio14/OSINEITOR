"""Diálogo «Nuevo scan»: lo que pide el usuario se convierte en un `ScanRequest` válido."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from osineitor_gui.ui.new_scan_dialog import NewScanDialog  # noqa: E402


def make_dialog(qtbot) -> NewScanDialog:
    dialog = NewScanDialog()
    qtbot.addWidget(dialog)
    return dialog


def test_defaults_leave_everything_to_the_cli(qtbot):
    dialog = make_dialog(qtbot)
    dialog.target.setText("  example.com ")
    dialog.accept()
    request = dialog.request()
    assert request.target.strip() == "example.com"
    assert request.kind == "auto" and request.depth is None
    assert request.max_entities is None and request.max_requests is None
    assert request.max_time is None
    assert request.to_args()[:6] == [
        "--no-color",
        "scan",
        "--depth",
        "2",
        "--ndjson",
        "--control-stdin",
    ]


def test_the_detected_type_follows_what_is_typed(qtbot):
    dialog = make_dialog(qtbot)
    assert dialog.detected.text() == ""
    dialog.target.setText("8.8.8.8")
    assert dialog.detected.text().endswith("ip")
    dialog.target.setText("")
    assert dialog.detected.text() == ""


def test_zero_means_unlimited_and_is_not_the_default(qtbot):
    dialog = make_dialog(qtbot)
    dialog.target.setText("example.com")
    dialog.max_entities.setValue(0)
    dialog.max_requests.setValue(50)
    dialog.max_time.setValue(0)
    dialog.depth.setValue(3)
    dialog.kind.setCurrentIndex(dialog.kind.findData("domain"))
    dialog.accept()
    request = dialog.request()
    assert (request.max_entities, request.max_requests, request.max_time) == (0, 50, 0)
    assert request.depth == 3 and request.kind == "domain"
    args = request.to_args()
    assert args[args.index("--max-entities") + 1] == "0"
    assert args[args.index("--max-requests") + 1] == "50"
    assert args[args.index("--max-time") + 1] == "0"


def test_checkboxes_reach_the_request(qtbot):
    dialog = make_dialog(qtbot)
    dialog.target.setText("example.com")
    dialog.no_save.setChecked(True)
    dialog.refresh.setChecked(True)
    dialog.accept()
    assert dialog.request().no_save and dialog.request().refresh and not dialog.request().no_cache


def test_an_empty_target_shows_the_error_and_keeps_the_dialog_open(qtbot):
    dialog = make_dialog(qtbot)
    dialog.show()
    dialog.accept()
    assert dialog.request() is None and dialog.isVisible()
    assert not dialog.error.isHidden() and "objetivo" in dialog.error.text()


def test_no_cache_and_refresh_together_are_rejected(qtbot):
    dialog = make_dialog(qtbot)
    dialog.show()
    dialog.target.setText("example.com")
    dialog.no_cache.setChecked(True)
    dialog.refresh.setChecked(True)
    dialog.accept()
    assert dialog.request() is None and dialog.isVisible()
    assert "contradictorios" in dialog.error.text()


def test_it_never_asks_for_active_modules_or_private_networks(qtbot):
    dialog = make_dialog(qtbot)
    dialog.target.setText("example.com")
    dialog.accept()
    request = dialog.request()
    args = request.to_args()
    assert not request.active and not request.allow_private
    assert "--active" not in args and "--allow-private" not in args
