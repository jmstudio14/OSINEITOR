"""CVSS (NVD), probabilidad de explotación EPSS (FIRST) y marca KEV (CISA) de cada CVE."""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

import httpx

from osineitor.errors import ModuleError, ModuleQuota
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Context, Module, status_error

CVE_ID = re.compile(r"^CVE-\d{4}-\d{4,}$", re.IGNORECASE)
NVD = "https://services.nvd.nist.gov/rest/json/cves/2.0"
EPSS = "https://api.first.org/data/v1/epss"
KEV = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
# De la versión más reciente de CVSS a la más antigua: se usa la primera que traiga la CVE.
CVSS_METRICS = (
    ("cvssMetricV40", "4.0"),
    ("cvssMetricV31", "3.1"),
    ("cvssMetricV30", "3.0"),
    ("cvssMetricV2", "2.0"),
)
# NVD permite 5 peticiones cada 30 s sin clave y 50 con ella.
NVD_INTERVAL = 6.5
NVD_INTERVAL_KEY = 0.7
MAX_CVSS = 30  # CVE por escaneo que consultan a NVD; el resto solo lleva EPSS y KEV


class CveEnrich(Module):
    name = "cve_enrich"
    description = "CVSS (NVD), EPSS (FIRST) y marca KEV (CISA) de las CVE; clave 'nvd' opcional"
    consumes = frozenset({EntityType.VULNERABILITY})
    produces = frozenset({EntityType.VULNERABILITY})
    probe_url = f"{EPSS}?cve=CVE-2021-44228"
    timeout = 600.0  # las consultas a NVD se espacian según su límite de uso

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx)
        self._nvd_lock = asyncio.Lock()
        self._nvd_last = 0.0
        self._nvd_count = 0
        self._kev_lock = asyncio.Lock()
        self._kev: dict[str, dict[str, Any]] | None = None

    def accepts(self, entity: Entity) -> bool:
        return entity.type == EntityType.VULNERABILITY and bool(CVE_ID.match(entity.value))

    async def _cvss(self, cve: str) -> dict[str, object]:
        key = self.ctx.config.key("nvd")
        async with self._nvd_lock:
            if self._nvd_count >= MAX_CVSS:
                return {}
            self._nvd_count += 1
            wait = self._nvd_last + (NVD_INTERVAL_KEY if key else NVD_INTERVAL) - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                response = await self.ctx.http.get(
                    NVD, params={"cveId": cve}, headers={"apiKey": key} if key else None
                )
            finally:
                self._nvd_last = time.monotonic()
        if response.status_code in (403, 429):
            raise ModuleQuota("NVD rechazó la petición por límite de uso (configura la key 'nvd')")
        if response.status_code == 404:
            return {}
        if response.status_code != 200:
            raise status_error("NVD", response)
        for item in response.json().get("vulnerabilities", []):
            metrics = item.get("cve", {}).get("metrics", {})
            for name, version in CVSS_METRICS:
                if metrics.get(name):
                    data = metrics[name][0].get("cvssData", {})
                    return {
                        "cvss": data.get("baseScore"),
                        "cvss_version": version,
                        "cvss_severity": data.get("baseSeverity")
                        or metrics[name][0].get("baseSeverity"),
                    }
        return {}

    async def _epss(self, cve: str) -> dict[str, object]:
        response = await self.ctx.http.get(EPSS, params={"cve": cve})
        if response.status_code != 200:
            raise status_error("api.first.org", response)
        rows = response.json().get("data") or []
        if not rows:
            return {}  # CVE demasiado reciente para tener puntuación
        try:
            return {
                "epss": float(rows[0]["epss"]),
                "epss_percentile": float(rows[0]["percentile"]),
                "epss_date": rows[0].get("date"),
            }
        except (KeyError, ValueError) as exc:
            raise ModuleError("api.first.org devolvió una puntuación EPSS ilegible") from exc

    async def _kev_catalog(self) -> dict[str, dict[str, Any]]:
        async with self._kev_lock:
            if self._kev is None:
                response = await self.ctx.http.get(KEV, timeout=60)
                if response.status_code != 200:
                    raise status_error("cisa.gov", response)
                self._kev = {
                    v["cveID"].upper(): v
                    for v in response.json().get("vulnerabilities", [])
                    if isinstance(v.get("cveID"), str)
                }
            return self._kev

    async def _kev_flag(self, cve: str) -> dict[str, object]:
        item = (await self._kev_catalog()).get(cve)
        if item is None:
            return {"kev": False}
        return {
            "kev": True,
            "kev_due_date": item.get("dueDate"),
            "kev_ransomware": item.get("knownRansomwareCampaignUse") == "Known",
        }

    async def run(self, entity: Entity) -> list[Entity]:
        cve = entity.value.upper()
        results = await asyncio.gather(
            self._cvss(cve), self._epss(cve), self._kev_flag(cve), return_exceptions=True
        )
        fields: dict[str, object] = {}
        errors: list[Exception] = []
        for result in results:
            if isinstance(result, httpx.TimeoutException):
                errors.append(ModuleError("una fuente de CVE no respondió a tiempo"))
            elif isinstance(result, Exception):
                errors.append(result)
            else:
                fields.update(result)
        if not fields:
            if errors:
                # Una cuota agotada es lo que el usuario puede arreglar: manda sobre otro fallo.
                raise next((e for e in errors if isinstance(e, ModuleQuota)), errors[0])
            return []
        return [self.emit(entity, EntityType.VULNERABILITY, entity.value, **fields)]
