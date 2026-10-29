"""Guardia de red: impide que un scan conecte con direcciones privadas o reservadas.

Los nombres que devuelven las fuentes externas (p. ej. subdominios de crt.sh) son datos no
fiables: un subdominio puede resolver a `127.0.0.1`, a una IP de la red local o al servicio de
metadatos de una nube (`169.254.169.254`). Los módulos activos se conectarían desde el equipo
del analista. La guardia resuelve el nombre antes de cada petición y en cada redirección.

Límite conocido: entre la comprobación y la conexión el DNS podría cambiar (*DNS rebinding*).
Fijar la IP resuelta en la conexión queda como mejora futura.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket

import httpx

from osineitor.errors import NetworkGuardError


async def resolve_host(host: str) -> list[str]:
    """Direcciones a las que resuelve `host` con el resolutor del sistema (el mismo de httpx).

    Devuelve una lista vacía si no resuelve; la petición fallará por sí sola con su error.
    """
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return []
    return sorted({str(info[4][0]).split("%")[0] for info in infos})


def is_public(address: str) -> bool:
    """True si la dirección es de Internet; False para privadas, loopback, link-local..."""
    try:
        ip = ipaddress.ip_address(address.split("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


async def ensure_public(url: str) -> None:
    """Lanza `NetworkGuardError` si la URL apunta (o resuelve) a una dirección no pública."""
    host = httpx.URL(url).host
    if not host:
        raise NetworkGuardError("URL sin host")
    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        addresses = await resolve_host(host)
    for address in addresses:
        if not is_public(address):
            raise NetworkGuardError(
                f"{host} apunta a {address}, una dirección no pública "
                "(usa --allow-private si es lo que quieres)"
            )
