"""Forma canónica de los valores de cada tipo de entidad.

Dos escrituras distintas del mismo dato (`MÜNCHEN.de.`, `xn--mnchen-3ya.de`) deben acabar
siendo la misma entidad. Este módulo no importa `osineitor.models` para evitar ciclos: los
tipos se identifican por su valor de texto.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit

import idna

from osineitor.errors import InvalidEntityValue
from osineitor.sanitize import clean_username

# Etiqueta DNS: se admite `_` (registros como `_dmarc`) pero no empezar ni acabar en `-`.
LABEL_RE = re.compile(r"^(?!-)[a-z0-9_-]{1,63}(?<!-)$")
DEFAULT_PORTS = {"http": 80, "https": 443}


def canonical_hostname(value: str) -> str:
    """Minúsculas, sin punto final y en punycode (IDNA 2008). Lanza `InvalidEntityValue`."""
    host = value.strip().lower().rstrip(".")
    if not host:
        raise InvalidEntityValue("dominio vacío")
    if not host.isascii():
        try:
            host = idna.encode(host, uts46=True).decode("ascii")
        except idna.IDNAError as exc:
            raise InvalidEntityValue(f"dominio no válido: {value!r} ({exc})") from exc
    if len(host) > 253 or not all(LABEL_RE.fullmatch(label) for label in host.split(".")):
        raise InvalidEntityValue(f"dominio no válido: {value!r}")
    return host


def canonical_ip(value: str) -> str:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError as exc:
        raise InvalidEntityValue(f"dirección IP no válida: {value!r}") from exc


def canonical_email(value: str) -> str:
    email = value.strip().lower()
    local, sep, domain = email.rpartition("@")
    if not sep or not local or len(local) > 64 or re.search(r"[\s\x00-\x1f]", local):
        raise InvalidEntityValue(f"email no válido: {value!r}")
    return f"{local}@{canonical_hostname(domain)}"


def canonical_url(value: str) -> str:
    """Normaliza esquema, host y puerto. Es de mejor esfuerzo: nunca lanza.

    Las URLs son evidencia (p. ej. del histórico de Wayback), no objetivos de red; si no se
    pueden interpretar se conservan tal cual.
    """
    url = value.strip()
    try:
        parts = urlsplit(url)
        host = parts.hostname
        if not parts.scheme or not host:
            return url
        host = canonical_hostname(host) if not _is_ip(host) else host
        netloc = f"[{host}]" if ":" in host else host
        if parts.port and parts.port != DEFAULT_PORTS.get(parts.scheme.lower()):
            netloc += f":{parts.port}"
        return urlunsplit((parts.scheme.lower(), netloc, parts.path, parts.query, ""))
    except ValueError:
        return url


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def canonical(entity_type: str, value: str) -> str:
    """Forma canónica de `value` según el tipo; los tipos sin regla se devuelven igual."""
    match str(entity_type):
        case "domain":
            return canonical_hostname(value)
        case "ip":
            return canonical_ip(value)
        case "email":
            return canonical_email(value)
        case "url":
            return canonical_url(value)
        case "username":
            return clean_username(value)
        case _:
            return value
