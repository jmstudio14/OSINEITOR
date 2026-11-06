"""Diálogo con el texto de uso responsable.

Con `require_acceptance` es la puerta del primer arranque: «Acepto» o «Salir» (por defecto).
Cerrar la ventana o pulsar Escape cuenta como rechazo.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QPlainTextEdit, QVBoxLayout, QWidget

from osineitor_gui import legal


class LegalDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, *, require_acceptance: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle(legal.LEGAL_TITLE)
        self.resize(520, 300)
        self.text = QPlainTextEdit(legal.LEGAL_TEXT)
        self.text.setReadOnly(True)
        if require_acceptance:
            buttons = QDialogButtonBox()
            self.accept_button = buttons.addButton(
                self.tr("Acepto"), QDialogButtonBox.ButtonRole.AcceptRole
            )
            self.exit_button = buttons.addButton(
                self.tr("Salir"), QDialogButtonBox.ButtonRole.RejectRole
            )
            self.accept_button.setAutoDefault(
                False
            )  # si no, el cuadro lo hace el botón por defecto
            self.exit_button.setDefault(True)  # Enter no acepta
            buttons.accepted.connect(self.accept)
        else:
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.text)
        layout.addWidget(buttons)
