"""Quita los estilos ANSI que Typer escribe si detecta una CI (`GITHUB_ACTIONS`, `FORCE_COLOR`)."""

from __future__ import annotations

import re

_STYLE = re.compile(r"\x1b\[[0-9;]*m")


def plain(text: str) -> str:
    return _STYLE.sub("", text)
