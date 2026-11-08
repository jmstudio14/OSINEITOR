"""Ventana principal: menús, barra de herramientas, barra de estado, tema y geometría."""

from __future__ import annotations

import contextlib
import html
from collections.abc import Sequence
from itertools import pairwise
from pathlib import Path
from typing import Any

from PySide6.QtCore import QByteArray, QEvent, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QGuiApplication,
    QKeySequence,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QStackedWidget,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from osineitor_gui import __version__
from osineitor_gui.api import CliApi
from osineitor_gui.scan_request import ScanRequest
from osineitor_gui.settings import THEMES, GuiSettings
from osineitor_gui.ui import icons
from osineitor_gui.ui.dashboard_view import DashboardView
from osineitor_gui.ui.history_panel import HistoryPanel
from osineitor_gui.ui.legal_dialog import LegalDialog
from osineitor_gui.ui.modules_view import HealthDialog
from osineitor_gui.ui.new_scan_dialog import NewScanDialog
from osineitor_gui.ui.scan_view import ScanView
from osineitor_gui.ui.search_panel import SearchPanel
from osineitor_gui.ui.settings_dialog import SettingsDialog
from osineitor_gui.ui.sidebar import Sidebar, TopBar
from osineitor_gui.ui.theme import apply_theme
from osineitor_gui.ui.widgets import EmptyState, Toast, button
from osineitor_gui.ui.worker import run_in_thread

STOP_WAIT = 5.0  # segundos que se espera a que la CLI cancele antes de matarla
# Filtro del diálogo de exportar → formato de `osineitor export -f`.
EXPORT_FORMATS = {"JSON (*.json)": "json", "Markdown (*.md)": "md", "HTML (*.html)": "html"}
DEFAULT_SIZE = (1280, 800)
NARROW_WIDTH = 1100  # por debajo, la barra lateral se contrae y la superior solo muestra iconos


