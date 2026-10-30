"""Evidencias: huella de la respuesta original de cada fuente y su comprobación posterior."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from urllib.parse import unquote

from osineitor.cache import MAX_BODY
from osineitor.logs import MASK
from osineitor.models import Evidence, ScanResult, digest

# Parámetros de consulta que llevan una API key; su valor nunca se guarda.
SECRET_PARAMS = frozenset({"api_key", "apikey", "key", "token", "access_token", "auth"})


def sanitize_url(url: str, secrets: tuple[str, ...] | list[str] = ()) -> str:
    """La URL consultada sin credenciales ni keys, conservando el resto de la consulta exacta."""
    url = url.split("#", 1)[0]
    base, sep, query = url.partition("?")
    scheme, scheme_sep, rest = base.partition("://")
    if scheme_sep:
        authority, slash, path = rest.partition("/")
        base = f"{scheme}://{authority.rpartition('@')[2]}{slash}{path}"
    pairs = []
    for pair in query.split("&") if sep else []:
        name, eq, _ = pair.partition("=")
        pairs.append(f"{name}={MASK}" if eq and unquote(name).lower() in SECRET_PARAMS else pair)
    out = base + (sep + "&".join(pairs) if sep else "")
    for secret in secrets:
        out = out.replace(secret, MASK)
    return out


def capture(
    kind: str,
    url: str,
    body: bytes,
    *,
    method: str,
    status: int | None = None,
    secrets: tuple[str, ...] | list[str] = (),
) -> Evidence:
    """Huella de `body`; si supera `MAX_BODY` se guarda recortado y se marca."""
    stored = body[:MAX_BODY]
    return Evidence(
        kind=kind,
        url=sanitize_url(url, secrets),
        method=method,
        status=status,
        sha256=hashlib.sha256(stored).hexdigest(),
        size=len(body),
        truncated=len(stored) < len(body),
        body=stored,
    )


@dataclass
class Verification:
    scan_id: int | None
    checked: int
    mismatches: list[dict] = field(default_factory=list)
    evidence_digest: str | None = None  # recalculada a partir de los cuerpos guardados
    digest_match: bool | None = None  # None si no se pidió comparar

    @property
    def ok(self) -> bool:
        return not self.mismatches and self.digest_match is not False


def verify(result: ScanResult, expected_digest: str | None = None) -> Verification:
    """Recalcula la huella de cada cuerpo y la compara con la guardada."""
    actual = [hashlib.sha256(e.body).hexdigest() for e in result.evidence]
    mismatches = []
    for number, (e, now) in enumerate(zip(result.evidence, actual, strict=True), start=1):
        resized = not e.truncated and len(e.body) != e.size
        if now != e.sha256 or resized:
            mismatches.append(
                {
                    "number": number,
                    "module": e.module,
                    "entity": e.entity,
                    "url": e.url,
                    "expected": e.sha256,
                    "actual": now,
                }
            )
    recomputed = digest(actual) if actual else None
    match = None
    if expected_digest is not None:
        match = recomputed is not None and recomputed == expected_digest.strip().lower()
    return Verification(result.scan_id, len(actual), mismatches, recomputed, match)
