"""Certificados del dominio en Certificate Transparency: huella, emisor, validez y SAN."""

from __future__ import annotations

import asyncio
import hashlib
import ssl
from datetime import UTC, datetime
from typing import Any

import httpx

from osineitor.errors import InvalidEntityValue, ModuleError
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, status_error
from osineitor.modules.domain._util import is_root_domain
from osineitor.normalize import canonical_hostname

MAX_CERTS = 20
MAX_DOMAINS = 200
EXPIRING_DAYS = 30
DOWNLOAD_BUDGET = 150.0  # segundos para bajar los PEM, tras la consulta de la lista


def _date(value: object) -> datetime | None:
    """Fecha de crt.sh (UTC sin zona, `2026-09-26T22:05:05`)."""
    try:
        return datetime.fromisoformat(str(value)).replace(tzinfo=UTC)
    except ValueError:
        return None


def _status(days: int | None) -> str | None:
    if days is None:
        return None
    if days < 0:
        return "caducado"
    return "caduca_pronto" if days <= EXPIRING_DAYS else "valido"


class CertDetails(Module):
    name = "cert_details"
    description = "Certificados en Certificate Transparency: huella, emisor, validez y SAN (crt.sh)"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.CERTIFICATE, EntityType.DOMAIN})
    canary = "example.com"
    min_interval = 1.0  # crt.sh es un servicio voluntario y se satura con facilidad
    timeout = 400.0  # la lista admite 60 s × 3 intentos, más DOWNLOAD_BUDGET

    def accepts(self, entity: Entity) -> bool:
        return is_root_domain(entity)

    async def _fingerprint(self, cert_id: int) -> str:
        """SHA-256 del certificado en DER, que es la huella que enseñan los navegadores."""
        response = await self.ctx.http.get("https://crt.sh/", params={"d": cert_id}, timeout=60)
        if response.status_code != 200:
            raise status_error("crt.sh", response)
        try:
            der = ssl.PEM_cert_to_DER_cert(response.text.strip())
        except ValueError as exc:
            raise ModuleError(f"crt.sh no devolvió un certificado válido para {cert_id}") from exc
        return hashlib.sha256(der).hexdigest()

    async def run(self, entity: Entity) -> list[Entity]:
        domain = entity.value.lower()
        try:
            response = await self.ctx.http.get(
                "https://crt.sh/", params={"q": domain, "output": "json"}, timeout=60
            )
        except httpx.TimeoutException as exc:
            raise ModuleError("crt.sh no respondió a tiempo (suele estar saturado)") from exc
        if response.status_code != 200:
            raise status_error("crt.sh", response)
        try:
            rows = response.json()
        except ValueError as exc:
            raise ModuleError("crt.sh no devolvió JSON (suele ocurrir si está saturado)") from exc

        by_id: dict[int, dict[str, Any]] = {
            row["id"]: row for row in rows if isinstance(row.get("id"), int)
        }
        newest = sorted(by_id.values(), key=lambda r: str(r.get("not_before")), reverse=True)
        newest = newest[:MAX_CERTS]
        tasks = [asyncio.ensure_future(self._fingerprint(row["id"])) for row in newest]
        # crt.sh tarda decenas de segundos por certificado cuando está saturado: lo que no llegue
        # a tiempo se descarta en lugar de perder también lo ya descargado.
        try:
            await asyncio.wait(tasks, timeout=DOWNLOAD_BUDGET)
        finally:
            late = [task for task in tasks if not task.done()]
            for task in late:
                task.cancel()
            await asyncio.gather(*late, return_exceptions=True)
        fingerprints = [
            (row, task.result())
            for row, task in zip(newest, tasks, strict=True)
            if not task.cancelled() and task.exception() is None
        ]
        if newest and not fingerprints:
            # Un certificado que falla no pierde el resto, pero si fallan todos algo va mal.
            errors = [t.exception() for t in tasks if not t.cancelled() and t.exception()]
            raise (
                errors[0]
                if errors
                else ModuleError("crt.sh no entregó ningún certificado a tiempo")
            )

        now = datetime.now(UTC)
        out: list[Entity] = []
        names: set[str] = set()
        for row, fingerprint in fingerprints:
            san = sorted(
                {
                    n.strip().lower()
                    for n in str(row.get("name_value", "")).splitlines()
                    if n.strip()
                }
            )
            expires = _date(row.get("not_after"))
            days = (expires - now).days if expires else None
            status = _status(days)
            cert = self.try_emit(
                entity,
                EntityType.CERTIFICATE,
                fingerprint,
                issuer=row.get("issuer_name"),
                common_name=row.get("common_name"),
                serial=row.get("serial_number"),
                not_before=row.get("not_before"),
                not_after=row.get("not_after"),
                san=san,
                expires_in_days=days,
                status=status,
            )
            if cert is None:
                continue
            out.append(cert)
            for name in san:
                try:
                    names.add(canonical_hostname(name.removeprefix("*.")))
                except InvalidEntityValue:
                    continue  # los SAN de un certificado son datos no fiables
        names.discard(domain)
        for name in sorted(names)[:MAX_DOMAINS]:
            data = {"subdomain": True} if name.endswith(f".{domain}") else {}
            found = self.try_emit(entity, EntityType.DOMAIN, name, **data)
            if found:
                out.append(found)
        return out
