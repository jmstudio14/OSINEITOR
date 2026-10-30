"""Eventos del contrato CLI↔GUI: una línea JSON por evento (NDJSON), versión 1.

Los cambios futuros son solo aditivos: campos nuevos o tipos nuevos de evento. Un cliente debe
ignorar lo que no conozca. Ver docs/CLI_CONTRACT.md y docs/cli-contract.schema.json.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from typing import Any

VERSION = 1

# Códigos de salida del proceso.
EXIT_OK = 0
EXIT_INTERNAL = 1  # excepción no prevista (el código que Python da por defecto)
EXIT_USAGE = 2  # entrada inválida (el que usa click)
EXIT_MODULE_ERRORS = 3  # terminó, pero algún módulo falló
EXIT_TRUNCATED = 4  # se agotó el presupuesto: el resultado es incompleto
EXIT_TAMPERED = 5  # `verify`: alguna evidencia no coincide con su huella
EXIT_CANCELLED = 130  # cancelado por el usuario (convención de Ctrl+C)


def event(type_: str, **fields: Any) -> dict[str, Any]:
    return {"v": VERSION, "ts": datetime.now(UTC).isoformat(), "type": type_, **fields}


class NdjsonSink:
    """Escribe eventos en stdout, uno por línea y con `flush`, para que el lector los vea ya.

    `ensure_ascii` hace que la salida sea ASCII puro: no depende de la codificación de la tubería
    (en Windows, cp1252 por defecto) ni se rompe con caracteres raros de terceros.
    """

    def emit(self, ev: dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(ev, ensure_ascii=True, default=str) + "\n")
        sys.stdout.flush()
