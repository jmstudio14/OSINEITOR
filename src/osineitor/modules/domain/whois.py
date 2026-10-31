"""Datos de registro por WHOIS (puerto 43) para los TLD sin RDAP."""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime
from functools import cache
from importlib import resources

from osineitor.errors import InvalidEntityValue
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Context, Module, ModuleError, ModuleQuota, ModuleSkipped
from osineitor.modules.domain._util import is_root_domain
from osineitor.normalize import canonical_hostname

MAX_BYTES = 64 * 1024
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 15.0
MIN_INTERVAL = 2.0  # segundos entre dos consultas al mismo servidor

# Solo se extraen estos campos: los de titular y contactos nunca se leen (privacidad).
ALIASES = {
    "registrar": ("registrar", "registrar.name", "registrar.organization"),
    "created": ("creation date", "created", "created on", "registered"),
    "expires": ("registry expiry date", "expiration date", "expire date", "expires"),
    "updated": ("updated date", "last update", "last updated on", "changed"),
    "status": ("domain status", "status"),
    "nameservers": ("name server", "nserver", "nameservers", "name servers", "name servers.dns"),
    "dnssec": ("dnssec", "signed"),
}
NOT_REGISTERED = re.compile(
    r"no match|not found|no entries found|no data found|status:\s*(free|available)\b", re.I
)
RATE_LIMITED = re.compile(r"rate limit|too many|quota|limit exceeded|blocked", re.I)
DATE_FORMATS = ("%d/%m/%Y %H:%M:%S", "%a %b %d %Y")


@cache
def servers() -> dict[str, dict[str, str]]:
    path = resources.files(__package__).joinpath("data/whois_servers.json")
    return json.loads(path.read_text(encoding="utf-8"))["servers"]


def parse(text: str) -> dict[str, list[str]]:
    """Texto WHOIS → `{ruta: [valores]}` en minúsculas.

    Las rutas de un bloque llevan el encabezado delante (`registrar.name`); un encabezado puede
    ir sin «:» y sus líneas sin clave cuentan como valores del propio encabezado.
    """
    fields: dict[str, list[str]] = {}
    section: str | None = None
    for raw in text.splitlines():
        body = raw.strip()
        if not body:
            section = None
            continue
        if body[0] in "%*#>":
            continue
        key, sep, value = body.partition(":")
        key, value = key.strip().lower(), value.strip()
        if raw[0] in " \t":
            if section is None:
                continue
            path, val = (f"{section}.{key}", value) if sep else (section, body)
        elif sep and value:
            section, path, val = None, key, value
        else:
            section = key if sep else body.lower()
            continue
        if val:
            fields.setdefault(path, []).append(val)
    return fields


def _date(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        pass
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).isoformat()
        except ValueError:
            continue
    return value


def _values(fields: dict[str, list[str]], names: tuple[str, ...]) -> list[str]:
    return [v for name in names for v in fields.get(name, [])]


def summarize(text: str) -> dict[str, object]:
    """Campos de registro que se emiten; vacío si el texto no trae ninguno reconocible."""
    fields = parse(text)
    pick = {key: _values(fields, names) for key, names in ALIASES.items()}
    nameservers = []
    for value in pick["nameservers"]:
        try:
            host = canonical_hostname(re.split(r"[\s|]", value, maxsplit=1)[0])
        except InvalidEntityValue:
            continue
        if host not in nameservers:
            nameservers.append(host)
    # Los estados EPP traen detrás una URL de ICANN; los demás son texto libre («NOT AVAILABLE»).
    status = list(dict.fromkeys(re.sub(r"\s+https?://\S+$", "", v) for v in pick["status"]))
    dnssec = next(
        (
            v.lower() in {"signed", "signeddelegation", "yes", "true"}
            for v in pick["dnssec"]
            if v.lower() in {"signed", "signeddelegation", "yes", "true", "unsigned", "no", "false"}
        ),
        None,
    )
    found = {
        "registrar": pick["registrar"][0] if pick["registrar"] else None,
        "created": _date(pick["created"][0]) if pick["created"] else None,
        "expires": _date(pick["expires"][0]) if pick["expires"] else None,
        "updated": _date(pick["updated"][0]) if pick["updated"] else None,
        "status": status,
        "nameservers": nameservers,
        "dnssec": dnssec,
    }
    return found if any(v not in (None, []) for v in found.values()) else {}


class Whois(Module):
    name = "whois"
    authority = "authoritative"
    description = "Registrador, fechas, estado y nameservers vía WHOIS para TLD sin RDAP"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.RECORD})
    canary = "google.io"
    # El socket va fuera de `ctx.http`: con --proxy se omite en lugar de filtrar la consulta.
    direct_dns = True
    timeout = 60.0

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx)
        self._lock = asyncio.Lock()
        self._last: dict[str, float] = {}

    def accepts(self, entity: Entity) -> bool:
        return is_root_domain(entity)

    async def _ask(self, server: str, query: str, port: int = 43) -> str:
        """Una consulta, separada de las demás al mismo servidor (no hay presupuesto aquí)."""
        async with self._lock:
            wait = self._last.get(server, 0.0) + MIN_INTERVAL - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(server, port), CONNECT_TIMEOUT
                )
                try:
                    writer.write(f"{query}\r\n".encode())
                    await writer.drain()
                    data = b""
                    while len(data) < MAX_BYTES:
                        chunk = await asyncio.wait_for(reader.read(4096), READ_TIMEOUT)
                        if not chunk:
                            break
                        data += chunk
                finally:
                    writer.close()
            except (OSError, TimeoutError) as exc:
                raise ModuleError(
                    f"el servidor WHOIS {server} no respondió ({type(exc).__name__})"
                ) from exc
            finally:
                self._last[server] = time.monotonic()
        return data[:MAX_BYTES].decode(errors="replace")

    async def run(self, entity: Entity) -> list[Entity]:
        tld = entity.value.rsplit(".", 1)[-1]
        entry = servers().get(tld)
        if entry is None:
            raise ModuleSkipped(
                f"no hay servidor WHOIS configurado para .{tld} "
                "(los TLD con RDAP los cubre el módulo rdap)"
            )
        if "unavailable" in entry:
            raise ModuleSkipped(entry["unavailable"])
        server = entry["server"]
        text = await self._ask(server, entry.get("query", "{domain}").format(domain=entity.value))
        self.record_evidence(f"whois://{server}/{entity.value}", text, method="WHOIS")

        if NOT_REGISTERED.search(text):
            return []
        found = summarize(text)
        if not found:
            if RATE_LIMITED.search(text):
                raise ModuleQuota(f"{server} rechazó la consulta por límite de uso")
            raise ModuleError(f"la respuesta de {server} no trae campos de registro reconocibles")
        return [self.emit(entity, EntityType.RECORD, f"whois:{entity.value}", **found)]
