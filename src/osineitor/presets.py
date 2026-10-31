"""Presets de escaneo: perfiles reutilizables que fijan módulos, profundidad y presupuesto.

Cada preset es un YAML cuyo nombre es el del fichero. Los incluidos están en `data/presets/`; los
del usuario, en `<config>/presets/`. Uno del usuario con el mismo nombre sustituye al incluido.

    description: Reconocimiento pasivo de un dominio
    depth: 2                      # 1 a 4
    modules: [crtsh, dns, rdap]   # sin esta clave, todos
    allow_active: false           # true ADMITE los módulos activos; sigue haciendo falta --active
    max_entities: 500             # presupuesto; 0 = sin límite
    max_requests: 300
    max_time: 120

Lo que el usuario indique en la línea de órdenes manda sobre el preset.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from osineitor.config import config_dir

KEYS = (
    "description",
    "depth",
    "modules",
    "allow_active",
    "max_entities",
    "max_requests",
    "max_time",
)
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
MODULE_RE = re.compile(r"^[a-z0-9_]+$")
BUILTIN_DIR = Path(__file__).parent / "data" / "presets"


class PresetError(ValueError):
    """Un preset no existe o no es válido."""


@dataclass(frozen=True)
class Preset:
    name: str
    source: str  # "incluido" | "usuario" | "usuario (sobrescribe)"
    description: str = ""
    depth: int | None = None
    modules: tuple[str, ...] | None = None  # None: todos
    allow_active: bool = False
    max_entities: int | None = None
    max_requests: int | None = None
    max_time: float | None = None


def user_dir() -> Path:
    return config_dir() / "presets"


def _number(raw: dict[str, Any], key: str, kind: type) -> Any:
    value = raw.get(key)
    if value is None:
        return None
    valid = isinstance(value, int | float) if kind is float else isinstance(value, int)
    if isinstance(value, bool) or not valid or value < 0:
        raise PresetError(f"`{key}` debe ser un número no negativo")
    return value


def _parse(name: str, raw: Any, source: str) -> Preset:
    if not isinstance(raw, dict):
        raise PresetError("debe ser un mapa con claves como `depth` o `modules`")
    if unknown := set(raw) - set(KEYS):
        raise PresetError(f"claves desconocidas: {', '.join(sorted(map(str, unknown)))}")
    description = raw.get("description", "")
    if not isinstance(description, str):
        raise PresetError("`description` debe ser un texto")
    depth = raw.get("depth")
    valid_depth = type(depth) is int and 1 <= depth <= 4
    if depth is not None and not valid_depth:
        raise PresetError("`depth` debe ser un entero de 1 a 4")
    modules = raw.get("modules")
    if modules is not None and not (
        isinstance(modules, list)
        and modules
        and all(isinstance(m, str) and MODULE_RE.fullmatch(m) for m in modules)
    ):
        raise PresetError("`modules` debe ser una lista no vacía de nombres de módulo")
    allow_active = raw.get("allow_active", False)
    if not isinstance(allow_active, bool):
        raise PresetError("`allow_active` debe ser true o false")
    return Preset(
        name=name,
        source=source,
        description=description.strip(),
        depth=depth,
        modules=tuple(modules) if modules else None,
        allow_active=allow_active,
        max_entities=_number(raw, "max_entities", int),
        max_requests=_number(raw, "max_requests", int),
        max_time=_number(raw, "max_time", float),
    )


def _load_dir(path: Path, source: str) -> tuple[dict[str, Preset], dict[str, str]]:
    found: dict[str, Preset] = {}
    errors: dict[str, str] = {}
    files = sorted([*path.glob("*.yml"), *path.glob("*.yaml")]) if path.is_dir() else []
    for file in files:
        name = file.stem
        try:
            if not NAME_RE.fullmatch(name):
                raise PresetError("el nombre del fichero debe ser minúsculas, números, `-` o `_`")
            try:
                raw = yaml.safe_load(file.read_text(encoding="utf-8"))
            except OSError as exc:
                raise PresetError(f"no se puede leer: {exc.strerror or exc}") from exc
            except (yaml.YAMLError, UnicodeDecodeError) as exc:
                raise PresetError(f"no es un YAML válido: {exc}") from exc
            found[name] = _parse(name, raw, source)
        except PresetError as exc:
            errors[name] = f"{file}: {exc}"
    return found, errors


def load_all() -> tuple[dict[str, Preset], dict[str, str]]:
    """Presets disponibles y, aparte, el motivo de cada fichero que no se pudo cargar.

    Un fichero roto no tumba a los demás, pero tampoco se ignora en silencio: `get` falla si el
    preset pedido es uno de ellos.
    """
    presets, errors = _load_dir(BUILTIN_DIR, "incluido")
    mine, mine_errors = _load_dir(user_dir(), "usuario")
    for name, preset in mine.items():
        presets[name] = replace(
            preset, source="usuario (sobrescribe)" if name in presets else "usuario"
        )
    return dict(sorted(presets.items())), {**errors, **mine_errors}


def get(name: str) -> Preset:
    presets, errors = load_all()
    if name in errors:
        raise PresetError(errors[name])
    if name not in presets:
        raise PresetError(f"preset desconocido: {name} (disponibles: {', '.join(presets)})")
    return presets[name]
