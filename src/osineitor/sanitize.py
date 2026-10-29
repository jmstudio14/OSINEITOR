"""Saneado de valores que viajan a URLs o se reutilizan como identificadores."""

from __future__ import annotations

import re
from urllib.parse import quote

from osineitor.errors import InvalidEntityValue

# Letras, números, guion bajo, punto y guion. Excluye `/ ? # % : @`, espacios y controles.
USERNAME_RE = re.compile(r"^[\w.\-]{1,64}$")


def quote_segment(value: str) -> str:
    """Codifica `value` para usarlo como un único segmento de ruta o consulta de una URL."""
    return quote(value, safe="")


def clean_username(value: str) -> str:
    """Devuelve el username sin `@` inicial o lanza `InvalidEntityValue`."""
    cleaned = value.strip().removeprefix("@")
    if not USERNAME_RE.fullmatch(cleaned):
        raise InvalidEntityValue(
            f"username no válido: {value!r} (se admiten letras, números, '.', '_' y '-', "
            "hasta 64 caracteres)"
        )
    return cleaned


def is_valid_username(value: str) -> bool:
    try:
        clean_username(value)
    except InvalidEntityValue:
        return False
    return True
