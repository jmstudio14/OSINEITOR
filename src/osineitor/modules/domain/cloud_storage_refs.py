"""Acceso público de los buckets de S3, GCS y Azure citados en las URLs recogidas (activo).

No se adivinan nombres: solo se comprueba el bucket que ya aparece en una URL. La prueba pide un
listado de una clave como máximo y no guarda su contenido.
"""

from __future__ import annotations

import re
from typing import NamedTuple
from urllib.parse import urlsplit

import httpx

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Context, Module
from osineitor.sanitize import quote_segment

BUCKET = r"[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]"
S3_ENDPOINT = r"s3(?:[.-][a-z0-9-]+){0,2}\.amazonaws\.com"
S3_VIRTUAL = re.compile(rf"^(?P<bucket>{BUCKET})\.(?P<endpoint>{S3_ENDPOINT})$")
S3_PATH = re.compile(rf"^{S3_ENDPOINT}$")
GCS_VIRTUAL = re.compile(rf"^(?P<bucket>{BUCKET})\.storage\.googleapis\.com$")
AZURE = re.compile(r"^(?P<account>[a-z0-9]{3,24})\.blob\.core\.windows\.net$")
NAME = re.compile(rf"^{BUCKET}$")


class Reference(NamedTuple):
    provider: str
    bucket: str  # en Azure, `cuenta/contenedor`
    url: str  # dónde se pide el listado
    params: dict[str, str]


def _first_segment(path: str) -> str:
    segment = path.lstrip("/").split("/", 1)[0].lower()
    return segment if NAME.fullmatch(segment) else ""


def parse_reference(url: str) -> Reference | None:
    """El bucket que cita una URL de almacenamiento en la nube, o `None` si no cita ninguno."""
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
    except ValueError:
        return None
    if parts.scheme not in ("http", "https"):
        return None
    segment = _first_segment(parts.path)
    s3_params = {"list-type": "2", "max-keys": "1"}
    if match := S3_VIRTUAL.match(host):
        bucket, endpoint = match["bucket"], match["endpoint"]
        # Con un punto en el nombre, el certificado comodín de Amazon no vale: va en la ruta.
        target = (
            f"https://{endpoint}/{quote_segment(bucket)}"
            if "." in bucket
            else f"https://{bucket}.{endpoint}/"
        )
        return Reference("s3", bucket, target, s3_params)
    if S3_PATH.match(host) and segment:
        return Reference("s3", segment, f"https://{host}/{quote_segment(segment)}", s3_params)
    gcs_params = {"max-keys": "1"}
    if match := GCS_VIRTUAL.match(host):
        return Reference(
            "gcs",
            match["bucket"],
            f"https://storage.googleapis.com/{quote_segment(match['bucket'])}",
            gcs_params,
        )
    if host == "storage.googleapis.com" and segment:
        return Reference("gcs", segment, f"https://{host}/{quote_segment(segment)}", gcs_params)
    if (match := AZURE.match(host)) and segment:
        return Reference(
            "azure",
            f"{match['account']}/{segment}",
            f"https://{host}/{quote_segment(segment)}",
            {"restype": "container", "comp": "list", "maxresults": "1"},
        )
    return None


def classify_access(provider: str, status: int, body: str) -> str:
    """`public_list`, `denied`, `absent` o `unknown` según la respuesta de cada proveedor."""
    listing = "<EnumerationResults" if provider == "azure" else "<ListBucketResult"
    if status == 200 and listing in body:
        return "public_list"
    if status == 403:
        return "denied"
    if provider == "azure":
        # A un anónimo, Azure le contesta 404 `ResourceNotFound` tanto si el contenedor es privado
        # como si no existe (comprobado en vivo): no se puede afirmar ninguna de las dos cosas.
        return "denied" if status == 409 and "PublicAccessNotPermitted" in body else "unknown"
    return "absent" if status == 404 else "unknown"


class CloudStorageRefs(Module):
    name = "cloud_storage_refs"
    description = "Acceso público de los buckets de S3, GCS y Azure citados en URLs (activo)"
    consumes = frozenset({EntityType.URL})
    produces = frozenset({EntityType.RECORD})
    passive = False
    canary = "https://noaa-gsod-pds.s3.amazonaws.com/"

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx)
        self._seen: set[tuple[str, str]] = set()

    def accepts(self, entity: Entity) -> bool:
        return entity.type == EntityType.URL and parse_reference(entity.value) is not None

    async def run(self, entity: Entity) -> list[Entity]:
        reference = parse_reference(entity.value)
        if reference is None or (reference.provider, reference.bucket) in self._seen:
            return []
        self._seen.add((reference.provider, reference.bucket))
        try:
            response = await self.ctx.http.get(
                reference.url, params=reference.params, follow_redirects=False
            )
        except httpx.ConnectError:
            # Sin DNS: en Azure la cuenta es parte del nombre, así que no existe.
            if reference.provider != "azure":
                raise
            status, access = None, "absent"
        else:
            status = response.status_code
            access = classify_access(reference.provider, status, response.text)
        # La URL de origen no se copia: puede traer un token de acceso en la consulta.
        return [
            self.emit(
                entity,
                EntityType.RECORD,
                f"cloud_storage:{reference.provider}:{reference.bucket}",
                provider=reference.provider,
                bucket=reference.bucket,
                access=access,
                status=status,
            )
        ]
