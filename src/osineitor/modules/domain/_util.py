from __future__ import annotations

from urllib.parse import urlsplit

from osineitor.models import Entity, EntityType

DOCUMENT_EXTENSIONS = (".pdf", ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp")


def is_root_domain(entity: Entity) -> bool:
    """True para el dominio investigado; False para subdominios descubiertos.

    Evita relanzar búsquedas de subdominios/histórico sobre cada subdominio al pivotear.
    """
    return entity.type == EntityType.DOMAIN and not entity.data.get("subdomain")


def is_document_url(url: str) -> bool:
    """True si la ruta de la URL acaba en una extensión de documento con metadatos que leer."""
    return urlsplit(url).path.lower().endswith(DOCUMENT_EXTENSIONS)


def in_domain(host: str, domain: str) -> bool:
    """True si `host` es `domain` o un subdominio suyo (un host ajeno no es del objetivo)."""
    return host == domain or host.endswith(f".{domain}")
