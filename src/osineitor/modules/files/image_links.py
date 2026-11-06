"""Enlaces de búsqueda inversa de una imagen por URL (sin red y sin subir nada)."""

from __future__ import annotations

from urllib.parse import quote, urlsplit

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")
ENGINES = {
    "google_lens": "https://lens.google.com/uploadbyurl?url={}",
    "yandex": "https://yandex.com/images/search?rpt=imageview&url={}",
    "tineye": "https://tineye.com/search?url={}",
    "bing": "https://www.bing.com/images/search?view=detailv2&iss=sbi&q=imgurl:{}",
}


class ImageLinks(Module):
    name = "image_links"
    description = "Enlaces de búsqueda inversa de imágenes (Google Lens, Yandex, TinEye, Bing)"
    consumes = frozenset({EntityType.URL})
    produces = frozenset({EntityType.RECORD})
    canary = "https://example.com/foto.jpg"

    def accepts(self, entity: Entity) -> bool:
        return entity.type == EntityType.URL and urlsplit(entity.value).path.lower().endswith(
            IMAGE_EXTENSIONS
        )

    async def run(self, entity: Entity) -> list[Entity]:
        encoded = quote(entity.value, safe="")
        return [
            self.emit(
                entity,
                EntityType.RECORD,
                f"image_links:{entity.value}",
                **{name: template.format(encoded) for name, template in ENGINES.items()},
            )
        ]
