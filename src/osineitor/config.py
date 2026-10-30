"""Configuración: API keys desde variables de entorno o fichero TOML."""

from __future__ import annotations

import getpass
import os
import subprocess
import tomllib
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import platformdirs

ENV_PREFIX = "OSINEITOR_"


def config_dir() -> Path:
    """Directorio de configuración: `OSINEITOR_CONFIG_DIR`, o el estándar de cada sistema.

    En Windows es `%APPDATA%\\osineitor`; en Linux respeta `XDG_CONFIG_HOME`.
    """
    override = os.environ.get("OSINEITOR_CONFIG_DIR")
    if override:
        return Path(override)
    return Path(platformdirs.user_config_dir("osineitor", appauthor=False, roaming=True))


def data_dir() -> Path:
    """Directorio de datos: `OSINEITOR_DATA_DIR`, o `%LOCALAPPDATA%\\osineitor` en Windows."""
    override = os.environ.get("OSINEITOR_DATA_DIR")
    if override:
        return Path(override)
    return Path(platformdirs.user_data_dir("osineitor", appauthor=False))


def config_path() -> Path:
    return config_dir() / "config.toml"


@dataclass
class Config:
    keys: dict[str, str] = field(default_factory=dict)
    timeout: float = 20.0
    user_agent: str = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
    require_purpose: bool = False  # exige --purpose en scans de emails y usernames

    def purpose_required(self) -> bool:
        """`OSINEITOR_REQUIRE_PURPOSE` (1/true/yes/on o 0/false/no/off) manda sobre el fichero."""
        env = os.environ.get(f"{ENV_PREFIX}REQUIRE_PURPOSE", "").strip().lower()
        if env in ("1", "true", "yes", "on"):
            return True
        if env in ("0", "false", "no", "off"):
            return False
        return self.require_purpose

    def key(self, name: str) -> str | None:
        """Devuelve la API key `name`; la variable de entorno tiene prioridad."""
        return os.environ.get(f"{ENV_PREFIX}{name.upper()}_KEY") or self.keys.get(name)

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        path = path or config_path()
        if not path.exists():
            return cls()
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        settings = raw.get("settings", {})
        return cls(
            keys={k: str(v) for k, v in raw.get("keys", {}).items()},
            timeout=float(settings.get("timeout", cls.timeout)),
            user_agent=str(settings.get("user_agent", cls.user_agent)),
            require_purpose=bool(settings.get("require_purpose", cls.require_purpose)),
        )

    def save(self, path: Path | None = None) -> Path:
        path = path or config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["[settings]", f"timeout = {self.timeout}", f"user_agent = {_q(self.user_agent)}"]
        lines.append(f"require_purpose = {str(self.require_purpose).lower()}")
        lines += ["", "[keys]"] + [f"{k} = {_q(v)}" for k, v in sorted(self.keys.items())]
        path.touch(mode=0o600, exist_ok=True)  # en POSIX nace privado, sin ventana con la umask
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        try:
            _restrict(path)
        except (OSError, subprocess.CalledProcessError) as exc:
            warnings.warn(f"No se pudieron restringir los permisos de {path}: {exc}", stacklevel=2)
        return path


def _restrict(path: Path) -> None:
    """Deja el fichero legible solo por el usuario actual (ACL en Windows, 0600 en el resto)."""
    if os.name == "nt":
        # `chmod` no sirve en Windows: solo cambia el atributo de solo lectura.
        user = f"{getpass.getuser()}:(R,W)"
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", user],
            check=True,
            capture_output=True,
        )
    else:
        path.chmod(0o600)


def _q(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
