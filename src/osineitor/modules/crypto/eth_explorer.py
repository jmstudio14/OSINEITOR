"""Saldo y actividad de una dirección de Ethereum (Etherscan API V2, requiere key gratuita).

Las etiquetas públicas (`getaddresstag`) solo están en el plan Pro Plus: no se piden.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from osineitor.crypto_address import classify
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError, ModuleQuota, status_error

API = "https://api.etherscan.io/v2/api"
MAINNET = "1"
WEI = Decimal(10) ** 18


class EthExplorer(Module):
    name = "eth_explorer"
    description = "Saldo y primera y última actividad de una dirección de Ethereum (Etherscan)"
    consumes = frozenset({EntityType.CRYPTO_ADDRESS})
    produces = frozenset({EntityType.RECORD})
    requires_key = "etherscan"
    canary = "0xde0b295669a9fd93d5f28d9ec85e40f4cb697bae"
    min_interval = 0.34  # plan gratuito: 3 peticiones por segundo

    def accepts(self, entity: Entity) -> bool:
        found = classify(entity.value)
        return entity.type == EntityType.CRYPTO_ADDRESS and bool(found) and found["chain"] == "eth"

    async def _call(self, address: str, action: str, **params: str) -> Any:
        response = await self.ctx.http.get(
            API,
            params={
                "chainid": MAINNET,
                "module": "account",
                "action": action,
                "address": address,
                "apikey": self.api_key or "",
                **params,
            },
        )
        if response.status_code != 200:
            raise status_error("api.etherscan.io", response)
        body = response.json()
        if str(body.get("status")) == "1":
            return body.get("result")
        message = str(body.get("message") or "")
        if message.startswith("No transactions found"):
            return []
        detail = str(body.get("result") or message)[:200]
        if "rate limit" in detail.lower():
            raise ModuleQuota(f"api.etherscan.io rechazó la petición por límite de uso: {detail}")
        raise ModuleError(f"api.etherscan.io respondió: {detail}")

    async def _activity(self, address: str, sort: str) -> str | None:
        txs = await self._call(address, "txlist", sort=sort, page="1", offset="1")
        if not txs or not isinstance(txs, list) or not str(txs[0].get("timeStamp", "")).isdigit():
            return None
        moment = datetime.fromtimestamp(int(txs[0]["timeStamp"]), tz=UTC)
        return moment.isoformat().replace("+00:00", "Z")

    async def run(self, entity: Entity) -> list[Entity]:
        wei = str(await self._call(entity.value, "balance", tag="latest"))
        if not wei.isdigit():
            raise ModuleError("api.etherscan.io devolvió un saldo que no es un número")
        return [
            self.emit(
                entity,
                EntityType.RECORD,
                f"eth:{entity.value}",
                balance_wei=wei,
                balance_eth=format(Decimal(wei) / WEI, "f"),
                first_activity=await self._activity(entity.value, "asc"),
                last_activity=await self._activity(entity.value, "desc"),
            )
        ]
