"""Preferencias de la aplicación, en un JSON propio (las API keys siguen en la CLI)."""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import platformdirs

from osineitor_gui.legal import LEGAL_VERSION

THEMES = ("system", "light", "dark")


def settings_dir() -> Path:
    """`OSINEITOR_GUI_CONFIG_DIR`, o `%APPDATA%\\osineitor-gui` en Windows."""
    override = os.environ.get("OSINEITOR_GUI_CONFIG_DIR")
    if override:
        return Path(override)
    return Path(platformdirs.user_config_dir("osineitor-gui", appauthor=False, roaming=True))


def settings_path() -> Path:
    return settings_dir() / "settings.json"


@dataclass
class GuiSettings:
    theme: str = "system"
    legal_accepted: int = 0  # versión del aviso legal aceptada (0 = ninguna)
    last_kind: str = "auto"
    last_export_dir: str = ""
    window_geometry: str = ""  # base64 de QMainWindow.saveGeometry()

    @property
    def needs_legal(self) -> bool:
        return self.legal_accepted < LEGAL_VERSION

    def accept_legal(self) -> None:
        self.legal_accepted = LEGAL_VERSION

    @classmethod
    def load(cls, path: Path | None = None) -> GuiSettings:
        """Carga las preferencias; un fichero ausente o corrupto da los valores por defecto."""
        path = path or settings_path()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(raw, dict):
            return cls()
        defaults = cls()
        values = {}
        for f in fields(cls):
            value = raw.get(f.name, getattr(defaults, f.name))
            # Un valor del tipo equivocado (editado a mano) se descarta, no rompe el arranque.
            values[f.name] = (
                value
                if type(value) is type(getattr(defaults, f.name))
                else getattr(defaults, f.name)
            )
        if values["theme"] not in THEMES:
            values["theme"] = "system"
        return cls(**values)

    def save(self, path: Path | None = None) -> Path:
        """Guarda de forma atómica: nunca queda un fichero a medias si se cierra el programa."""
        path = path or settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
        with contextlib.suppress(OSError):
            tmp.unlink()
        return path
