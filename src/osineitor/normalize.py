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
ASN_RE = re.compile(r"^(?:as)?(\d{1,10})$", re.IGNORECASE)
MAX_ASN = 2**32 - 1
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")
CRYPTO_RE = re.compile(r"^[A-Za-z0-9]{14,128}$")
MAX_TEXT = 512


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


def canonical_asn(value: str) -> str:
    """`as13335`, `AS13335` y `13335` son el mismo sistema autónomo: `AS13335`."""
    match = ASN_RE.fullmatch(value.strip())
    if not match or not 1 <= int(match[1]) <= MAX_ASN:
        raise InvalidEntityValue(f"ASN no válido: {value!r}")
    return f"AS{int(match[1])}"


def canonical_netblock(value: str) -> str:
    """Red en notación CIDR con los bits de host a cero (`10.0.0.5/24` → `10.0.0.0/24`)."""
    try:
        return str(ipaddress.ip_network(value.strip(), strict=False))
    except ValueError as exc:
        raise InvalidEntityValue(f"bloque de red no válido: {value!r}") from exc


def canonical_fingerprint(value: str) -> str:
    """Huella SHA-256 de un certificado: 64 hexadecimales en minúsculas, sin `:` ni espacios."""
    fingerprint = re.sub(r"[:\s]", "", value).lower()
    if not SHA256_RE.fullmatch(fingerprint):
        raise InvalidEntityValue(f"huella SHA-256 no válida: {value!r}")
    return fingerprint


def canonical_phone(value: str) -> str:
    """Teléfono en formato E.164 (`+34 600-123-456` → `+34600123456`); `00` equivale a `+`."""
    phone = re.sub(r"[\s().\-]", "", value)
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    if not PHONE_RE.fullmatch(phone):
        raise InvalidEntityValue(f"teléfono no válido: {value!r} (usa el prefijo internacional)")
    return phone


def canonical_crypto_address(value: str) -> str:
    """Dirección de criptomoneda tal cual (distingue mayúsculas); solo se comprueba su forma."""
    address = value.strip()
    if not CRYPTO_RE.fullmatch(address):
        raise InvalidEntityValue(f"dirección de criptomoneda no válida: {value!r}")
    return address


def canonical_text(entity_type: str, value: str) -> str:
    """Texto libre (organización, persona...) con los espacios colapsados."""
    text = " ".join(value.split())
    if not text or len(text) > MAX_TEXT or not text.isprintable():
        raise InvalidEntityValue(
            f"{entity_type} no válido: debe tener entre 1 y {MAX_TEXT} caracteres imprimibles"
        )
    return text


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
        case "asn":
            return canonical_asn(value)
        case "netblock":
            return canonical_netblock(value)
        case "certificate":
            return canonical_fingerprint(value)
        case "phone":
            return canonical_phone(value)
        case "crypto_address":
            return canonical_crypto_address(value)
        case "technology" | "organization" | "person" | "file" | "location" | "finding":
            return canonical_text(str(entity_type), value)
        case _:
            return value
