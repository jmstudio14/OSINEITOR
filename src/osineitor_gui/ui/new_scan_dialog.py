"""Diálogo «Nuevo scan»: objetivo, tipo, profundidad y presupuesto. Solo módulos pasivos."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from osineitor_gui.scan_request import KINDS, InvalidRequest, ScanRequest, detect_kind

DEFAULT = -1  # valor especial de los cuadros numéricos: «por defecto» = no pasar la opción


class NewScanDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Nuevo scan"))
        self._request: ScanRequest | None = None

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
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        for box in (self.no_save, self.no_cache, self.refresh):
            layout.addWidget(box)
        layout.addWidget(QLabel(self.tr("Solo se usan módulos pasivos.")))
        layout.addWidget(self.error)
        layout.addWidget(buttons)

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
            max_entities=self._optional(self.max_entities),
            max_requests=self._optional(self.max_requests),
            max_time=self._optional(self.max_time),
            no_cache=self.no_cache.isChecked(),
            refresh=self.refresh.isChecked(),
            no_save=self.no_save.isChecked(),
        )
        try:
            request.validate()
        except InvalidRequest as exc:
            self.error.setText(str(exc))
            self.error.show()
            return
        self._request = request
        super().accept()
