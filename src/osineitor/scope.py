"""Alcance declarado de un scan: qué dominios y redes se pueden investigar.

`--scope scope.yml`:

    domains: [example.com]          # el dominio y sus subdominios
    ips: [203.0.113.0/24, 198.51.100.7]
    exclude: [admin.example.com, 203.0.113.9]

Lo que cae fuera no entra en el resultado ni se investiga más. Una lista ausente no restringe ese
tipo de dato: con solo `domains` se admiten las IPs a las que resuelven esos dominios; para
limitarlas hay que declarar `ips`. Los tipos sin host (`record`, `profile`, `username`, `breach`,
`vulnerability`) heredan el alcance de la entidad de la que salen.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from osineitor.errors import InvalidEntityValue
from osineitor.models import Entity, EntityType
from osineitor.normalize import canonical_hostname

KEYS = ("domains", "ips", "exclude")
Network = ipaddress.IPv4Network | ipaddress.IPv6Network


class ScopeError(ValueError):
    """El fichero de alcance no es válido."""


def _network(text: str) -> Network | None:
    try:
        return ipaddress.ip_network(text, strict=False)
    except ValueError:
        return None


def _in_domain(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == d or host.endswith(f".{d}") for d in domains)


def _host(entity: Entity) -> str | None:
    """Host que decide el alcance de la entidad, o `None` si no tiene (hereda)."""
    match entity.type:
        case EntityType.DOMAIN | EntityType.IP:
            return entity.value
        case EntityType.EMAIL:
            return entity.value.rpartition("@")[2]
        case EntityType.URL:
            return urlsplit(entity.value).hostname
        case EntityType.SERVICE:  # `host:puerto`; el puerto va siempre al final
            return entity.value.rpartition(":")[0].strip("[]")
    return None


def _hostname(key: str, item: str) -> str:
    try:
        return canonical_hostname(item.removeprefix("*."))
    except InvalidEntityValue as exc:
        raise ScopeError(f"`{key}`: {exc}") from exc


@dataclass(frozen=True)
class Scope:
    domains: tuple[str, ...] = ()
    networks: tuple[Network, ...] = ()
    exclude_domains: tuple[str, ...] = ()
    exclude_networks: tuple[Network, ...] = ()

    @classmethod
    def parse(cls, raw: Any) -> Scope:
        if not isinstance(raw, dict):
            raise ScopeError("el alcance debe ser un mapa con `domains`, `ips` y/o `exclude`")
        if unknown := set(raw) - set(KEYS):
            raise ScopeError(f"claves desconocidas: {', '.join(sorted(map(str, unknown)))}")
        lists: dict[str, list[str]] = {}
        for key in KEYS:
            value = raw.get(key)
            if value is None:
                continue
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ScopeError(f"`{key}` debe ser una lista de textos")
            lists[key] = [v.strip() for v in value]
        if not (lists.get("domains") or lists.get("ips")):
            raise ScopeError("declara al menos `domains` o `ips` (no pueden estar vacíos)")

        networks = []
        for item in lists.get("ips", []):
            if (net := _network(item)) is None:
                raise ScopeError(f"`ips`: {item!r} no es una IP ni una red CIDR")
            networks.append(net)
        exclude_networks, exclude_domains = [], []
        for item in lists.get("exclude", []):
            if (net := _network(item)) is not None:
                exclude_networks.append(net)
            else:
                exclude_domains.append(_hostname("exclude", item))
        return cls(
            tuple(_hostname("domains", d) for d in lists.get("domains", [])),
            tuple(networks),
            tuple(exclude_domains),
            tuple(exclude_networks),
        )

    @classmethod
    def from_file(cls, path: Path) -> Scope:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ScopeError(f"no se puede leer {path}: {exc.strerror or exc}") from exc
        except (yaml.YAMLError, UnicodeDecodeError) as exc:
            raise ScopeError(f"{path} no es un YAML válido: {exc}") from exc
        return cls.parse(raw)

    def allows(self, entity: Entity) -> bool:
        host = _host(entity)
        if host is None:
            return True
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            host = host.lower().rstrip(".")
            if _in_domain(host, self.exclude_domains):
                return False
            return not self.domains or _in_domain(host, self.domains)
        if any(ip in net for net in self.exclude_networks):
            return False
        return not self.networks or any(ip in net for net in self.networks)

    def to_dict(self) -> dict[str, list[str]]:
        """Forma normalizada, la que se guarda y se muestra."""
        out = {
            "domains": list(self.domains),
            "ips": [str(n) for n in self.networks],
            "exclude": [*self.exclude_domains, *(str(n) for n in self.exclude_networks)],
        }
        return {k: v for k, v in out.items() if v}
