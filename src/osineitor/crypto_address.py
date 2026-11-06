"""Reconocimiento local de direcciones de criptomonedas: formato y suma de comprobación.

No importa `osineitor.models` (lo usa `detect_type`). Sin red.
"""

from __future__ import annotations

import hashlib
import re

BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BECH32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
ETH_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
XMR_RE = re.compile(r"^[48][1-9A-HJ-NP-Za-km-z]{94}$")
# Prefijo de versión → (cadena, tipo). Dirección base58check de 25 bytes.
BASE58_VERSIONS = {
    0x00: ("btc", "p2pkh"),
    0x05: ("btc", "p2sh"),
    0x30: ("ltc", "p2pkh"),
    0x32: ("ltc", "p2sh"),
    0x1E: ("doge", "p2pkh"),
}
BECH32_HRP = {"bc": "btc", "ltc": "ltc"}


def _base58check(address: str) -> bytes | None:
    number = 0
    for char in address:
        index = BASE58.find(char)
        if index < 0:
            return None
        number = number * 58 + index
    raw = number.to_bytes(25, "big") if number < 1 << 200 else b""
    # Los ceros a la izquierda se codifican como «1»: una dirección válida mide 25 bytes.
    leading = len(address) - len(address.lstrip("1"))
    if len(raw) != 25 or raw[:leading] != b"\x00" * leading:
        return None
    check = hashlib.sha256(hashlib.sha256(raw[:21]).digest()).digest()[:4]
    return raw if check == raw[21:] else None


def _polymod(values: list[int]) -> int:
    generator = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
    check = 1
    for value in values:
        top = check >> 25
        check = (check & 0x1FFFFFF) << 5 ^ value
        for i in range(5):
            check ^= generator[i] if (top >> i) & 1 else 0
    return check


def _bech32(address: str) -> tuple[str, int] | None:
    """(hrp, versión del testigo) si la suma de comprobación de bech32 o bech32m es correcta."""
    if address != address.lower() and address != address.upper():
        return None
    address = address.lower()
    position = address.rfind("1")
    if position < 1 or position + 7 > len(address) or len(address) > 90:
        return None
    hrp, data = address[:position], address[position + 1 :]
    if any(char not in BECH32 for char in data):
        return None
    values = [BECH32.index(char) for char in data]
    expanded = [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]
    constant = _polymod(expanded + values)
    witness = values[0]
    if (witness == 0 and constant == 1) or (witness != 0 and constant == 0x2BC830A3):
        return hrp, witness
    return None


def classify(address: str) -> dict[str, str] | None:
    """`{"chain", "format"}` si la dirección es válida en alguna cadena conocida, o `None`.

    Bitcoin, Litecoin y Dogecoin se validan con su suma de comprobación. Ethereum solo por forma
    (la suma de comprobación EIP-55 pide Keccak-256, que no está en la biblioteca estándar) y
    Monero por forma y longitud.
    """
    address = address.strip()
    if ETH_RE.fullmatch(address):
        return {"chain": "eth", "format": "hex"}
    if XMR_RE.fullmatch(address):
        return {"chain": "xmr", "format": "standard"}
    if bech := _bech32(address):
        chain = BECH32_HRP.get(bech[0])
        if chain:
            return {"chain": chain, "format": "bech32" if bech[1] == 0 else "bech32m"}
        return None
    if raw := _base58check(address):
        known = BASE58_VERSIONS.get(raw[0])
        if known:
            return {"chain": known[0], "format": known[1]}
    return None
