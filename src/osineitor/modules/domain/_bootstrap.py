"""Bootstrap RDAP de IANA: qué TLD tienen servidor RDAP."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from osineitor.config import data_dir
from osineitor.http import HttpClient

IANA_URL = "https://data.iana.org/rdap/dns.json"
CACHE_TTL = 7 * 24 * 3600  # el bootstrap cambia poco


def parse(data: dict[str, Any]) -> frozenset[str]:
    """TLD (minúsculas, sin punto) que tienen servidor RDAP."""
    return frozenset(tld.lower() for tlds, _urls in data.get("services", []) for tld in tlds)


def cache_path() -> Path:
    return data_dir() / "rdap-bootstrap.json"


def _read(path: Path, *, max_age: float | None) -> frozenset[str] | None:
    try:
        if max_age is not None and time.time() - path.stat().st_mtime > max_age:
            return None
        return parse(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


async def rdap_tlds(http: HttpClient) -> frozenset[str] | None:
    """TLD con RDAP, desde la caché local o descargando el bootstrap de IANA.

    Devuelve `None` si no se puede saber (sin red y sin caché): quien llama debe entonces
    intentar la consulta igualmente en vez de descartar el dominio.
    """
    path = cache_path()
    if (cached := _read(path, max_age=CACHE_TTL)) is not None:
        return cached
    try:
        response = await http.get(IANA_URL)
        if response.status_code == 200:
            data = response.json()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data), encoding="utf-8")
            return parse(data)
    except (httpx.HTTPError, ValueError):
        pass
    return _read(path, max_age=None)  # caché caducada antes que nada
