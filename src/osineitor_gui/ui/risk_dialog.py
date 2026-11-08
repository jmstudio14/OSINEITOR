"""Confirmaciones explícitas de las opciones de riesgo: módulos activos y redes privadas.

La vista solo pregunta; quién exige la confirmación es `ScanRequest`. El botón por defecto y el de
Escape son «Cancelar»: Enter no confirma nunca.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QMessageBox, QWidget

from osineitor_gui import legal


def _tr(text: str) -> str:
    return QCoreApplication.translate("risk_dialog", text)


def _risk_box(parent: QWidget | None, title: str, text: str) -> QMessageBox:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(text)
    box.accept_button = box.addButton(
        _tr("Entiendo el riesgo y continúo"), QMessageBox.ButtonRole.AcceptRole
    )
    box.cancel_button = box.addButton(_tr("Cancelar"), QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(box.cancel_button)
    box.setEscapeButton(box.cancel_button)
    return box


def active_box(parent: QWidget | None = None) -> QMessageBox:
    return _risk_box(parent, _tr("Módulos activos"), legal.ACTIVE_WARNING)


def private_box(parent: QWidget | None = None) -> QMessageBox:
    return _risk_box(parent, _tr("Redes privadas"), legal.PRIVATE_WARNING)


def _confirmed(box: QMessageBox) -> bool:
    box.exec()
    return box.clickedButton() is box.accept_button


def confirm_active(parent: QWidget | None = None) -> bool:
    return _confirmed(active_box(parent))


def confirm_private(parent: QWidget | None = None) -> bool:
    return _confirmed(private_box(parent))
