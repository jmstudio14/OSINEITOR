"""Datasets de terceros que `osineitor update-data` descarga al directorio de datos del usuario.

Cada instalación queda anotada en `manifest.json` con su versión, SHA-256 y licencia. Solo se
instalan los de licencia compatible con la del proyecto (MIT): un dataset con otra licencia (GPL,
CC-BY-SA, propietaria, desconocida) se rechaza antes de descargarlo. Quien lee un dataset usa
`installed_path`, que devuelve `None` si el fichero no coincide con su hash registrado.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from osineitor.config import data_dir
from osineitor.http import HttpClient

# Licencias SPDX que se pueden redistribuir con un paquete MIT.
COMPATIBLE_LICENSES = frozenset(
    {
        "MIT",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "Apache-2.0",
        "ISC",
        "CC0-1.0",
        "Unlicense",
        "CC-BY-4.0",
    }
)
MAX_BYTES = 50 * 1024 * 1024
MANIFEST = "manifest.json"


class DatasetError(Exception):
    """La descarga no se puede instalar."""


def _sherlock(raw: bytes) -> bytes:
    """Valida las firmas de Sherlock y quita la clave `$schema`, que no es un sitio."""
    try:
        sites = json.loads(raw)
    except ValueError as exc:
        raise DatasetError("no es JSON válido") from exc
    if not isinstance(sites, dict):
        raise DatasetError("se esperaba un mapa de sitios")
    sites.pop("$schema", None)
    if not sites or not all(
        isinstance(s, dict) and isinstance(s.get("url"), str) for s in sites.values()
    ):
        raise DatasetError("hay sitios sin `url`")
    return json.dumps(sites, indent=1, ensure_ascii=False).encode()


def _as_is(raw: bytes) -> bytes:
    return raw


@dataclass(frozen=True)
class Dataset:
    name: str
    description: str
    url: str
    license: str  # identificador SPDX
    filename: str
    prepare: Callable[[bytes], bytes] = _as_is  # valida y adapta la descarga; lanza DatasetError


CATALOG: tuple[Dataset, ...] = (
    Dataset(
        name="sherlock-sites",
        description="Firmas de sitios para username_sites (Sherlock)",
        url=(
            "https://raw.githubusercontent.com/sherlock-project/sherlock/master/"
            "sherlock_project/resources/data.json"
        ),
        license="MIT",
        filename="sites.json",
        prepare=_sherlock,
    ),
)


@dataclass
class Result:
    name: str
    status: str  # "actualizado" | "sin cambios" | "rechazado" | "error"
    detail: str = ""
    license: str = ""
    version: str = ""
    sha256: str = ""


def datasets_dir() -> Path:
    return data_dir() / "datasets"


def manifest() -> dict[str, dict]:
    try:
        return json.loads((datasets_dir() / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def installed_path(name: str) -> Path | None:
    """Fichero del dataset instalado, o `None` si no está o no coincide con su hash registrado."""
    entry = manifest().get(name)
    if not isinstance(entry, dict) or not isinstance(entry.get("filename"), str):
        return None
    path = datasets_dir() / entry["filename"]
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None
    return path if digest == entry.get("sha256") else None


def _write(path: Path, data: bytes) -> None:
    """Escritura atómica: o queda el fichero entero nuevo o el anterior."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


async def _install(http: HttpClient, dataset: Dataset, entries: dict[str, dict]) -> Result:
    if dataset.license not in COMPATIBLE_LICENSES:
        return Result(
            dataset.name,
            "rechazado",
            f"licencia {dataset.license} incompatible con MIT: no se instala",
            dataset.license,
        )
    response = await http.get(dataset.url)
    if response.status_code != 200:
        raise DatasetError(f"{dataset.url} respondió {response.status_code}")
    if len(response.content) > MAX_BYTES:
        raise DatasetError(f"la descarga supera {MAX_BYTES // 2**20} MiB")
    data = dataset.prepare(response.content)
    sha256 = hashlib.sha256(data).hexdigest()
    old = entries.get(dataset.name, {})
    if old.get("sha256") == sha256 and installed_path(dataset.name):
        return Result(
            dataset.name, "sin cambios", "", dataset.license, old.get("version", ""), sha256
        )
    now = datetime.now(UTC)
    headers = response.headers
    version = (
        headers.get("last-modified") or headers.get("etag", "").strip('"') or now.date().isoformat()
    )
    _write(datasets_dir() / dataset.filename, data)
    entries[dataset.name] = {
        "version": version,
        "sha256": sha256,
        "license": dataset.license,
        "url": dataset.url,
        "filename": dataset.filename,
        "size": len(data),
        "updated_at": now.isoformat(),
    }
    return Result(dataset.name, "actualizado", "", dataset.license, version, sha256)


async def update(
    http: HttpClient,
    names: Iterable[str] | None = None,
    catalog: tuple[Dataset, ...] | None = None,
) -> list[Result]:
    """Descarga los datasets pedidos (todos si no se indica ninguno) y anota cada instalación."""
    wanted = set(names or ())
    entries = manifest()
    results = []
    for dataset in catalog or CATALOG:
        if wanted and dataset.name not in wanted:
            continue
        try:
            results.append(await _install(http, dataset, entries))
        except Exception as exc:  # un dataset roto no impide actualizar los demás
            results.append(Result(dataset.name, "error", f"{type(exc).__name__}: {exc}"))
    if any(r.status == "actualizado" for r in results):
        _write(datasets_dir() / MANIFEST, json.dumps(entries, indent=1).encode())
    return results
