"""Saldo y actividad de una dirección de Bitcoin (mempool.space)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from osineitor.crypto_address import classify
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, status_error
from osineitor.sanitize import quote_segment

BASE = "https://mempool.space/api/address"
# La primera página de `txs` trae hasta 25 transacciones confirmadas: solo con tantas o menos
# sabemos cuál fue la primera.
PAGE = 25


def _iso(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat().replace("+00:00", "Z")


class BtcExplorer(Module):
    name = "btc_explorer"
    description = "Saldo, nº de transacciones y actividad de una dirección de Bitcoin"
    consumes = frozenset({EntityType.CRYPTO_ADDRESS})
    produces = frozenset({EntityType.RECORD})
    canary = "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq"
    min_interval = 1.0

    def accepts(self, entity: Entity) -> bool:
        found = classify(entity.value)
        return entity.type == EntityType.CRYPTO_ADDRESS and bool(found) and found["chain"] == "btc"

    async def _json(self, path: str) -> Any:
        response = await self.ctx.http.get(f"{BASE}/{path}")
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise status_error("mempool.space", response)
        return response.json()

    async def run(self, entity: Entity) -> list[Entity]:
        address = quote_segment(entity.value)
        info = await self._json(address)
        if not isinstance(info, dict):
            return []
        chain = info.get("chain_stats") or {}
        pool = info.get("mempool_stats") or {}
        received = int(chain.get("funded_txo_sum") or 0)
        spent = int(chain.get("spent_txo_sum") or 0)
        count = int(chain.get("tx_count") or 0)
        times: list[int] = []
        if count:
            txs = await self._json(f"{address}/txs") or []
            times = [
                tx["status"]["block_time"]
                for tx in txs
                if isinstance(tx, dict) and (tx.get("status") or {}).get("block_time")
            ]
        return [
            self.emit(
                entity,
                EntityType.RECORD,
                f"btc:{entity.value}",
                balance_sat=received - spent,
                total_received_sat=received,
                total_sent_sat=spent,
                transactions=count,
                unconfirmed_transactions=int(pool.get("tx_count") or 0),
                last_activity=_iso(max(times)) if times else None,
                first_activity=_iso(min(times)) if times and count <= PAGE else None,
            )
        ]
