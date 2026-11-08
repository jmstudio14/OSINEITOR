"""Lista de objetivos para `scan --targets-file`: un objetivo por línea."""

from __future__ import annotations

from pathlib import Path

MAX_BYTES = 1024 * 1024
MAX_TARGETS = 200


class TargetsError(ValueError):
    """El fichero de objetivos no se puede leer o no sirve."""


def read_targets(path: Path) -> list[str]:
    """Objetivos del fichero, sin líneas vacías, comentarios (`#`) ni repetidos, en orden."""
    try:
        if path.stat().st_size > MAX_BYTES:
            raise TargetsError(f"el fichero es demasiado grande (máximo {MAX_BYTES // 1024} KiB)")
        text = path.read_bytes().decode("utf-8-sig")
    except OSError as exc:
        raise TargetsError(f"no se puede leer {path.name}: {exc.strerror or exc}") from exc
    except UnicodeDecodeError as exc:
        raise TargetsError(f"{path.name} no está en UTF-8") from exc
    found: dict[str, None] = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            found.setdefault(line)
    if not found:
        raise TargetsError(f"{path.name} no tiene ningún objetivo")
    if len(found) > MAX_TARGETS:
        raise TargetsError(f"demasiados objetivos ({len(found)}, máximo {MAX_TARGETS})")
    return list(found)
