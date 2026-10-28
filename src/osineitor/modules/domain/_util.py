from __future__ import annotations

from osineitor.models import Entity, EntityType


def is_root_domain(entity: Entity) -> bool:
    """True para el dominio investigado; False para subdominios descubiertos.

    Evita relanzar búsquedas de subdominios/histórico sobre cada subdominio al pivotear.
    """
    return entity.type == EntityType.DOMAIN and not entity.data.get("subdomain")
