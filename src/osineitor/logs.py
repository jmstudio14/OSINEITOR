"""Registro estructurado (JSON, una línea por registro) con las API keys siempre fuera.

Sin `--verbose` ni `--log-file` no hay ningún handler: no se escribe nada. Las keys viajan en la
query y en cabeceras, así que el registro nunca guarda ni una ni otras (`redact_url`), y además el
formateador sustituye por `***` cualquier valor de key conocido en cualquier texto (`_scrub`).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any

import httpx

from osineitor.config import ENV_PREFIX, Config

ROOT = "osineitor"
MIN_SECRET_LENGTH = 4  # una "key" más corta reemplazaría trozos de texto cualquiera
MASK = "***"

_to_stderr = False
_secrets: list[str] = []  # los que enmascara el registro activo; `mask_credentials` añade


def redact_url(url: str) -> str:
    """`esquema://host[:puerto]/ruta`: sin credenciales, consulta ni fragmento."""
    scheme, sep, rest = url.partition("://")
    if not sep:
        return url.split("?", 1)[0].split("#", 1)[0]
    authority, slash, path = rest.partition("/")
    path = path.split("?", 1)[0].split("#", 1)[0]
    authority = authority.split("?", 1)[0].split("#", 1)[0].rpartition("@")[2]
    return f"{scheme}://{authority}{slash}{path}"


def _url_password(url: str) -> set[str]:
    try:
        return {httpx.URL(url).password} - {""}
    except httpx.InvalidURL:  # un proxy mal escrito lo rechaza `--proxy` más adelante
        return set()


def mask_credentials(url: str) -> None:
    """Enmascara en el registro la contraseña de una URL (p. ej. la de `--proxy`)."""
    for password in _url_password(url):
        if len(password) >= MIN_SECRET_LENGTH and password not in _secrets:
            _secrets.append(password)
            _secrets.sort(key=lambda v: (-len(v), v))


def known_secrets() -> list[str]:
    """Valores de las API keys configuradas (fichero y variables de entorno), las largas primero."""
    values = set(Config.load().keys.values())
    values |= {v for k, v in os.environ.items() if k.startswith(ENV_PREFIX) and k.endswith("_KEY")}
    values |= _url_password(os.environ.get(f"{ENV_PREFIX}PROXY", ""))
    return sorted((v for v in values if len(v) >= MIN_SECRET_LENGTH), key=lambda v: (-len(v), v))


class JsonFormatter(logging.Formatter):
    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        self._secrets = secrets

    def _scrub(self, value: Any) -> Any:
        if isinstance(value, str):
            for secret in self._secrets:
                value = value.replace(secret, MASK)
            return value
        if isinstance(value, dict):
            return {self._scrub(str(k)): self._scrub(v) for k, v in value.items()}
        if isinstance(value, list | tuple | set | frozenset):
            return [self._scrub(v) for v in value]
        return value

    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            **getattr(record, "fields", {}),
        }
        if record.exc_info:
            data["exc"] = f"{record.exc_info[0].__name__}: {record.exc_info[1]}"
        return json.dumps(self._scrub(data), ensure_ascii=False, default=str)


def close() -> None:
    """Cierra y retira los handlers (también libera el fichero en Windows)."""
    global _to_stderr
    logger = logging.getLogger(ROOT)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    _to_stderr = False


def setup(verbose: bool = False, log_file: str | os.PathLike[str] | None = None) -> None:
    """Configura el registro; idempotente. Lanza `OSError` si no se puede abrir el fichero."""
    global _to_stderr
    close()
    logger = logging.getLogger(ROOT)
    logger.propagate = False
    handlers: list[logging.Handler] = []
    if log_file:
        handlers.append(logging.FileHandler(log_file, mode="a", encoding="utf-8"))
    if verbose:
        handlers.append(logging.StreamHandler(sys.stderr))
    if handlers:
        _secrets[:] = known_secrets()
        formatter = JsonFormatter(_secrets)
        for handler in handlers:
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    else:
        logger.addHandler(logging.NullHandler())  # sin esto Python imprimiría los WARNING
        logger.setLevel(logging.WARNING)
    _to_stderr = verbose


def to_stderr() -> bool:
    """¿Hay registros saliendo por `stderr`? (entonces no se dibuja la barra de progreso)."""
    return _to_stderr


def get(name: str) -> logging.Logger:
    return logging.getLogger(f"{ROOT}.{name}")
