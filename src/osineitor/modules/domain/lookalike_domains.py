"""Dominios parecidos al propio (typosquatting y homógrafos) ya registrados, por DNS.

Es una comprobación **defensiva** del dominio investigado. Deja un único `record`: no emite
`domain`, porque un dominio parecido puede ser hostil y, como entidad, se pivotaría contra él.
"""

from __future__ import annotations

import asyncio
from itertools import zip_longest

import dns.exception
import dns.resolver

from osineitor.errors import InvalidEntityValue
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError
from osineitor.modules.domain._util import is_root_domain
from osineitor.normalize import canonical_hostname

MAX_CANDIDATES = 300
CONCURRENCY = 20
TLDS = ("com", "net", "org", "co", "io", "info", "biz", "es", "app", "online")
KEYBOARD = {
    **dict.fromkeys("1", "2q"),
    "2": "13qw",
    "3": "24we",
    "4": "35er",
    "5": "46rt",
    "6": "57ty",
    "7": "68yu",
    "8": "79ui",
    "9": "80io",
    "0": "9op",
    "q": "12wa",
    "w": "23qes",
    "e": "34wrd",
    "r": "45etf",
    "t": "56ryg",
    "y": "67tuh",
    "u": "78yij",
    "i": "89uok",
    "o": "90ipl",
    "p": "0ol",
    "a": "qwsz",
    "s": "awedxz",
    "d": "serfcx",
    "f": "drtgvc",
    "g": "ftyhbv",
    "h": "gyujnb",
    "j": "huikmn",
    "k": "jiolm",
    "l": "kop",
    "z": "asx",
    "x": "zsdc",
    "c": "xdfv",
    "v": "cfgb",
    "b": "vghn",
    "n": "bhjm",
    "m": "njk",
}
# Caracteres que se confunden a simple vista; los cirílicos acaban como punycode.
HOMOGLYPHS = {
    "o": ("0", "о"),
    "l": ("1", "i"),
    "i": ("1", "l", "і"),
    "a": ("а",),
    "e": ("е",),
    "c": ("с",),
    "p": ("р",),
    "m": ("rn",),
    "w": ("vv",),
    "d": ("cl",),
}


def _valid(label: str) -> bool:
    return bool(label) and not label.startswith("-") and not label.endswith("-") and len(label) < 64


def permutations(domain: str) -> dict[str, str]:
    """Candidatos `{dominio: técnica}` a partir de un dominio registrable, como mucho 300.

    Se reparten las técnicas por turnos para que el tope no deje fuera a ninguna.
    """
    label, _, suffix = domain.partition(".")
    kinds: dict[str, set[str]] = {
        k: set()
        for k in ("omisión", "repetición", "transposición", "teclado", "homógrafo", "guion", "tld")
    }
    for i, ch in enumerate(label):
        kinds["omisión"].add(label[:i] + label[i + 1 :])
        kinds["repetición"].add(label[:i] + ch + label[i:])
        if i + 1 < len(label):
            kinds["transposición"].add(label[:i] + label[i + 1] + ch + label[i + 2 :])
            kinds["guion"].add(label[: i + 1] + "-" + label[i + 1 :])
        for near in KEYBOARD.get(ch, ""):
            kinds["teclado"].add(label[:i] + near + label[i + 1 :])
        for glyph in HOMOGLYPHS.get(ch, ()):
            kinds["homógrafo"].add(label[:i] + glyph + label[i + 1 :])
    found: dict[str, list[str]] = {}
    for kind, labels in kinds.items():
        names = []
        for item in sorted(labels):
            if item == label or not _valid(item):
                continue
            try:
                names.append(canonical_hostname(f"{item}.{suffix}"))
            except InvalidEntityValue:
                continue
        found[kind] = names
    found["tld"] = [f"{label}.{tld}" for tld in TLDS if f"{label}.{tld}" != domain]

    out: dict[str, str] = {}
    for row in zip_longest(*found.values()):
        for kind, name in zip(found, row, strict=True):
            if name and name != domain and name not in out and len(out) < MAX_CANDIDATES:
                out[name] = kind
    return out


class LookalikeDomains(Module):
    name = "lookalike_domains"
    description = "Dominios parecidos al propio (typosquatting, homógrafos) ya registrados"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.RECORD})
    direct_dns = True
    canary = "example.com"
    timeout = 300.0

    def accepts(self, entity: Entity) -> bool:
        return is_root_domain(entity)

    async def _lookup(self, name: str, rtype: str) -> list[str] | None:
        """Valores del registro; `[]` si no existe, `None` si el resolvedor no respondió."""
        try:
            answer = await self.ctx.resolver.resolve(name, rtype, lifetime=5)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return []
        except (dns.resolver.NoNameservers, dns.exception.Timeout):
            return None
        return sorted(rdata.to_text().rstrip(".").lower() for rdata in answer)

    async def _check(self, name: str, kind: str, gate: asyncio.Semaphore) -> dict | None | bool:
        async with gate:
            ns = await self._lookup(name, "NS")
            if ns is None:
                return False
            if not ns:
                return None  # sin NS: el nombre no está delegado, es decir, no está registrado
            a = await self._lookup(name, "A") or []
            aaaa = await self._lookup(name, "AAAA") or []
            mx = await self._lookup(name, "MX") or []
        item: dict[str, object] = {"domain": name, "technique": kind, "ns": ns}
        if a or aaaa:
            item["a"] = a + aaaa
        if mx:
            item["mx"] = mx
        return item

    async def run(self, entity: Entity) -> list[Entity]:
        candidates = permutations(entity.value)
        gate = asyncio.Semaphore(CONCURRENCY)
        results = await asyncio.gather(
            *(self._check(name, kind, gate) for name, kind in candidates.items())
        )
        unknown = sum(1 for r in results if r is False)
        if candidates and unknown == len(results):
            raise ModuleError("el resolvedor DNS no respondió a ninguna consulta")
        registered = sorted((r for r in results if isinstance(r, dict)), key=lambda r: r["domain"])
        for item in registered:
            self.record_evidence(f"dns://{item['domain']}/NS", "\n".join(item["ns"]))
        if not registered:
            return []
        return [
            self.emit(
                entity,
                EntityType.RECORD,
                f"lookalike:{entity.value}",
                registered=registered,
                with_mx=sum(1 for r in registered if r.get("mx")),
                checked=len(candidates),
                unanswered=unknown,
            )
        ]
