"""Carga las fixtures grabadas con `scripts/record_fixtures.py` (respuestas reales anonimizadas)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import respx

from tests.conftest import FakeResolver

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load(module: str, case: str = "real") -> dict[str, Any]:
    return json.loads((FIXTURES / module / f"{case}.json").read_text(encoding="utf-8"))


def serve(fixture: dict[str, Any]) -> None:
    """Registra en `respx` cada respuesta grabada; debe llamarse dentro de un `@respx.mock`."""
    for call in fixture["http"]:
        respx.route(method=call["method"], url=call["url"]).mock(
            return_value=httpx.Response(
                call["status"], headers=call["headers"], content=call["body"].encode()
            )
        )


def resolver(fixture: dict[str, Any]) -> FakeResolver:
    """Resolvedor en memoria con las respuestas DNS grabadas."""
    return FakeResolver({(c["name"], c["type"]): c["values"] for c in fixture["dns"]})
