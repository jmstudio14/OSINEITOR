"""Ventana principal (G2): menús, barra, tema, geometría y localizador de la CLI.

Necesita PySide6 (extra `gui`) y pytest-qt; sin ellos se omite. Corre sin pantalla.
"""

from __future__ import annotations

import json
import os

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QStyleHints  # noqa: E402
from PySide6.QtWidgets import QFileDialog, QMessageBox, QToolBar  # noqa: E402

from osineitor_gui import __version__, app, legal  # noqa: E402
from osineitor_gui.cli_locator import CliNotFound  # noqa: E402
from osineitor_gui.scan_request import ScanRequest  # noqa: E402
from osineitor_gui.settings import GuiSettings, settings_path  # noqa: E402
from osineitor_gui.ui import main_window  # noqa: E402
from osineitor_gui.ui.history_panel import HistoryPanel  # noqa: E402
from osineitor_gui.ui.legal_dialog import LegalDialog  # noqa: E402
from osineitor_gui.ui.main_window import MainWindow  # noqa: E402
from osineitor_gui.ui.new_scan_dialog import NewScanDialog  # noqa: E402
from tests.gui.fakecli import CLI as FAKE_CLI  # noqa: E402
from tests.gui.fakecli import save_scan, use_modules  # noqa: E402

CLI = ["python", "-m", "osineitor"]


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("OSINEITOR_GUI_CONFIG_DIR", str(tmp_path / "gui"))
    yield
    QGuiApplication.styleHints().unsetColorScheme()  # el tema es global: no se filtra entre tests


REAL_RELOAD = HistoryPanel.reload


@pytest.fixture(autouse=True)
def stub_history(monkeypatch):
    """Sin esto cada ventana lanzaría `history` contra la CLI al abrirse; los tests que lo
    necesitan usan `real_history`."""
    reloads = []
    monkeypatch.setattr(HistoryPanel, "reload", lambda self: reloads.append(1))
    return reloads


@pytest.fixture
def real_history(monkeypatch):
    monkeypatch.setattr(HistoryPanel, "reload", REAL_RELOAD)


def make_window(qtbot, settings=None, cli=CLI, cli_error=None) -> MainWindow:
    window = MainWindow(settings or GuiSettings(), cli, cli_error)
    qtbot.addWidget(window)
    return window


def labels(actions) -> list[str]:
    return [a.text().replace("&", "") for a in actions if not a.isSeparator()]


def test_menus_have_only_actions_that_work_today(qtbot):
    window = make_window(qtbot)
    menus = {a.text().replace("&", ""): a.menu() for a in window.menuBar().actions()}
    assert list(menus) == ["Archivo", "Ver", "Ayuda"]
    assert labels(menus["Archivo"].actions()) == [
        "Nuevo scan…",
        "Abrir scan guardado…",
        "Exportar scan…",
        "Cancelar scan",
        "Salir",
    ]
    assert labels(menus["Ayuda"].actions()) == ["Uso responsable", "Acerca de"]
    assert "Historial" in labels(menus["Ver"].actions())
    theme = next(a.menu() for a in menus["Ver"].actions() if a.menu())
    assert labels(theme.actions()) == ["Sistema", "Claro", "Oscuro"]
    disabled = [a for m in menus.values() for a in m.actions() if not a.isEnabled()]
    # Sin scan en marcha no hay nada que cancelar, ni scan guardado que exportar.
    assert disabled == [window.action_export, window.action_cancel]


def test_toolbar_has_new_scan_cancel_export_and_quit(qtbot):
    window = make_window(qtbot)
    [toolbar] = window.findChildren(QToolBar)
    assert toolbar.actions() == [
        window.action_new,
        window.action_cancel,
        window.action_export,
        window.action_quit,
    ]


def test_new_scan_needs_the_cli(qtbot):
    assert make_window(qtbot).action_new.isEnabled()
    assert not make_window(qtbot, cli=None, cli_error="falta").action_new.isEnabled()


def test_new_scan_action_opens_the_dialog(qtbot):
    window = make_window(qtbot)
    window.action_new.trigger()
    assert window.findChild(NewScanDialog) is not None


