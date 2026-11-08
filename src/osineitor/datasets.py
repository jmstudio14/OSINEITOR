"""Datasets de terceros que `osineitor update-data` descarga al directorio de datos del usuario.

Cada instalación queda anotada en `manifest.json` con su versión, SHA-256 y licencia. Solo se
instalan los de licencia compatible con la del proyecto (MIT): un dataset con otra licencia (GPL,
CC-BY-SA, propietaria, desconocida) se rechaza antes de descargarlo. La única excepción es
`public-feed`: feeds públicos de hechos (rangos de IP) sin licencia declarada, que el usuario
descarga y que no se redistribuyen en el paquete. Quien lee un dataset usa `installed_path`, que
devuelve `None` si el fichero no coincide con su hash registrado.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from osineitor import logs
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
        # No es un SPDX: feed público de hechos sin licencia declarada. Solo para entradas del
        # catálogo revisadas una a una.
        "public-feed",
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


def _cidrs(items: Iterable[object]) -> bytes:
    """Redes normalizadas, sin repetir y en orden: la misma descarga da siempre los mismos bytes."""
    try:
        networks = {str(ipaddress.ip_network(str(item), strict=False)) for item in items}
    except ValueError as exc:
        raise DatasetError(f"hay un rango que no es una red: {exc}") from exc
    if not networks:
        raise DatasetError("no trae ningún rango")
    return json.dumps(sorted(networks)).encode()


def _json_feed(raw: bytes) -> dict:
    try:
        feed = json.loads(raw)
    except ValueError as exc:
        raise DatasetError("no es JSON válido") from exc
    if not isinstance(feed, dict):
        raise DatasetError("se esperaba un objeto JSON")
    return feed


def _entries(feed: dict, key: str) -> list[dict]:
    items = feed.get(key)
    if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
        raise DatasetError(f"falta la lista `{key}`")
    return items


def _aws(raw: bytes) -> bytes:
    feed = _json_feed(raw)
    return _cidrs(
        [i.get("ip_prefix") for i in _entries(feed, "prefixes")]
        + [i.get("ipv6_prefix") for i in _entries(feed, "ipv6_prefixes")]
    )


def _gcp(raw: bytes) -> bytes:
    prefixes = _entries(_json_feed(raw), "prefixes")
    return _cidrs(i.get("ipv4Prefix") or i.get("ipv6Prefix") for i in prefixes)


def _cloudflare(raw: bytes) -> bytes:
    return _cidrs(raw.decode(errors="replace").split())


def _azure(raw: bytes) -> bytes:
    """Rangos de la etiqueta `AzureCloud`, que agrupa todas las direcciones públicas de Azure."""
    values = _entries(_json_feed(raw), "values")
    cloud = next((v for v in values if v.get("name") == "AzureCloud"), None)
    prefixes = (cloud or {}).get("properties", {}).get("addressPrefixes")
    if not isinstance(prefixes, list):
        raise DatasetError("falta la etiqueta `AzureCloud` con sus `addressPrefixes`")
    return _cidrs(prefixes)


AZURE_PAGE = "https://www.microsoft.com/en-us/download/details.aspx?id=56519"
AZURE_LINK = re.compile(
    r"https://download\.microsoft\.com/download/[^\"'\s<>]+/ServiceTags_Public_(\d{8})\.json"
)
# Ruta de descarga que Microsoft mantiene desde hace años: plan B si la página cambia.
AZURE_BASE = "https://download.microsoft.com/download/7/1/d/71d86715-5596-4529-9b13-da13a5de5b63/"
AZURE_GUESS_DAYS = 14
AZURE_STALE_AFTER = timedelta(days=14)


def _today() -> date:
    return datetime.now(UTC).date()


def _azure_installed_url() -> str:
    url = manifest().get("azure-ip-ranges", {}).get("url")
    return url if isinstance(url, str) and AZURE_LINK.fullmatch(url) else ""


async def _azure_guess(http: HttpClient) -> str:
    """Prueba la ruta conocida con las fechas recientes, de la más nueva a la más antigua: los
    ficheros viejos siguen publicados, así que el primero que exista es el vigente."""
    installed = _azure_installed_url()
    base = installed.rsplit("/", 1)[0] + "/" if installed else AZURE_BASE
    for days in range(AZURE_GUESS_DAYS):
        url = f"{base}ServiceTags_Public_{_today() - timedelta(days=days):%Y%m%d}.json"
        if (await http.request("HEAD", url)).status_code == 200:
            return url
    raise DatasetError(
        f"la página de Microsoft no trae el enlace y no hay fichero en los últimos "
        f"{AZURE_GUESS_DAYS} días"
    )


async def _azure_url(http: HttpClient) -> str:
    """Microsoft publica cada semana un fichero con otra URL: se lee de su página de descarga.
    Si la página no lo trae, se busca en la ruta conocida (`_azure_guess`). Los errores de red
    se propagan: sin red el plan B tampoco llegaría."""
    response = await http.get(AZURE_PAGE)
    links = {}
    if response.status_code == 200:
        links = {m.group(0): m.group(1) for m in AZURE_LINK.finditer(response.text)}
    if links:
        return max(links, key=links.__getitem__)  # el de fecha más reciente
    logs.get("datasets").warning(
        "la página de Microsoft (%s) no trae el enlace (HTTP %s); se usa la ruta conocida",
        AZURE_PAGE,
        response.status_code,
    )
    return await _azure_guess(http)


def azure_published() -> date | None:
    """Fecha del fichero de Azure instalado (va en su nombre), o `None` si no hay."""
    if not installed_path("azure-ip-ranges") or not (url := _azure_installed_url()):
        return None
    return datetime.strptime(AZURE_LINK.fullmatch(url).group(1), "%Y%m%d").date()


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
    sha256: str = ""  # hash de la descarga tal cual llega; vacío = sin fijar (URL mutable)
    # Si la URL de descarga cambia, la averigua; con la misma URL que la instalada no se descarga.
    discover: Callable[[HttpClient], Awaitable[str]] | None = None


CATALOG: tuple[Dataset, ...] = (
    Dataset(
        name="sherlock-sites",
        description="Firmas de sitios para username_sites (Sherlock)",
        # Fijado a un commit y a su hash: lo que se instala es lo revisado, no lo que haya en
        # `master` hoy. Para actualizar, cambia el commit y el hash a la vez (ver ROADMAP).
        url=(
            "https://raw.githubusercontent.com/sherlock-project/sherlock/"
            "4e2a4f6b66433849abe46cae76ed557c6c8313c8/sherlock_project/resources/data.json"
        ),
        license="MIT",
        filename="sites.json",
        prepare=_sherlock,
        sha256="3fdfc6694c5cd99798881215554b09e617c6d5284a6219fae309882566a9fb30",
    ),
    # Rangos de IP de los proveedores (`cloud_attribution`). Cambian a diario: no llevan hash
    # fijo, pero `prepare` valida el formato y el manifiesto anota el hash de lo instalado.
    Dataset(
        name="aws-ip-ranges",
        description="Rangos de IP de AWS para cloud_attribution",
        url="https://ip-ranges.amazonaws.com/ip-ranges.json",
        license="public-feed",
        filename="aws-ip-ranges.json",
        prepare=_aws,
    ),
    Dataset(
        name="gcp-ip-ranges",
        description="Rangos de IP de Google Cloud para cloud_attribution",
        url="https://www.gstatic.com/ipranges/cloud.json",
        license="public-feed",
        filename="gcp-ip-ranges.json",
        prepare=_gcp,
    ),
    Dataset(
        name="cloudflare-ips-v4",
        description="Rangos IPv4 de Cloudflare para cloud_attribution",
        url="https://www.cloudflare.com/ips-v4",
        license="public-feed",
        filename="cloudflare-ips-v4.json",
        prepare=_cloudflare,
    ),
    Dataset(
        name="cloudflare-ips-v6",
        description="Rangos IPv6 de Cloudflare para cloud_attribution",
        url="https://www.cloudflare.com/ips-v6",
        license="public-feed",
        filename="cloudflare-ips-v6.json",
        prepare=_cloudflare,
    ),
    Dataset(
        name="azure-ip-ranges",
        description="Rangos de IP de Azure (AzureCloud) para cloud_attribution",
        url=AZURE_PAGE,
        license="public-feed",
        filename="azure-ip-ranges.json",
        prepare=_azure,
        discover=_azure_url,
    ),
)
# Datasets que se comprueban solos al arrancar la CLI (ver `auto_update`).
AUTO_UPDATE = ("azure-ip-ranges",)
AUTO_UPDATE_EVERY = timedelta(days=1)
AUTO_UPDATE_STAMP = "auto-update.json"


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
    old = entries.get(dataset.name, {})
    url = await dataset.discover(http) if dataset.discover else dataset.url
    if dataset.discover and old.get("url") == url and installed_path(dataset.name):
        # La URL lleva la fecha del fichero: si es la misma, lo instalado está al día.
        return Result(
            dataset.name, "sin cambios", "", dataset.license, old.get("version", ""), old["sha256"]
        )
    response = await http.get(url)
    if response.status_code != 200:
        raise DatasetError(f"{url} respondió {response.status_code}")
    if len(response.content) > MAX_BYTES:
        raise DatasetError(f"la descarga supera {MAX_BYTES // 2**20} MiB")
    if dataset.sha256 and hashlib.sha256(response.content).hexdigest() != dataset.sha256:
        raise DatasetError(f"el hash de {url} no coincide con el fijado en el catálogo")
    data = dataset.prepare(response.content)
    sha256 = hashlib.sha256(data).hexdigest()
    if old.get("sha256") == sha256 and old.get("url") == url and installed_path(dataset.name):
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
        "url": url,
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


async def auto_update(http: HttpClient) -> list[Result]:
    """Comprueba `AUTO_UPDATE` como mucho una vez cada `AUTO_UPDATE_EVERY`; `[]` si no tocaba."""
    stamp = datasets_dir() / AUTO_UPDATE_STAMP
    now = datetime.now(UTC)
    try:
        checked = datetime.fromisoformat(json.loads(stamp.read_text("utf-8"))["checked_at"])
        if timedelta(0) <= now - checked < AUTO_UPDATE_EVERY:
            return []
    except (OSError, ValueError, KeyError, TypeError):
        pass  # sin sello válido: toca comprobar
    results = await update(http, AUTO_UPDATE)
    # También tras un error: sin red, no se reintenta en cada orden sino al día siguiente.
    _write(stamp, json.dumps({"checked_at": now.isoformat()}).encode())
    return results
