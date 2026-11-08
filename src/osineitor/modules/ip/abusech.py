"""IOC asociados a un dominio o IP en ThreatFox y URLhaus, de abuse.ch (requiere Auth-Key).

Sobre el `record` de `file_hash`, busca el hash en MalwareBazaar: solo sale la huella.
"""

from __future__ import annotations

from typing import Any

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError, status_error

THREATFOX = "https://threatfox-api.abuse.ch/api/v1/"
URLHAUS = "https://urlhaus-api.abuse.ch/v1/host/"
BAZAAR = "https://mb-api.abuse.ch/api/v1/"
MAX_ITEMS = 20
FILE_HASH = "file_hash:"


class AbuseCh(Module):
    name = "abusech"
    description = "IOC en ThreatFox y URLhaus y hash de fichero en MalwareBazaar (abuse.ch)"
    consumes = frozenset({EntityType.DOMAIN, EntityType.IP, EntityType.RECORD})
    produces = frozenset({EntityType.RECORD})
    requires_key = "abusech"
    canary = "example.com"
    min_interval = 1.0

    def accepts(self, entity: Entity) -> bool:
        if entity.type == EntityType.RECORD:
            return entity.value.startswith(FILE_HASH)
        return entity.type == EntityType.IP or (
            entity.type == EntityType.DOMAIN and not entity.data.get("subdomain")
        )

    def _check(self, service: str, status: int) -> None:
        if status in (401, 403):
            raise ModuleError(f"Auth-Key de abuse.ch inválida o sin acceso a {service}")

    async def _sample(self, entity: Entity, headers: dict[str, str]) -> list[Entity]:
        sha256 = entity.value.removeprefix(FILE_HASH)
        response = await self.ctx.http.post(
            BAZAAR, data={"query": "get_info", "hash": sha256}, headers=headers
        )
        self._check("MalwareBazaar", response.status_code)
        if response.status_code != 200:
            raise status_error("mb-api.abuse.ch", response)
        body = response.json()
        status = body.get("query_status")
        if status == "hash_not_found":
            return []
        if status != "ok":
            raise ModuleError(f"mb-api.abuse.ch respondió {status}")
        samples = [s for s in body.get("data") or [] if isinstance(s, dict)]
        if not samples:
            return []
        sample = samples[0]
        return [
            self.emit(
                entity,
                EntityType.RECORD,
                f"abusech:{sha256}",
                malware=sample.get("signature"),
                file_type=sample.get("file_type"),
                first_seen=sample.get("first_seen"),
                last_seen=sample.get("last_seen"),
                tags=(sample.get("tags") or [])[:MAX_ITEMS],
            )
        ]

    async def run(self, entity: Entity) -> list[Entity]:
        headers = {"Auth-Key": self.api_key or ""}
        if entity.type == EntityType.RECORD:
            return await self._sample(entity, headers)
        value = entity.value

        fox = await self.ctx.http.post(
            THREATFOX,
            json={"query": "search_ioc", "search_term": value, "exact_match": True},
            headers=headers,
        )
        self._check("ThreatFox", fox.status_code)
        if fox.status_code != 200:
            raise status_error("threatfox-api.abuse.ch", fox)
        hits: list[dict[str, Any]] = [
            h for h in fox.json().get("data") or [] if isinstance(h, dict)
        ]

        haus = await self.ctx.http.post(URLHAUS, data={"host": value}, headers=headers)
        self._check("URLhaus", haus.status_code)
        if haus.status_code != 200:
            raise status_error("urlhaus-api.abuse.ch", haus)
        haus_data = haus.json()
        urls = haus_data.get("urls") if haus_data.get("query_status") == "ok" else []
        urls = [u for u in urls or [] if isinstance(u, dict)]

        if not hits and not urls:
            return []
        return [
            self.emit(
                entity,
                EntityType.RECORD,
                f"abusech:{value}",
                threatfox=len(hits),
                malware=sorted(
                    {h.get("malware_printable") for h in hits if h.get("malware_printable")}
                ),
                threat_types=sorted({h.get("threat_type") for h in hits if h.get("threat_type")}),
                first_seen=min(
                    (h["first_seen"] for h in hits if h.get("first_seen")), default=None
                ),
                last_seen=max((h["last_seen"] for h in hits if h.get("last_seen")), default=None),
                urlhaus=int(haus_data.get("url_count") or len(urls)),
                urlhaus_online=sum(1 for u in urls if u.get("url_status") == "online"),
                urlhaus_threats=sorted({u.get("threat") for u in urls if u.get("threat")}),
                tags=sorted({t for h in hits for t in h.get("tags") or []})[:MAX_ITEMS],
            )
        ]