def test_quit_action_closes_the_window(qtbot):
    window = make_window(qtbot)
    window.show()
    window.action_quit.trigger()
    assert not window.isVisible()


@pytest.mark.parametrize(
    ("theme", "scheme"),
    [
        ("light", Qt.ColorScheme.Light),
        ("dark", Qt.ColorScheme.Dark),
        ("system", Qt.ColorScheme.Unknown),
    ],
)
def test_choosing_a_theme_asks_qt_for_that_color_scheme(qtbot, monkeypatch, theme, scheme):
    """La plataforma `offscreen` ignora el esquema (en Windows sí cambia): se comprueba la orden."""
    requested = []
    monkeypatch.setattr(QStyleHints, "setColorScheme", lambda self, s: requested.append(s))
    make_window(qtbot).theme_actions[theme].trigger()
    assert requested == [scheme]


@pytest.mark.parametrize("theme", ["light", "dark", "system"])
def test_choosing_a_theme_saves_it_and_marks_only_that_one(qtbot, theme):
    settings = GuiSettings(theme="dark" if theme == "system" else "system")
    window = make_window(qtbot, settings)
    window.theme_actions[theme].trigger()
    assert settings.theme == theme
    assert GuiSettings.load().theme == theme
    assert window.theme_actions[theme].isChecked()
    assert sum(a.isChecked() for a in window.theme_actions.values()) == 1


def test_the_saved_theme_is_checked_on_start(qtbot):
    window = make_window(qtbot, GuiSettings(theme="dark"))
    assert window.theme_actions["dark"].isChecked()


def test_geometry_is_saved_on_close_and_restored(qtbot):
    settings = GuiSettings()
    window = make_window(qtbot, settings)
    window.resize(701, 503)
    window.close()
    assert settings.window_geometry
    assert GuiSettings.load().window_geometry == settings.window_geometry
    again = make_window(qtbot, GuiSettings.load())
    assert (again.width(), again.height()) == (701, 503)


def test_a_corrupt_saved_geometry_does_not_break_the_start(qtbot):
    window = make_window(qtbot, GuiSettings(window_geometry="no-es-base64!!"))
    assert window.width() > 0


def test_status_bar_shows_the_cli_or_the_error(qtbot):
    assert "python -m osineitor" in make_window(qtbot).statusBar().currentMessage()
    window = make_window(qtbot, cli=None, cli_error="No se encuentra la CLI de OSINEITOR")
    message = window.statusBar().currentMessage()
    assert "CLI no encontrada" in message


def test_legal_menu_shows_the_responsible_use_text(qtbot):
    window = make_window(qtbot)
    window.action_legal.trigger()
    dialog = window.findChild(LegalDialog)
    assert dialog is not None and dialog.windowTitle() == legal.LEGAL_TITLE
    assert dialog.text.toPlainText() == legal.LEGAL_TEXT
    assert dialog.text.isReadOnly()


def test_about_menu_shows_the_version(qtbot, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "about", lambda *args: shown.append(args))
    make_window(qtbot).action_about.trigger()
    assert len(shown) == 1 and __version__ in shown[0][2]


def settled(view) -> bool:
    return view.session.finished and not view._timer.isActive()


def open_scan(qtbot, monkeypatch, modules: str, **kwargs):
    use_modules(monkeypatch, modules)
    # Al cerrar la ventana al final del test, un scan vivo preguntaría: responde que sí.
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    window = make_window(qtbot, cli=FAKE_CLI)
    view = window.open_scan(ScanRequest(target="example.com", kind="domain", **kwargs))
    return window, view


def test_opening_a_scan_adds_a_tab_with_progress_and_enables_cancel(qtbot, monkeypatch):
    window, view = open_scan(qtbot, monkeypatch, "fast,hang")
    assert window.tabs.count() == 1 and window.stack.currentWidget() is window.tabs
    assert window.action_cancel.isEnabled()
    qtbot.waitUntil(lambda: "1 entidades" in window.summary.text(), timeout=30_000)
    assert "en curso" in window.summary.text()
    window.action_cancel.trigger()
    qtbot.waitUntil(lambda: settled(view), timeout=30_000)
    assert not window.action_cancel.isEnabled()
    assert window.tabs.tabText(0) == "example.com (cancelado)"
    assert "cancelado" in window.summary.text()


