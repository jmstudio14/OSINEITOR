"""Cadena y formato de una dirección de criptomoneda (validación local, sin red)."""

from __future__ import annotations

from osineitor.crypto_address import classify
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module

CHAINS = {
    "btc": "Bitcoin",
    "eth": "Ethereum",
    "ltc": "Litecoin",
    "doge": "Dogecoin",
    "xmr": "Monero",
}


class CryptoDetect(Module):
    name = "crypto_detect"
    description = "Cadena y formato de una dirección de criptomoneda; valida la suma (sin red)"
    consumes = frozenset({EntityType.CRYPTO_ADDRESS})
    produces = frozenset({EntityType.RECORD})
    canary = "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq"

    async def run(self, entity: Entity) -> list[Entity]:
        found = classify(entity.value)
        if not found:
            return []
        return [
            self.emit(
                entity,
                EntityType.RECORD,
                f"crypto:{entity.value}",
                chain=found["chain"],
                chain_name=CHAINS[found["chain"]],
                format=found["format"],
                # Ethereum y Monero solo se validan por forma: el resto, por su suma.
                checksum_verified=found["chain"] not in ("eth", "xmr"),
            )
        ]
