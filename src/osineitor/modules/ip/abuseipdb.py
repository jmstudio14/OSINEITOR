"""Reputación de la IP según los reportes de abuso de AbuseIPDB (requiere key)."""

from __future__ import annotations

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError


class AbuseIpDb(Module):
    name = "abuseipdb"
    description = "Puntuación de abuso y reportes de los últimos 90 días (AbuseIPDB)"
    consumes = frozenset({EntityType.IP})
    produces = frozenset({EntityType.RECORD})
    requires_key = "abuseipdb"

    async def run(self, entity: Entity) -> list[Entity]:
        response = await self.ctx.http.get(
            "https://api.abuseipdb.com/api/v2/check",
            params={"ipAddress": entity.value, "maxAgeInDays": "90"},
            headers={"Key": self.api_key or "", "Accept": "application/json"},
        )
        if response.status_code != 200:
            raise ModuleError(f"api.abuseipdb.com respondió {response.status_code}")
        data = response.json().get("data", {})
        return [
            self.emit(
                entity,
                EntityType.RECORD,
                f"abuseipdb:{entity.value}",
                abuse_score=data.get("abuseConfidenceScore"),
                total_reports=data.get("totalReports"),
                distinct_reporters=data.get("numDistinctUsers"),
                last_reported=data.get("lastReportedAt"),
                usage_type=data.get("usageType"),
                isp=data.get("isp"),
                domain=data.get("domain"),
                is_tor=data.get("isTor"),
            )
        ]
