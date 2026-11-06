"""Diálogo «Nuevo scan»: objetivo, tipo, módulos, presupuesto, opciones de riesgo y propósito.

Las opciones de riesgo (módulos activos, redes privadas) solo se marcan tras una confirmación
explícita (`risk_dialog`); quien las exige de verdad es `ScanRequest`.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from osineitor_gui.scan_request import KINDS, InvalidRequest, ScanRequest, detect_kind
from osineitor_gui.ui import risk_dialog

DEFAULT = -1  # valor especial de los cuadros numéricos: «por defecto» = no pasar la opción


class NewScanDialog(QDialog):
    def __init__(
        self, parent: QWidget | None = None, modules: list[dict[str, Any]] | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Nuevo scan"))
        self._request: ScanRequest | None = None
        self._active_confirmed = False
        self._private_confirmed = False
        self._modules = list(modules or [])

        self.target = QLineEdit()
        self.target.setPlaceholderText(self.tr("example.com, 8.8.8.8, alguien@example.com…"))
        self.target.textChanged.connect(self._update_detected)
        self.detected = QLabel()

        kind_names = {
            "auto": self.tr("Automático"),
            "domain": self.tr("Dominio"),
            "ip": "IP",
            "email": "Email",
            "username": "Username",
        }
        self.kind = QComboBox()
        for kind in KINDS:
            self.kind.addItem(kind_names[kind], kind)

        self.depth = QSpinBox()
        self.depth.setRange(0, 4)
        self.depth.setSpecialValueText(self.tr("Automática"))

        self.max_entities = self._budget_spin(QSpinBox())
        self.max_requests = self._budget_spin(QSpinBox())
        self.max_time = self._budget_spin(QDoubleSpinBox())
        self.max_time.setDecimals(1)
        self.max_time.setSuffix(" s")

        self.purpose = QLineEdit()
        self.purpose.setPlaceholderText(self.tr("Para qué haces este scan (opcional)"))
        purpose_hint = QLabel(
            self.tr("Los scans de email y username lo exigen si tu configuración lo pide.")
        )
        purpose_hint.setWordWrap(True)

        self.module_list = QListWidget()
        self.module_list.setMaximumHeight(140)
        self.modules_note = QLabel()
        self.modules_note.setWordWrap(True)
        self._fill_modules()

        self.active_box = QCheckBox(self.tr("Incluir módulos activos (contactan con el objetivo)"))
        self.active_box.toggled.connect(self._on_active)
        self.private_box = QCheckBox(self.tr("Permitir redes privadas"))
        self.private_box.toggled.connect(self._on_private)
        self.risk_note = QLabel()
        self.risk_note.setWordWrap(True)

        self.no_save = QCheckBox(self.tr("No guardar el scan en el historial"))
        self.no_cache = QCheckBox(self.tr("No usar la caché"))
        self.refresh = QCheckBox(self.tr("Refrescar la caché"))

        self.error = QLabel()
        self.error.setStyleSheet("color: #d93025;")
        self.error.setWordWrap(True)
        self.error.hide()

        form = QFormLayout()
        form.addRow(self.tr("Objetivo"), self.target)
        form.addRow("", self.detected)
        form.addRow(self.tr("Tipo"), self.kind)
        form.addRow(self.tr("Profundidad"), self.depth)
        form.addRow(self.tr("Máx. entidades"), self.max_entities)
        form.addRow(self.tr("Máx. peticiones"), self.max_requests)
        form.addRow(self.tr("Máx. tiempo"), self.max_time)
        form.addRow(self.tr("Propósito"), self.purpose)
        form.addRow("", purpose_hint)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel(self.tr("Módulos (sin marcar, los de siempre)")))
        layout.addWidget(self.module_list)
        layout.addWidget(self.modules_note)
        for box in (self.active_box, self.private_box, self.no_save, self.no_cache, self.refresh):
            layout.addWidget(box)
        layout.addWidget(self.risk_note)
        layout.addWidget(self.error)
        layout.addWidget(buttons)
        self._update_risk_state()

    # --- módulos ----------------------------------------------------------------------------

    def _fill_modules(self) -> None:
        if not self._modules:
            self.module_list.hide()
            self.modules_note.setText(
                self.tr("No se pudo cargar la lista de módulos: se usarán los de siempre.")
            )
            return
        self.modules_note.hide()
        for module in self._modules:
            label = f"{module['name']} — {module.get('description', '')}"
            if not module.get("passive", True):
                label += f" [{self.tr('activo')}]"
            entry = QListWidgetItem(label)
            entry.setData(Qt.ItemDataRole.UserRole, module["name"])
            entry.setData(Qt.ItemDataRole.UserRole + 1, not module.get("passive", True))
            entry.setCheckState(Qt.CheckState.Unchecked)
            key = module.get("requires_key")
            if key and not module.get("key_configured"):
                # Sin su API key el módulo no puede hacer nada: visible, pero no seleccionable.
                entry.setFlags(Qt.ItemFlag.NoItemFlags)
                entry.setToolTip(f"{self.tr('Necesita la API key')} «{key}»")
                entry.setData(Qt.ItemDataRole.UserRole + 2, True)
            self.module_list.addItem(entry)

    def _set_module_enabled(self, entry: QListWidgetItem, enabled: bool) -> None:
        if entry.data(Qt.ItemDataRole.UserRole + 2):  # sin API key: nunca seleccionable
            return
        flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable
        entry.setFlags(flags | Qt.ItemFlag.ItemIsEnabled if enabled else Qt.ItemFlag.NoItemFlags)
        if not enabled:
            entry.setCheckState(Qt.CheckState.Unchecked)

    def _update_risk_state(self) -> None:
        for i in range(self.module_list.count()):
            entry = self.module_list.item(i)
            is_active_module = entry.data(Qt.ItemDataRole.UserRole + 1)
            self._set_module_enabled(entry, self._active_confirmed or not is_active_module)
        self.risk_note.setText(
            self.tr("Se incluirán módulos activos: envían tráfico al objetivo.")
            if self._active_confirmed
            else self.tr("Solo se usan módulos pasivos.")
        )

    def _selected_modules(self) -> tuple[str, ...]:
        return tuple(
            entry.data(Qt.ItemDataRole.UserRole)
            for entry in (self.module_list.item(i) for i in range(self.module_list.count()))
            if entry.checkState() == Qt.CheckState.Checked
        )

    # --- opciones de riesgo -----------------------------------------------------------------

    def _on_active(self, checked: bool) -> None:
        self._active_confirmed = checked and risk_dialog.confirm_active(self)
        if checked and not self._active_confirmed:
            self._uncheck(self.active_box)
        self._update_risk_state()

    def _on_private(self, checked: bool) -> None:
        self._private_confirmed = checked and risk_dialog.confirm_private(self)
        if checked and not self._private_confirmed:
            self._uncheck(self.private_box)

    @staticmethod
    def _uncheck(box: QCheckBox) -> None:
        box.blockSignals(True)  # sin reentrar en `toggled`
        box.setChecked(False)
        box.blockSignals(False)

    # --- resto ------------------------------------------------------------------------------

    def _budget_spin(self, spin):
        spin.setRange(DEFAULT, 10**9)
        spin.setValue(DEFAULT)
        spin.setSpecialValueText(self.tr("Por defecto"))
        spin.setToolTip(self.tr("0 = sin límite"))
        return spin

    def _update_detected(self, text: str) -> None:
        kind = detect_kind(text) if text.strip() else ""
        self.detected.setText(f"{self.tr('Tipo detectado')}: {kind}" if kind else "")

    @staticmethod
    def _optional(spin) -> int | float | None:
        return None if spin.value() == DEFAULT else spin.value()

    def request(self) -> ScanRequest | None:
        """El scan pedido; `None` si el diálogo no se aceptó."""
        return self._request

    def accept(self) -> None:
        request = ScanRequest(
            target=self.target.text(),
            kind=self.kind.currentData(),
            depth=self.depth.value() or None,
            modules=self._selected_modules(),
            active=self._active_confirmed,
            confirm_active=self._active_confirmed,
            allow_private=self._private_confirmed,
            confirm_private=self._private_confirmed,
            max_entities=self._optional(self.max_entities),
            max_requests=self._optional(self.max_requests),
            max_time=self._optional(self.max_time),
            no_cache=self.no_cache.isChecked(),
            refresh=self.refresh.isChecked(),
            no_save=self.no_save.isChecked(),
            purpose=self.purpose.text() or None,
        )
        try:
            request.validate()
        except InvalidRequest as exc:
            self.error.setText(str(exc))
            self.error.show()
            return
        self._request = request
        super().accept()
