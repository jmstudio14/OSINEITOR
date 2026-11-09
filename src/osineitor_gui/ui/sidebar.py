"""Barra lateral (navegación, contraíble) y barra superior (sección, búsqueda, estado de la CLI)."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from osineitor_gui.ui import icons
from osineitor_gui.ui.widgets import label, set_style

EXPANDED_WIDTH, COLLAPSED_WIDTH = 204, 56
ICON = QSize(18, 18)
ICON_LOGO = 24


class Sidebar(QFrame):
    """Las páginas se excluyen entre sí; Salud, Ajustes y Ayuda solo lanzan su acción."""

    page_selected = Signal(str)
    choice_changed = Signal(str)  # el usuario contrajo o expandió el menú

    def __init__(self, choice: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "sidebar")
        self.collapsed = False
        self.choice = choice  # lo que eligió el usuario: manda sobre la anchura
        self._buttons: list[tuple[QToolButton, str, str]] = []  # (botón, icono, texto)
        self._pages: dict[str, QToolButton] = {}

        self.logo = QLabel()
        self.logo.setAccessibleName("OSINEITOR")
        self.brand = label("OSINEITOR", "brand")
        top = QHBoxLayout()
        top.setContentsMargins(6, 4, 6, 10)
        top.setSpacing(8)
        top.addWidget(self.logo)
        top.addWidget(self.brand, 1)

        self._items = QVBoxLayout()
        self._items.setSpacing(2)
        self._footer = QVBoxLayout()
        self._footer.setSpacing(2)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 10)
        layout.setSpacing(2)
        layout.addLayout(top)
        layout.addLayout(self._items)
        layout.addStretch(1)
        layout.addLayout(self._footer)

        self.toggle_button = self._button("panel-left-close", self.tr("Contraer menú"))
        self.toggle_button.clicked.connect(self._toggle)
        self._footer.addWidget(self.toggle_button)
        self.setFixedWidth(EXPANDED_WIDTH)
        self.retint()

    def _button(self, icon: str, text: str) -> QToolButton:
        button = QToolButton()
        button.setProperty("kind", "nav")
        button.setText(text)
        button.setToolTip(text)
        button.setAccessibleName(text)
        button.setIconSize(ICON)
        button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setSizePolicy(button.sizePolicy().Policy.Expanding, button.sizePolicy().Policy.Fixed)
        self._buttons.append((button, icon, text))
        return button

    def add_page(self, name: str, icon: str, text: str, shortcut: str = "") -> QToolButton:
        button = self._button(icon, text)
        button.setCheckable(True)
        if shortcut:
            button.setToolTip(f"{text} ({shortcut})")
        button.clicked.connect(lambda: self.page_selected.emit(name))
        self._pages[name] = button
        self._items.addWidget(button)
        return button

    def add_action(self, action: QAction, icon: str, text: str, *, footer: bool = False) -> None:
        button = self._button(icon, text)
        button.clicked.connect(action.trigger)
        button.setEnabled(action.isEnabled())
        action.enabledChanged.connect(button.setEnabled)
        if footer:
            self._footer.insertWidget(self._footer.count() - 1, button)
        else:
            self._items.addWidget(button)

    def tab_order(self) -> list[QToolButton]:
        """De arriba abajo, como se ven: el botón de contraer se creó el primero."""
        return [b for b, _icon, _text in self._buttons[1:]] + [self.toggle_button]

    def select(self, name: str) -> None:
        for page, button in self._pages.items():
            button.setChecked(page == name)

    def selected(self) -> str | None:
        return next((name for name, b in self._pages.items() if b.isChecked()), None)

    def _toggle(self) -> None:
        self.set_collapsed(not self.collapsed)
        self.choice = "collapsed" if self.collapsed else "expanded"
        self.choice_changed.emit(self.choice)

    def toggle(self) -> None:
        self._toggle()

    def fit_width(self, narrow: bool) -> None:
        """La ventana cruzó el umbral de anchura; lo que eligió el usuario manda."""
        self.set_collapsed(self.choice == "collapsed" if self.choice else narrow)

    def set_collapsed(self, collapsed: bool) -> None:
        self.collapsed = collapsed
        self.setFixedWidth(COLLAPSED_WIDTH if collapsed else EXPANDED_WIDTH)
        self.brand.setVisible(not collapsed)
        style = (
            Qt.ToolButtonStyle.ToolButtonIconOnly
            if collapsed
            else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        for button, _icon, _text in self._buttons:
            button.setToolButtonStyle(style)
        text = self.tr("Expandir menú") if collapsed else self.tr("Contraer menú")
        self.toggle_button.setText(text)
        self.toggle_button.setToolTip(text)
        self.toggle_button.setAccessibleName(text)
        self.retint()

    def retint(self) -> None:
        self.logo.setPixmap(icons.icon("shield-check", "accent").pixmap(ICON_LOGO, ICON_LOGO))
        for button, icon, _text in self._buttons:
            if button is self.toggle_button:
                icon = "panel-left-open" if self.collapsed else "panel-left-close"
            button.setIcon(icons.icon(icon))

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.ApplicationPaletteChange:
            self.retint()
        super().changeEvent(event)


class TopBar(QFrame):
    """Nombre de la sección, búsqueda global, chip real de la CLI y las acciones principales."""

    search_requested = Signal(str)

    def __init__(self, toolbar: QToolBar, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "topbar")
        self.title = label("", "pageTitle")
        self.search = QLineEdit()
        self.search.setPlaceholderText(self.tr("Buscar en todos los scans (Ctrl+K)"))
        self.search.setAccessibleName(self.tr("Buscar en todos los scans"))
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(380)
        self.search.setMinimumWidth(140)
        self.search.returnPressed.connect(lambda: self.search_requested.emit(self.search.text()))
        QShortcut(QKeySequence("Ctrl+K"), self, self._focus_search)
        self.chip = label("", "chip")
        self.toolbar = toolbar
        toolbar.setParent(self)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 12, 8)
        layout.setSpacing(12)
        layout.addWidget(self.title)
        layout.addStretch(1)
        layout.addWidget(self.search, 2)
        layout.addWidget(self.chip)
        layout.addWidget(toolbar)

    def _focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def set_cli_state(self, text: str, tone: str, detail: str = "") -> None:
        self.chip.setText(text)
        self.chip.setToolTip(detail)
        self.chip.setAccessibleName(text)
        set_style(self.chip, tone=tone)

    def set_compact(self, compact: bool) -> None:
        self.toolbar.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonIconOnly
            if compact
            else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
