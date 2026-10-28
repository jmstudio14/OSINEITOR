"""Exportación de scans a JSON, Markdown y HTML."""

from __future__ import annotations

from collections.abc import Callable

from osineitor.models import ScanResult
from osineitor.report.html import to_html
from osineitor.report.json_report import to_json
from osineitor.report.markdown import to_markdown

FORMATS: dict[str, tuple[str, Callable[[ScanResult], str]]] = {
    "json": ("json", to_json),
    "md": ("md", to_markdown),
    "html": ("html", to_html),
}


def render(result: ScanResult, fmt: str) -> str:
    return FORMATS[fmt][1](result)
