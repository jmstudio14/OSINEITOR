"""Configuración: API keys desde variables de entorno o fichero TOML."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ENV_PREFIX = "OSINEITOR_"


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "osineitor"


def data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / "osineitor"


def config_path() -> Path:
    return config_dir() / "config.toml"


@dataclass
class Config:
    keys: dict[str, str] = field(default_factory=dict)
    timeout: float = 20.0
    user_agent: str = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"

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
        )

    def save(self, path: Path | None = None) -> Path:
        path = path or config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["[settings]", f"timeout = {self.timeout}", f"user_agent = {_q(self.user_agent)}"]
        lines += ["", "[keys]"] + [f"{k} = {_q(v)}" for k, v in sorted(self.keys.items())]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        path.chmod(0o600)
        return path


def _q(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