def test_the_status_bar_shows_the_finished_scan(qtbot, monkeypatch):
    window, view = open_scan(qtbot, monkeypatch, "fast", no_save=True)
    qtbot.waitUntil(lambda: settled(view), timeout=30_000)
    assert window.summary.text().endswith("completo")
    assert window.progress.value() == window.progress.maximum() == view.session.total


def test_closing_a_running_tab_asks_and_cancels(qtbot, monkeypatch):
    window, view = open_scan(qtbot, monkeypatch, "fast,hang", no_save=True)
    qtbot.waitUntil(lambda: bool(view.session.entities), timeout=30_000)
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.No)
    window.tabs.tabCloseRequested.emit(0)
    assert window.tabs.count() == 1 and view.is_running  # respondió que no
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    window.tabs.tabCloseRequested.emit(0)
    assert window.tabs.count() == 0 and window.stack.currentIndex() == 0
    assert not view._runner.running  # la CLI no queda huérfana


def test_closing_the_window_with_a_running_scan_stops_the_cli(qtbot, monkeypatch):
    window, view = open_scan(qtbot, monkeypatch, "fast,hang", no_save=True)
    qtbot.waitUntil(lambda: bool(view.session.entities), timeout=30_000)
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.No)
    window.show()
    window.close()
    assert window.isVisible() and view._runner.running  # «No»: la ventana se queda
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    window.close()
    assert not window.isVisible() and not view._runner.running


def test_main_shows_the_dialog_when_the_cli_is_missing(qtbot, monkeypatch):
    def missing():
        raise CliNotFound("No se encuentra la CLI de OSINEITOR (osineitor).")

    critical = []
    monkeypatch.setattr(app, "locate_cli", missing)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: critical.append(args))
    monkeypatch.setattr(app.QApplication, "exec", lambda: 0)
    monkeypatch.setattr(main_window.MainWindow, "show", lambda self: None)
    assert app.main(["osineitor-gui"]) == 0
    assert len(critical) == 1 and "No se encuentra la CLI" in critical[0][2]


def test_main_starts_with_the_located_cli(qtbot, monkeypatch):
    monkeypatch.setattr(app, "locate_cli", lambda: CLI)
    monkeypatch.setattr(app.QApplication, "exec", lambda: 0)
    monkeypatch.setattr(main_window.MainWindow, "show", lambda self: None)
    assert app.main(["osineitor-gui"]) == 0
    assert not settings_path().exists()  # arrancar no escribe preferencias


# --- historial, abrir y exportar (G4) ------------------------------------------------------------


def saved_window(qtbot, monkeypatch):
    """Ventana con la CLI falsa y un scan ya guardado (id 1) en el historial."""
    save_scan(monkeypatch)
    return make_window(qtbot, cli=FAKE_CLI)


def test_the_history_dock_loads_on_start_and_can_be_hidden(qtbot, stub_history):
    window = make_window(qtbot)
    window.show()
    qtbot.waitUntil(lambda: bool(stub_history), timeout=5000)  # carga inicial
    assert window.history_dock.isVisible()
    toggle = window.history_dock.toggleViewAction()
    toggle.trigger()
    assert not window.history_dock.isVisible()


def test_no_cli_disables_history_and_open_saved(qtbot, stub_history):
    window = make_window(qtbot, cli=None, cli_error="falta")
    assert not window.history.isEnabled() and not window.action_open_saved.isEnabled()
    qtbot.wait(50)
    assert not stub_history  # sin CLI no se intenta cargar


def test_open_saved_shows_and_reloads_the_history(qtbot, stub_history):
    window = make_window(qtbot)
    window.show()
    window.history_dock.hide()
    stub_history.clear()
    window.action_open_saved.trigger()
    assert window.history_dock.isVisible() and stub_history == [1]


