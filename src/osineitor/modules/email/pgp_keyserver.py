"""Clave PGP pública asociada al email en keys.openpgp.org (solo identidades verificadas)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import unquote

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, status_error

FINGERPRINT = re.compile(r"^(?:[0-9A-Fa-f]{40}|[0-9A-Fa-f]{64})$")
MAX_IDENTITIES = 10
# Números de algoritmo de clave pública del RFC 4880 / 9580.
ALGORITHMS = {"1": "RSA", "17": "DSA", "18": "ECDH", "19": "ECDSA", "22": "EdDSA"}


def _date(epoch: str) -> str | None:
    try:
        return datetime.fromtimestamp(int(epoch), UTC).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


class PgpKeyserver(Module):
    name = "pgp_keyserver"
    description = "Clave PGP pública del email en keys.openpgp.org (identidades verificadas)"
    consumes = frozenset({EntityType.EMAIL})
    produces = frozenset({EntityType.RECORD})
    canary = "test@example.com"
    # El servidor admite una consulta por email y minuto (con una ráfaga de 50).
    min_interval = 2.0

    async def run(self, entity: Entity) -> list[Entity]:
        response = await self.ctx.http.get(
            "https://keys.openpgp.org/pks/lookup",
            params={"op": "index", "options": "mr", "search": entity.value},
        )
        if response.status_code == 404:  # sin clave, o el dueño no autorizó buscarla por email
            return []
        if response.status_code != 200:
            raise status_error("keys.openpgp.org", response)
        keys: list[Entity] = []
        identities: list[str] = []
        for line in response.text.splitlines():
            fields = line.split(":")
            if fields[0] == "pub" and len(fields) >= 5 and FINGERPRINT.match(fields[1]):
                key = self.try_emit(
                    entity,
                    EntityType.RECORD,
                    f"pgp:{fields[1].upper()}",
                    algorithm=ALGORITHMS.get(fields[2]),
                    bits=int(fields[3]) if fields[3].isdigit() else None,
                    created_at=_date(fields[4]),
                )
                if key:
                    keys.append(key)
                    identities = key.data["identities"] = []
            elif fields[0] == "uid" and keys and len(identities) < MAX_IDENTITIES:
                if uid := unquote(fields[1]).strip():
                    identities.append(uid[:200])
        return keys
