"""Proveedores de correo, DNS, identidad y colaboración deducidos del DNS ya recogido."""

from __future__ import annotations

import json
import re
from functools import cache
from importlib import resources
from typing import Any

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module

SPF_HOST = re.compile(r"\b(?:include:|redirect=)([^\s]+)", re.I)


@cache
def signatures() -> dict[str, Any]:
    path = resources.files(__package__).joinpath("data/saas_signatures.json")
    return json.loads(path.read_text(encoding="utf-8"))


def _host(value: str) -> str:
    """Nombre de host de un valor MX («10 mx.example.com.») o NS, en minúsculas."""
    return value.split()[-1].lower().rstrip(".") if value.split() else ""


def _suffix(host: str, patterns: list[str]) -> str | None:
    return next((p for p in patterns if host == p or host.endswith(f".{p}")), None)


class SaasFootprint(Module):
    name = "saas_footprint"
    description = "Proveedores de correo, DNS, identidad y colaboración deducidos del DNS"
    consumes = frozenset({EntityType.RECORD})
    produces = frozenset({EntityType.TECHNOLOGY})
    analyzer = True
    canary = "example.com"

    def accepts(self, entity: Entity) -> bool:
        return entity.type == EntityType.RECORD and entity.value.startswith("dns:")

    async def run(self, entity: Entity) -> list[Entity]:
        data = entity.data
        mx = [_host(v) for v in data.get("MX", [])]
        ns = [_host(v) for v in data.get("NS", [])]
        txt = [v.lower() for v in data.get("TXT", [])]
        includes = [m.rstrip(".").lower() for m in SPF_HOST.findall(data.get("SPF") or "")]
        version = signatures()["version"]

        out = []
        for provider in signatures()["providers"]:
            evidence = []
            for host in mx:
                if hit := _suffix(host, provider.get("mx", [])):
                    evidence.append(f"MX {host} ({hit})")
            for host in ns:
                hit = _suffix(host, provider.get("ns", [])) or next(
                    (p for p in provider.get("ns_contains", []) if p in host), None
                )
                if hit:
                    evidence.append(f"NS {host} ({hit})")
            for host in includes:
                if hit := _suffix(host, provider.get("spf", [])):
                    evidence.append(f"SPF include:{host} ({hit})")
            for value in txt:
                if hit := next((p for p in provider.get("txt", []) if value.startswith(p)), None):
                    evidence.append(f"TXT {hit}")
            if evidence:
                out.append(
                    self.emit(
                        entity,
                        EntityType.TECHNOLOGY,
                        provider["name"],
                        category=provider["category"],
                        evidence=sorted(set(evidence)),
                        signatures=version,
                    )
                )
        return out