def test_double_click_in_the_history_opens_the_saved_scan_once(qtbot, monkeypatch, real_history):
    window = saved_window(qtbot, monkeypatch)
    with qtbot.waitSignal(window.history.loaded, timeout=30_000):
        pass
    window.history.table.doubleClicked.emit(window.history.model.index(0, 0))
    qtbot.waitUntil(lambda: window.tabs.count() == 1, timeout=30_000)
    view = window.tabs.widget(0)
    assert view.scan_id == 1 and window.tabs.tabText(0) == "example.com #1"
    values = [view.entities_model.entity(r)["value"] for r in range(view.entities_model.rowCount())]
    assert "9.9.9.9" in values
    assert not view.is_running and not window.action_cancel.isEnabled()
    assert window.action_export.isEnabled()
    window.open_saved(1)  # ya abierto: activa la pestaña, no abre otra
    qtbot.wait(300)
    assert window.tabs.count() == 1


def test_opening_a_missing_scan_shows_the_error(qtbot, monkeypatch):
    use_modules(monkeypatch, "fast")
    shown = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a: shown.append(a))
    window = make_window(qtbot, cli=FAKE_CLI)
    window.open_saved(99)
    qtbot.waitUntil(lambda: bool(shown), timeout=30_000)
    assert "No se pudo abrir el scan" in shown[0][1] and window.tabs.count() == 0


@pytest.mark.parametrize(
    ("chosen", "name", "check"),
    [
        ("JSON (*.json)", "r.json", lambda text: json.loads(text)["scan_id"] == 1),
        ("Markdown (*.md)", "r.md", lambda text: "example.com" in text),
        ("HTML (*.html)", "r.html", lambda text: "<html" in text.lower()),
    ],
)
def test_export_writes_the_chosen_format(qtbot, monkeypatch, tmp_path, chosen, name, check):
    window = saved_window(qtbot, monkeypatch)
    window.open_saved(1)
    qtbot.waitUntil(lambda: window.tabs.count() == 1, timeout=30_000)
    target = tmp_path / name
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a: (str(target), chosen))
    window.action_export.trigger()
    qtbot.waitUntil(
        lambda: window.statusBar().currentMessage().startswith("Exportado"), timeout=30_000
    )
    assert check(target.read_text(encoding="utf-8"))


def test_export_without_extension_adds_the_one_of_the_format(qtbot, monkeypatch, tmp_path):
    window = saved_window(qtbot, monkeypatch)
    window.open_saved(1)
    qtbot.waitUntil(lambda: window.tabs.count() == 1, timeout=30_000)
    target = tmp_path / "informe"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a: (str(target), "HTML (*.html)"))
    window.action_export.trigger()
    qtbot.waitUntil((tmp_path / "informe.html").exists, timeout=30_000)


def test_cancelling_the_export_dialog_does_nothing(qtbot, monkeypatch, tmp_path):
    window = saved_window(qtbot, monkeypatch)
    window.open_saved(1)
    qtbot.waitUntil(lambda: window.tabs.count() == 1, timeout=30_000)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a: ("", ""))
    window.action_export.trigger()
    qtbot.wait(300)
    assert not window.statusBar().currentMessage().startswith("Exportado")
    assert list(tmp_path.glob("r.*")) == []


def test_a_live_scan_cannot_be_exported_until_it_is_saved_and_finished(
    qtbot, monkeypatch, stub_history
):
    window, view = open_scan(qtbot, monkeypatch, "fast,hang")
    assert not window.action_export.isEnabled()  # en marcha
    qtbot.waitUntil(lambda: bool(view.session.entities), timeout=30_000)
    window.action_cancel.trigger()
    qtbot.waitUntil(lambda: settled(view), timeout=30_000)
    assert view.scan_id == 1 and window.action_export.isEnabled()  # cancelado, pero guardado
    assert stub_history  # al guardarse el scan se recarga el historial


def test_a_scan_that_is_not_saved_cannot_be_exported(qtbot, monkeypatch):
    window, view = open_scan(qtbot, monkeypatch, "fast", no_save=True)
    qtbot.waitUntil(lambda: settled(view), timeout=30_000)
    assert view.scan_id is None and not window.action_export.isEnabled()
