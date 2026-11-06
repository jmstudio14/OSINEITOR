"""Ventana principal: menús, barra de herramientas, barra de estado, tema y geometría."""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QStackedWidget,
    QTabWidget,
)

from osineitor_gui import __version__
from osineitor_gui.api import CliApi
from osineitor_gui.scan_request import ScanRequest
from osineitor_gui.settings import THEMES, GuiSettings
from osineitor_gui.ui.history_panel import HistoryPanel
from osineitor_gui.ui.legal_dialog import LegalDialog
from osineitor_gui.ui.modules_view import HealthDialog
from osineitor_gui.ui.new_scan_dialog import NewScanDialog
from osineitor_gui.ui.scan_view import ScanView
from osineitor_gui.ui.settings_dialog import SettingsDialog
from osineitor_gui.ui.theme import apply_theme
from osineitor_gui.ui.worker import run_in_thread

STOP_WAIT = 5.0  # segundos que se espera a que la CLI cancele antes de matarla
# Filtro del diálogo de exportar → formato de `osineitor export -f`.
EXPORT_FORMATS = {"JSON (*.json)": "json", "Markdown (*.md)": "md", "HTML (*.html)": "html"}


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
        self.resize(1000, 650)
        if settings.window_geometry:
            self.restoreGeometry(QByteArray.fromBase64(settings.window_geometry.encode("ascii")))

        welcome = QLabel(self.tr("Sin scans abiertos"))
        welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.tabs.currentChanged.connect(self._update_state)
        self.stack = QStackedWidget()
        self.stack.addWidget(welcome)
        self.stack.addWidget(self.tabs)
        self.setCentralWidget(self.stack)

        self._build_actions()
        self._build_history_dock()
        self._build_menus()
        toolbar = self.addToolBar(self.tr("Principal"))
        toolbar.setMovable(False)
        toolbar.addActions(
            [self.action_new, self.action_cancel, self.action_export, self.action_quit]
        )

        self.progress = QProgressBar()
        self.progress.setMaximumWidth(160)
        self.summary = QLabel()
        self.statusBar().addPermanentWidget(self.summary)
        self.statusBar().addPermanentWidget(self.progress)
        if cli:
            self.statusBar().showMessage(f"{self.tr('CLI')}: {' '.join(cli)}")
        else:
            self.statusBar().showMessage(f"{self.tr('CLI no encontrada')}: {cli_error}")
        self._update_state()
        if self.cli:
            QTimer.singleShot(0, self.history.reload)
            QTimer.singleShot(0, self.load_catalog)

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

    def _build_history_dock(self) -> None:
        self.history = HistoryPanel(self.api)
        self.history.setEnabled(self.cli is not None)
        self.history.scan_requested.connect(self.open_saved)
        self.history_dock = QDockWidget(self.tr("Historial"), self)
        self.history_dock.setWidget(self.history)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.history_dock)

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu(self.tr("&Archivo"))
        file_menu.addActions(
            [self.action_new, self.action_open_saved, self.action_export, self.action_cancel]
        )
        file_menu.addSeparator()
        file_menu.addAction(self.action_quit)
        view_menu = self.menuBar().addMenu(self.tr("&Ver"))
        view_menu.addAction(self.history_dock.toggleViewAction())
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

    def _catalog_failed(self, exc: Exception) -> None:
        self.statusBar().showMessage(
            f"{self.tr('No se pudo cargar la lista de módulos')}: {exc}", 15000
        )

    def open_scan(self, request: ScanRequest) -> ScanView:
        """Lanza un scan en una pestaña nueva."""
        view = ScanView(request, self.cli, self)
        self._add_tab(view)
        view.start()
        return view

    def _add_tab(self, view: ScanView) -> None:
        view.changed.connect(lambda v=view: self._on_view_changed(v))
        self.tabs.setCurrentIndex(self.tabs.addTab(view, view.title()))

    def open_saved(self, scan_id: int) -> None:
        """Abre un scan guardado en una pestaña (o activa la que ya lo muestra)."""
        for index, view in enumerate(self._views()):
            if view.scan_id == scan_id:
                self.tabs.setCurrentIndex(index)
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
        self.history_dock.show()
        self.history_dock.raise_()
        self.history.reload()
        self.history.table.setFocus()

    def _export(self) -> None:
        view = self._current()
        if view is None or view.scan_id is None:
            return
        scan_id = view.scan_id
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
            lambda done: self.statusBar().showMessage(
                f"{self.tr('Exportado')}: {done.get('path', path)}", 10000
            ),
            lambda exc: self._show_error(self.tr("No se pudo exportar el scan"), exc),
            self,
        )

    def _show_error(self, title: str, exc: Exception) -> None:
        QMessageBox.critical(self, title, str(exc))

    def _on_view_changed(self, view: ScanView) -> None:
        index = self.tabs.indexOf(view)
        if index >= 0:
            self.tabs.setTabText(index, view.title())
        scan_id = view.scan_id
        live_saved = view.request is not None and view.session.finished and scan_id is not None
        if live_saved and scan_id not in self._saved_ids:  # se guardó: aparece en el historial
            self._saved_ids.add(scan_id)
            self.history.reload()
        self._update_state()

    def _update_state(self, *_args) -> None:
        view = self._current()
        self.stack.setCurrentIndex(1 if self.tabs.count() else 0)
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
        self.settings.window_geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
        self.settings.save()
        super().closeEvent(event)