class MainWindow(QMainWindow):
    def __init__(
        self, settings: GuiSettings, cli: Sequence[str] | None, cli_error: str | None = None
    ) -> None:
        super().__init__()
        self.settings = settings
        self.cli = list(cli) if cli else None
        self.api = CliApi(self.cli)
        self._saved_ids: set[int] = set()  # scans en vivo ya anotados en el historial
        self._health: HealthDialog | None = None
        self._settings_dialog: SettingsDialog | None = None
        self.catalog: list[dict[str, Any]] | None = None  # `modules --json`, para «Nuevo scan»
        self.setWindowTitle("OSINEITOR")
        self._narrow: bool | None = None
        self._resize_to_screen()
        if settings.window_geometry:
            self.restoreGeometry(QByteArray.fromBase64(settings.window_geometry.encode("ascii")))

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.tabs.currentChanged.connect(self._update_state)

        self._build_actions()
        self.history = HistoryPanel(self.api)
        self.history.setEnabled(self.cli is not None)
        self.history.scan_requested.connect(self.open_saved)
        self.history.export_requested.connect(self._export_scan)
        self.history.loaded.connect(self._on_history_loaded)
        self.search_panel = SearchPanel(self.api)
        self.search_panel.setEnabled(self.cli is not None)
        self.search_panel.scan_requested.connect(self.open_saved)
        self.dashboard = DashboardView(self.api, self.action_new)
        self.dashboard.scan_requested.connect(self.open_saved)
        self.scans_empty = EmptyState(
            "radar",
            self.tr("Sin scans abiertos"),
            self.tr("Lanza un scan nuevo o abre uno del historial."),
        )
        scans_cta = button(self.tr("Nuevo scan…"), "primary")
        scans_cta.setEnabled(self.action_new.isEnabled())
        scans_cta.clicked.connect(self.action_new.trigger)
        self.scans_empty.add_action(scans_cta)

        self.stack = QStackedWidget()
        self._pages: dict[str, QWidget] = {
            "dashboard": self.dashboard,
            "scans": self.tabs,
            "history": self.history,
            "search": self.search_panel,
        }
        self._titles = {
            "dashboard": self.tr("Panel"),
            "scans": self.tr("Scans"),
            "history": self.tr("Historial"),
            "search": self.tr("Búsqueda"),
        }
        for page in self._pages.values():
            self.stack.addWidget(page)
        self.stack.addWidget(self.scans_empty)

        self._build_nav_actions()
        self._build_menus()
        toolbar = QToolBar(self.tr("Principal"))
        toolbar.setMovable(False)
        toolbar.setIconSize(icons.ICON_SIZE)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toolbar.addActions(
            [self.action_new, self.action_cancel, self.action_export, self.action_quit]
        )
        toolbar.widgetForAction(self.action_new).setProperty("kind", "primary")
        for action in toolbar.actions():
            toolbar.widgetForAction(action).setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.topbar = TopBar(toolbar)
        self.topbar.search.setEnabled(self.cli is not None)
        self.topbar.search_requested.connect(self.run_search)
        self._build_sidebar()

        main_column = QVBoxLayout()
        main_column.setContentsMargins(0, 0, 0, 0)
        main_column.setSpacing(0)
        main_column.addWidget(self.topbar)
        main_column.addWidget(self.stack, 1)
        central = QWidget()
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self.sidebar)
        row.addLayout(main_column, 1)
        self.setCentralWidget(central)
        # Tabulador en el orden visual: barra lateral, barra superior y contenido.
        tab_chain = [
            *self.sidebar.tab_order(),
            self.topbar.search,
            *(toolbar.widgetForAction(action) for action in toolbar.actions()),
        ]
        for first, second in pairwise(tab_chain):
            QWidget.setTabOrder(first, second)
        self.toast = Toast(central)

        self.progress = QProgressBar()
        self.progress.setMaximumWidth(160)
        self.progress.setTextVisible(False)
        self.progress.setAccessibleName(self.tr("Progreso del scan"))
        self.summary = QLabel()
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.statusBar().addPermanentWidget(self.summary)
        self.statusBar().addPermanentWidget(self.progress)
        if cli:
            self.statusBar().showMessage(f"{self.tr('CLI')}: {' '.join(cli)}")
            self.topbar.set_cli_state(self.tr("Comprobando CLI…"), "info", " ".join(cli))
        else:
            self.statusBar().showMessage(f"{self.tr('CLI no encontrada')}: {cli_error}")
            self.topbar.set_cli_state(self.tr("CLI no encontrada"), "critical")
        self._retint()
        self._apply_width()
        self.show_page("dashboard")
        self.dashboard.setFocus()  # el foco inicial, en el contenido: sin anillo en un botón
        self._update_state()
        if self.cli:
            QTimer.singleShot(0, self.history.reload)
            QTimer.singleShot(0, self.load_catalog)
        else:
            self.dashboard.set_history([], cli_error)

    def _resize_to_screen(self) -> None:
        width, height = DEFAULT_SIZE
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            width, height = min(width, available.width()), min(height, available.height())
        self.resize(width, height)

    def _build_actions(self) -> None:
        self.action_new = QAction(self.tr("&Nuevo scan…"), self)
        self.action_new.setShortcut(QKeySequence("Ctrl+N"))
        self.action_new.setEnabled(self.cli is not None)
        self.action_new.triggered.connect(self._new_scan)

        self.action_cancel = QAction(self.tr("&Cancelar scan"), self)
        self.action_cancel.triggered.connect(self._cancel_current)

        self.action_open_saved = QAction(self.tr("&Abrir scan guardado…"), self)
        self.action_open_saved.setEnabled(self.cli is not None)
        self.action_open_saved.triggered.connect(self._show_history)

        self.action_export = QAction(self.tr("&Exportar scan…"), self)
        self.action_export.setEnabled(False)
        self.action_export.triggered.connect(self._export)

        self.action_quit = QAction(self.tr("&Salir"), self)
        self.action_quit.setShortcut(QKeySequence("Ctrl+Q"))
        self.action_quit.triggered.connect(self.close)

        self.theme_actions: dict[str, QAction] = {}
        group = QActionGroup(self)
        group.setExclusive(True)
        names = {
            "system": self.tr("&Sistema"),
            "light": self.tr("&Claro"),
            "dark": self.tr("&Oscuro"),
        }
        for theme in THEMES:
            action = QAction(names[theme], self, checkable=True)
            action.setChecked(theme == self.settings.theme)
            action.triggered.connect(lambda _checked=False, t=theme: self.set_theme(t))
            group.addAction(action)
            self.theme_actions[theme] = action

        self.action_health = QAction(self.tr("&Salud de los módulos…"), self)
        self.action_health.setEnabled(self.cli is not None)
        self.action_health.triggered.connect(self._show_health)

        self.action_settings = QAction(self.tr("&Ajustes…"), self)
        self.action_settings.setShortcut(QKeySequence("Ctrl+,"))
        self.action_settings.triggered.connect(self._show_settings)

        self.action_legal = QAction(self.tr("&Uso responsable"), self)
        self.action_legal.triggered.connect(self._show_legal)
        self.action_about = QAction(self.tr("&Acerca de"), self)
        self.action_about.triggered.connect(self._show_about)

    def _build_nav_actions(self) -> None:
        self.nav_actions: dict[str, QAction] = {}
        names = {
            "dashboard": self.tr("&Panel"),
            "scans": self.tr("S&cans"),
            "history": self.tr("&Historial"),
            "search": self.tr("&Búsqueda"),
        }
        for number, (page, text) in enumerate(names.items(), start=1):
            action = QAction(text, self)
            action.setShortcut(QKeySequence(f"Ctrl+{number}"))
            action.triggered.connect(lambda _checked=False, name=page: self.show_page(name))
            self.nav_actions[page] = action
        self.action_toggle_sidebar = QAction(self.tr("Contraer o expandir el &menú"), self)
        self.action_toggle_sidebar.setShortcut(QKeySequence("Ctrl+B"))

    def _build_sidebar(self) -> None:
        self.sidebar = Sidebar()
        self.action_toggle_sidebar.triggered.connect(self.sidebar.toggle)
        pages = (
            ("dashboard", "layout-dashboard", self.tr("Panel")),
            ("scans", "radar", self.tr("Scans")),
            ("history", "history", self.tr("Historial")),
            ("search", "search", self.tr("Búsqueda")),
        )
        for number, (page, icon, text) in enumerate(pages, start=1):
            self.sidebar.add_page(page, icon, text, f"Ctrl+{number}")
        self.sidebar.page_selected.connect(self.show_page)
        self.sidebar.add_action(self.action_health, "activity", self.tr("Salud"))
        self.sidebar.add_action(self.action_settings, "settings", self.tr("Ajustes"))
        self.sidebar.add_action(self.action_legal, "scale", self.tr("Uso responsable"), footer=True)
        self.sidebar.add_action(self.action_about, "info", self.tr("Acerca de"), footer=True)

    def show_page(self, name: str) -> None:
        page = self._pages[name]
        if name == "scans" and not self.tabs.count():
            page = self.scans_empty
        self.stack.setCurrentWidget(page)
        self.sidebar.select(name)
        self.topbar.title.setText(self._titles[name])
        if name == "history":
            self.history.table.setFocus()

    def run_search(self, query: str) -> None:
        self.show_page("search")
        self.search_panel.run(query)

    def _on_history_loaded(self) -> None:
        self.dashboard.set_history(self.history.model.rows(), self.history.error)

    def _retint(self) -> None:
        self.action_new.setIcon(icons.icon("plus", "on_accent"))
        self.action_cancel.setIcon(icons.icon("circle-stop"))
        self.action_export.setIcon(icons.icon("download"))
        self.action_quit.setIcon(icons.icon("log-out"))

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.ApplicationPaletteChange:
            self._retint()
        super().changeEvent(event)

    def _apply_width(self) -> None:
        narrow = self.width() < NARROW_WIDTH
        if narrow != self._narrow:
            self._narrow = narrow
            self.sidebar.fit_width(narrow)
            self.topbar.set_compact(narrow)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self.centralWidget() is not None:
            self._apply_width()

    def _notify(self, text: str, tone: str = "safe") -> None:
        self.statusBar().showMessage(text, 10000)
        self.toast.show_message(text, tone)

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu(self.tr("&Archivo"))
        file_menu.addActions(
            [self.action_new, self.action_open_saved, self.action_export, self.action_cancel]
        )
        file_menu.addSeparator()
        file_menu.addAction(self.action_quit)
        view_menu = self.menuBar().addMenu(self.tr("&Ver"))
        view_menu.addActions(list(self.nav_actions.values()))
        view_menu.addAction(self.action_toggle_sidebar)
        view_menu.addSeparator()
        theme_menu = view_menu.addMenu(self.tr("&Tema"))
        theme_menu.addActions(list(self.theme_actions.values()))
        tools_menu = self.menuBar().addMenu(self.tr("&Herramientas"))
        tools_menu.addActions([self.action_health, self.action_settings])
        help_menu = self.menuBar().addMenu(self.tr("A&yuda"))
        help_menu.addActions([self.action_legal, self.action_about])

    # --- scans ------------------------------------------------------------------------------

    def _views(self) -> list[ScanView]:
        return [self.tabs.widget(i) for i in range(self.tabs.count())]

    def _current(self) -> ScanView | None:
        return self.tabs.currentWidget()

    def _new_scan(self) -> None:
        dialog = NewScanDialog(self, self.catalog)
        dialog.accepted.connect(lambda: self.open_scan(dialog.request()))
        dialog.open()

    def load_catalog(self) -> None:
        """Pide la lista de módulos a la CLI; si falla, «Nuevo scan» se abre sin selector."""
        run_in_thread(self.api.modules, self._catalog_loaded, self._catalog_failed, self)

    def _catalog_loaded(self, modules: list[dict[str, Any]]) -> None:
        self.catalog = modules
        self.topbar.set_cli_state(self.tr("CLI operativa"), "safe", " ".join(self.cli or []))
        self.dashboard.set_catalog(modules)

    def _catalog_failed(self, exc: Exception) -> None:
        self.statusBar().showMessage(
            f"{self.tr('No se pudo cargar la lista de módulos')}: {exc}", 15000
        )
        self.topbar.set_cli_state(self.tr("CLI no responde"), "critical")

    def open_scan(self, request: ScanRequest) -> ScanView:
        """Lanza un scan en una pestaña nueva."""
        view = ScanView(request, self.cli, self)
        self._add_tab(view)
        view.start()
        return view

    def _add_tab(self, view: ScanView) -> None:
        view.changed.connect(lambda v=view: self._on_view_changed(v))
        self.tabs.setCurrentIndex(self.tabs.addTab(view, view.title()))
        self.show_page("scans")

    def open_saved(self, scan_id: int) -> None:
        """Abre un scan guardado en una pestaña (o activa la que ya lo muestra)."""
        for index, view in enumerate(self._views()):
            if view.scan_id == scan_id:
                self.tabs.setCurrentIndex(index)
                self.show_page("scans")
                return
        run_in_thread(
            lambda: self.api.show(scan_id),
            self._saved_loaded,
            lambda exc: self._show_error(self.tr("No se pudo abrir el scan"), exc),
            self,
        )

    def _saved_loaded(self, result: dict[str, Any]) -> None:
        if any(view.scan_id == result.get("scan_id") for view in self._views()):
            return  # se abrió mientras tanto (doble clic repetido)
        self._add_tab(ScanView.from_result(result, self))

    def _show_history(self) -> None:
        self.show_page("history")
        self.history.reload()

    def _export(self) -> None:
        view = self._current()
        if view is not None and view.scan_id is not None:
            self._export_scan(view.scan_id)

    def _export_scan(self, scan_id: int) -> None:
        path, chosen = QFileDialog.getSaveFileName(
            self, self.tr("Exportar scan"), f"scan-{scan_id}", ";;".join(EXPORT_FORMATS)
        )
        if not path:
            return
        fmt = EXPORT_FORMATS.get(chosen, "json")
        if not Path(path).suffix:
            path += f".{fmt}"
        run_in_thread(
            lambda: self.api.export(scan_id, fmt, path),
            lambda done: self._notify(f"{self.tr('Exportado')}: {done.get('path', path)}"),
            lambda exc: self._show_error(self.tr("No se pudo exportar el scan"), exc),
            self,
        )

    def _show_error(self, title: str, exc: Exception) -> None:
        # El texto es el stderr de la CLI: Qt lo tomaría por HTML si lleva etiquetas. Escapado y
        # dentro de <qt>, se ve tal cual.
        text = html.escape(str(exc)).replace("\n", "<br>")
        QMessageBox.critical(self, title, f"<qt>{text}</qt>")

    def _on_view_changed(self, view: ScanView) -> None:
        index = self.tabs.indexOf(view)
        if index >= 0:
            self.tabs.setTabText(index, view.title())
        scan_id = view.scan_id
        live_saved = view.request is not None and view.session.finished and scan_id is not None
        if live_saved and scan_id not in self._saved_ids:  # se guardó: aparece en el historial
            self._saved_ids.add(scan_id)
            self.history.reload()
            self._notify(f"{self.tr('Scan guardado')}: #{scan_id}")
        self._update_state()

    def _update_state(self, *_args) -> None:
        # No cambia de página: un scan en marcha refresca esto cada 100 ms y sacaría al usuario
        # de la que esté viendo.
        view = self._current()
        self.action_cancel.setEnabled(view is not None and view.is_running)
        self.action_export.setEnabled(
            view is not None and view.scan_id is not None and not view.is_running
        )
        if view is None:
            self.summary.clear()
            self.progress.hide()
            return
        session = view.session
        self.summary.setText(
            f"{len(session.entities)} {self.tr('entidades')} · "
            f"{session.requests} {self.tr('peticiones')} · {view.status_text()}"
        )
        self.progress.setRange(0, max(session.total, 1))
        self.progress.setValue(session.done)
        self.progress.setVisible(view.is_running or session.total > 0)

    def _cancel_current(self) -> None:
        view = self._current()
        if view is not None:
            view.cancel()

    @staticmethod
    def _stop(view: ScanView) -> None:
        """Cancela de forma ordenada y, si la CLI no sale a tiempo, la mata: no queda huérfana."""
        view.cancel()
        try:
            view.wait(STOP_WAIT)
        except TimeoutError:
            view.kill()
            with contextlib.suppress(TimeoutError):
                view.wait(STOP_WAIT)

    def _confirm_stop(self) -> bool:
        answer = QMessageBox.question(
            self,
            self.tr("Scan en marcha"),
            self.tr("Hay un scan en marcha. ¿Cancelarlo? Se guarda lo obtenido hasta ahora."),
        )
        return answer == QMessageBox.StandardButton.Yes

    def _close_tab(self, index: int) -> None:
        view = self.tabs.widget(index)
        if view.is_running:
            if not self._confirm_stop():
                return
            self._stop(view)
        self.tabs.removeTab(index)
        view.deleteLater()
        if not self.tabs.count():
            self.show_page("dashboard")
        self.dashboard.setFocus()  # el foco inicial, en el contenido: sin anillo en un botón
        self._update_state()

    def set_theme(self, theme: str) -> None:
        apply_theme(theme)
        self.theme_actions[theme].setChecked(True)  # el cambio puede venir de los ajustes
        self.settings.theme = theme
        self.settings.save()

    def _show_settings(self) -> None:
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self.api, self.settings, self)
            self._settings_dialog.theme_changed.connect(self.set_theme)
        self._settings_dialog.reload()
        self._settings_dialog.show()
        self._settings_dialog.raise_()

    def _show_health(self) -> None:
        if self._health is None:
            self._health = HealthDialog(self.api, self)
        self._health.show()
        self._health.raise_()

    def _show_legal(self) -> None:
        LegalDialog(self).open()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            self.tr("Acerca de OSINEITOR"),
            f"OSINEITOR {__version__}\n\n{self.tr('Investigación OSINT sobre fuentes abiertas.')}",
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        running = [view for view in self._views() if view.is_running]
        if running:
            if not self._confirm_stop():
                event.ignore()
                return
            for view in running:
                self._stop(view)
        self.dashboard.stop()
        self.settings.window_geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
        self.settings.save()
        super().closeEvent(event)
