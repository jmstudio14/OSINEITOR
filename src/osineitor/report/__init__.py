"""Exportación de scans a JSON, Markdown, HTML, CSV y formatos de grafo."""

from __future__ import annotations

from collections.abc import Callable

from osineitor.models import ScanResult
from osineitor.report.csv_report import to_csv_entities, to_csv_findings, to_csv_relations
from osineitor.report.graph_export import to_cypher, to_gexf, to_graphml
from osineitor.report.html import to_html
from osineitor.report.json_report import to_json
from osineitor.report.markdown import to_markdown

FORMATS: dict[str, tuple[str, Callable[[ScanResult], str]]] = {
    "json": ("json", to_json),
    "md": ("md", to_markdown),
    "html": ("html", to_html),
    "csv": ("entities.csv", to_csv_entities),
    "csv-relations": ("relations.csv", to_csv_relations),
    "csv-findings": ("findings.csv", to_csv_findings),
    "graphml": ("graphml", to_graphml),
    "gexf": ("gexf", to_gexf),
    "cypher": ("cypher", to_cypher),
}


def render(result: ScanResult, fmt: str) -> str:
    return FORMATS[fmt][1](result)
