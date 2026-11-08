"""Diálogo «Nuevo scan»: lo que pide el usuario se convierte en un `ScanRequest` válido."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402

from osineitor_gui.ui import risk_dialog  # noqa: E402
from osineitor_gui.ui.new_scan_dialog import NewScanDialog  # noqa: E402


def make_dialog(qtbot, modules=None) -> NewScanDialog:
    dialog = NewScanDialog(None, modules)
    qtbot.addWidget(dialog)
    return dialog


def mod(name, *, passive=True, key=None, configured=False) -> dict:
    return {
        "name": name,
        "description": f"descripción de {name}",
        "passive": passive,
        "requires_key": key,
        "key_configured": configured,
    }


CATALOG = [
    mod("dns"),
    mod("rdap"),
    mod("portscan", passive=False),
    mod("shodan", key="shodan"),
    mod("hibp", key="hibp", configured=True),
]


def item(dialog: NewScanDialog, name: str):
    return next(
        dialog.module_list.item(i)
        for i in range(dialog.module_list.count())
        if dialog.module_list.item(i).data(Qt.ItemDataRole.UserRole) == name
    )


def answers(monkeypatch, *, active=True, private=True) -> dict[str, int]:
    """Sustituye las confirmaciones por la respuesta del usuario y cuenta las preguntas."""
    asked = {"active": 0, "private": 0}

    def make(kind, answer):
        def confirm(parent=None):
            asked[kind] += 1
            return answer

        return confirm

    monkeypatch.setattr(risk_dialog, "confirm_active", make("active", active))
    monkeypatch.setattr(risk_dialog, "confirm_private", make("private", private))
    return asked


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


def test_by_default_it_asks_for_no_active_modules_or_private_networks(qtbot):
    dialog = make_dialog(qtbot)
    dialog.target.setText("example.com")
    dialog.accept()
    request = dialog.request()
    args = request.to_args()
    assert not request.active and not request.allow_private
    assert "--active" not in args and "--allow-private" not in args


# --- selector de módulos, opciones de riesgo y propósito (G7) -------------------------------


def test_no_catalog_hides_the_selector_and_says_so(qtbot):
    for catalog in (None, []):
        dialog = make_dialog(qtbot, catalog)
        assert dialog.module_list.isHidden()
        assert dialog.modules_note.text() and not dialog.modules_note.isHidden()
        dialog.target.setText("example.com")
        dialog.accept()
        assert dialog.request().modules == ()


def test_the_catalog_lists_every_module_unchecked(qtbot):
    dialog = make_dialog(qtbot, CATALOG)
    dialog.show()
    assert dialog.module_list.isVisible()
    assert dialog.module_list.count() == len(CATALOG)
    states = {dialog.module_list.item(i).checkState() for i in range(dialog.module_list.count())}
    assert states == {Qt.CheckState.Unchecked}


def test_modules_without_key_are_disabled_with_the_reason(qtbot):
    dialog = make_dialog(qtbot, CATALOG)
    shodan, hibp = item(dialog, "shodan"), item(dialog, "hibp")
    assert not shodan.flags() & Qt.ItemFlag.ItemIsEnabled
    assert not shodan.flags() & Qt.ItemFlag.ItemIsUserCheckable
    assert "shodan" in shodan.toolTip()
    assert hibp.flags() & Qt.ItemFlag.ItemIsEnabled  # tiene su key


def test_active_modules_are_disabled_until_the_active_box_is_confirmed(qtbot, monkeypatch):
    asked = answers(monkeypatch)
    dialog = make_dialog(qtbot, CATALOG)
    portscan = item(dialog, "portscan")
    assert not portscan.flags() & Qt.ItemFlag.ItemIsEnabled
    dialog.active_box.setChecked(True)
    assert asked["active"] == 1
    assert portscan.flags() & Qt.ItemFlag.ItemIsEnabled
    assert item(dialog, "dns").flags() & Qt.ItemFlag.ItemIsEnabled


def test_active_box_confirmed_sets_both_flags(qtbot, monkeypatch):
    answers(monkeypatch, active=True)
    dialog = make_dialog(qtbot)
    dialog.target.setText("example.com")
    dialog.active_box.setChecked(True)
    dialog.accept()
    request = dialog.request()
    assert request.active and request.confirm_active
    assert "--active" in request.to_args()


def test_active_box_declined_unchecks_itself(qtbot, monkeypatch):
    asked = answers(monkeypatch, active=False)
    dialog = make_dialog(qtbot, CATALOG)
    dialog.target.setText("example.com")
    dialog.active_box.setChecked(True)
    assert asked["active"] == 1 and not dialog.active_box.isChecked()
    assert not item(dialog, "portscan").flags() & Qt.ItemFlag.ItemIsEnabled
    dialog.accept()
    request = dialog.request()
    assert request.active is False and request.confirm_active is False
    assert "--active" not in request.to_args()


def test_unchecking_active_resets_the_confirmation_and_the_active_modules(qtbot, monkeypatch):
    asked = answers(monkeypatch)
    dialog = make_dialog(qtbot, CATALOG)
    dialog.target.setText("example.com")
    dialog.active_box.setChecked(True)
    item(dialog, "portscan").setCheckState(Qt.CheckState.Checked)
    item(dialog, "dns").setCheckState(Qt.CheckState.Checked)
    dialog.active_box.setChecked(False)
    assert item(dialog, "portscan").checkState() == Qt.CheckState.Unchecked
    assert item(dialog, "dns").checkState() == Qt.CheckState.Checked  # los pasivos se conservan
    dialog.accept()
    request = dialog.request()
    assert request.active is False and request.confirm_active is False
    assert request.modules == ("dns",)
    dialog.active_box.setChecked(True)  # volver a marcarla vuelve a preguntar
    assert asked["active"] == 2


def test_private_box_follows_the_same_rule(qtbot, monkeypatch):
    asked = answers(monkeypatch, private=False)
    dialog = make_dialog(qtbot)
    dialog.target.setText("192.168.1.1")
    dialog.private_box.setChecked(True)
    assert asked["private"] == 1 and not dialog.private_box.isChecked()
    dialog.accept()
    assert dialog.request().allow_private is False
    assert "--allow-private" not in dialog.request().to_args()

    answers(monkeypatch, private=True)
    dialog.private_box.setChecked(True)
    dialog.accept()
    request = dialog.request()
    assert request.allow_private and request.confirm_private
    dialog.private_box.setChecked(False)
    dialog.accept()
    assert dialog.request().allow_private is False and dialog.request().confirm_private is False


def test_selected_modules_go_to_the_request_in_order(qtbot):
    dialog = make_dialog(qtbot, CATALOG)
    dialog.target.setText("example.com")
    item(dialog, "hibp").setCheckState(Qt.CheckState.Checked)
    item(dialog, "dns").setCheckState(Qt.CheckState.Checked)
    dialog.accept()
    args = dialog.request().to_args()
    assert dialog.request().modules == ("dns", "hibp")
    assert [args[i + 1] for i, a in enumerate(args) if a == "-m"] == ["dns", "hibp"]


def test_ticking_nothing_means_the_cli_defaults(qtbot):
    dialog = make_dialog(qtbot, CATALOG)
    dialog.target.setText("example.com")
    dialog.accept()
    assert dialog.request().modules == () and "-m" not in dialog.request().to_args()


def test_the_view_cannot_skip_the_confirmation(qtbot, monkeypatch):
    """Aunque la vista marque las casillas, sin confirmar no salen las opciones de riesgo."""
    answers(monkeypatch, active=False, private=False)
    dialog = make_dialog(qtbot, CATALOG)
    dialog.target.setText("example.com")
    dialog.active_box.setChecked(True)
    dialog.private_box.setChecked(True)
    dialog.accept()
    args = dialog.request().to_args()
    assert "--active" not in args and "--allow-private" not in args


def test_the_note_follows_the_active_box(qtbot, monkeypatch):
    answers(monkeypatch)
    dialog = make_dialog(qtbot)
    passive_text = dialog.risk_note.text()
    dialog.active_box.setChecked(True)
    assert dialog.risk_note.text() != passive_text
    dialog.active_box.setChecked(False)
    assert dialog.risk_note.text() == passive_text


def test_the_purpose_reaches_the_request(qtbot):
    dialog = make_dialog(qtbot)
    dialog.target.setText("alguien@example.com")
    dialog.purpose.setText("  auditoría autorizada ")
    dialog.accept()
    args = dialog.request().to_args()
    assert args[args.index("--purpose") + 1] == "auditoría autorizada"


def test_an_empty_purpose_is_not_sent(qtbot):
    dialog = make_dialog(qtbot)
    dialog.target.setText("example.com")
    dialog.accept()
    assert "--purpose" not in dialog.request().to_args()


def test_an_invalid_purpose_is_shown_inline(qtbot):
    dialog = make_dialog(qtbot)
    dialog.show()
    dialog.target.setText("example.com")
    dialog.purpose.setText("x" * 501)
    dialog.accept()
    assert dialog.request() is None and dialog.isVisible()
    assert "500" in dialog.error.text() and not dialog.error.isHidden()
