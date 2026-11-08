"""Guardia de red: impide que un scan conecte con direcciones privadas o reservadas.

Los nombres que devuelven las fuentes externas (p. ej. subdominios de crt.sh) son datos no
fiables: un subdominio puede resolver a `127.0.0.1`, a una IP de la red local o al servicio de
metadatos de una nube (`169.254.169.254`). Los módulos activos se conectarían desde el equipo
del analista. La guardia resuelve el nombre antes de cada petición y en cada redirección.

Límite conocido: entre la comprobación y la conexión el DNS podría cambiar (*DNS rebinding*).
Un nombre que no resuelve se bloquea; fijar la IP resuelta en la conexión queda como mejora
futura.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket

import httpx

from osineitor.errors import NetworkGuardError


async def resolve_host(host: str) -> list[str]:
    """Direcciones a las que resuelve `host` con el resolutor del sistema (el mismo de httpx).

    Devuelve una lista vacía si no resuelve.
    """
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return []
    return sorted({str(info[4][0]).split("%")[0] for info in infos})


# IPv6 que llevan una IPv4 en sus 32 bits bajos: IPv4-compatible, SIIT y NAT64 (RFC 6052).
EMBEDDED_IPV4 = tuple(ipaddress.ip_network(n) for n in ("::/96", "::ffff:0:0:0/96", "64:ff9b::/96"))


def is_public(address: str) -> bool:
    """True si la dirección es de Internet; False para privadas, loopback, link-local..."""
    try:
        ip = ipaddress.ip_address(address.split("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.is_site_local:  # fec0::/10: obsoleta, pero sigue siendo red local
            return False
        if ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        elif any(ip in network for network in EMBEDDED_IPV4):
            ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return ip.is_global and not ip.is_multicast


async def ensure_public(url: str, *, resolve: bool = True) -> None:
    """Lanza `NetworkGuardError` si la URL apunta (o resuelve) a una dirección no pública.

    Si el nombre no resuelve, lanza `httpx.ConnectError` (lo mismo que daría httpx) sin dejar
    pasar la petición: httpx lo resolvería otra vez y podría obtener otra IP (*DNS rebinding*).

    Con `resolve=False` (hay un proxy) los nombres no se resuelven aquí: lo haría el DNS local y
    filtraría cada host consultado. Solo se comprueban las IP literales.
    """
    host = httpx.URL(url).host
    if not host:
        raise NetworkGuardError("URL sin host")
    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        if not resolve:
            return
        addresses = await resolve_host(host)
        if not addresses:
            raise httpx.ConnectError(f"{host} no resuelve") from None
    for address in addresses:
        if not is_public(address):
            raise NetworkGuardError(
                f"{host} apunta a {address}, una dirección no pública "
                "(usa --allow-private si es lo que quieres)"
            )
