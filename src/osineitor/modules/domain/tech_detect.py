"""Tecnologías del sitio por firmas propias: cabeceras, cookies, `meta`, scripts y HTML (ACTIVO)."""

from __future__ import annotations

import json
import re
from functools import cache
from importlib import resources
from typing import Any

import httpx

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError
from osineitor.modules.domain._util import is_root_domain

MAX_BODY = 500_000
MAX_CMS_ASSETS = 50
WP_ASSET = re.compile(
    r"""/wp-content/(plugins|themes)/([a-z0-9_-]+)/(?:[^"'\s<>]*?\?ver=([0-9][\w.-]*))?""",
    re.IGNORECASE,
)
META = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
ATTR = re.compile(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
SCRIPT_SRC = re.compile(r"""<script\b[^>]*\bsrc\s*=\s*["']([^"']+)""", re.IGNORECASE)


@cache
def signatures() -> dict[str, Any]:
    path = resources.files(__package__).joinpath("data/tech_signatures.json")
    return json.loads(path.read_text(encoding="utf-8"))


def _meta_tags(body: str) -> dict[str, str]:
    """`name` → `content` de las etiquetas `<meta>`, en minúsculas."""
    tags: dict[str, str] = {}
    for tag in META.findall(body):
        attrs = {k.lower(): a or b for k, a, b in ATTR.findall(tag)}
        if attrs.get("name") and "content" in attrs:
            tags.setdefault(attrs["name"].lower(), attrs["content"])
    return tags


def _cookie_names(headers: httpx.Headers) -> list[str]:
    return [c.split("=", 1)[0].strip() for c in headers.get_list("set-cookie")]


def detect(response: httpx.Response, body: str) -> dict[str, dict[str, Any]]:
    """`{tecnología: {category, version, evidence}}` según las firmas versionadas."""
    headers = {k.lower(): v for k, v in response.headers.items()}
    cookies = _cookie_names(response.headers)
    meta = _meta_tags(body)
    scripts = SCRIPT_SRC.findall(body)
    found: dict[str, dict[str, Any]] = {}

    def hit(sig: dict[str, Any], evidence: str, match: re.Match[str] | None) -> None:
        item = found.setdefault(
            sig["name"], {"category": sig["category"], "version": None, "evidence": []}
        )
        if evidence not in item["evidence"]:
            item["evidence"].append(evidence)
        if match and match.groups() and match.group(1) and not item["version"]:
            item["version"] = match.group(1)

    for sig in signatures()["technologies"]:
        for header, pattern in sig.get("headers", {}).items():
            if (value := headers.get(header)) is not None and (
                m := re.search(pattern, value, re.IGNORECASE)
            ):
                hit(sig, f"cabecera {header}", m)
        for pattern in sig.get("cookies", []):
            for name in cookies:
                if re.search(pattern, name):
                    hit(sig, f"cookie {name}", None)
        for name, pattern in sig.get("meta", {}).items():
            if (value := meta.get(name)) is not None and (
                m := re.search(pattern, value, re.IGNORECASE)
            ):
                hit(sig, f"meta {name}", m)
        for pattern in sig.get("scripts", []):
            for src in scripts:
                if m := re.search(pattern, src, re.IGNORECASE):
                    hit(sig, "script", m)
                    break
        for pattern in sig.get("html", []):
            if m := re.search(pattern, body, re.IGNORECASE):
                hit(sig, "html", m)
    return found


def cms_assets(body: str) -> dict[str, dict[str, Any]]:
    """Plugins y temas de WordPress que la propia portada enlaza: `{nombre: {category, version}}`.

    shortcut: el `?ver=` es el que pone el plugin al cargar sus ficheros y no siempre es su
    versión; es una pista. Solo ve lo que carga la portada, no enumera nada más.
    """
    found: dict[str, dict[str, Any]] = {}
    for kind, slug, version in WP_ASSET.findall(body):
        singular = "plugin" if kind.lower() == "plugins" else "theme"
        name = f"WordPress {singular}: {slug.lower()}"
        if name not in found and len(found) >= MAX_CMS_ASSETS:
            continue
        item = found.setdefault(name, {"category": singular, "version": None})
        item["version"] = item["version"] or version or None
    return found


class TechDetect(Module):
    name = "tech_detect"
    authority = "authoritative"
    description = "Tecnologías del sitio por firmas propias (contacta al objetivo)"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.TECHNOLOGY})
    passive = False
    canary = "example.com"

    def accepts(self, entity: Entity) -> bool:
        return is_root_domain(entity)

    async def run(self, entity: Entity) -> list[Entity]:
        response = None
        for scheme in ("https", "http"):
            try:
                response = await self.ctx.http.get(f"{scheme}://{entity.value}")
                break
            except httpx.TransportError:
                continue
        if response is None:
            raise ModuleError("el sitio no responde por HTTP(S)")
        version = signatures()["version"]
        body = response.text[:MAX_BODY]
        by_signature = [
            self.emit(
                entity,
                EntityType.TECHNOLOGY,
                name,
                category=info["category"],
                version=info["version"],
                evidence=info["evidence"],
                signatures=version,
            )
            for name, info in sorted(detect(response, body).items())
        ]
        assets = [
            self.emit(
                entity,
                EntityType.TECHNOLOGY,
                name,
                category=info["category"],
                version=info["version"],
                evidence=["html"],
            )
            for name, info in sorted(cms_assets(body).items())
        ]
        return by_signature + assets
