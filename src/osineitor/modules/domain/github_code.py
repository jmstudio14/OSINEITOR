"""Menciones de un dominio en código público de GitHub y posibles secretos en ellas (requiere key).

Criterio de la fase 6: **nunca se guarda el valor de un secreto**. Las reglas corren en memoria
sobre el fragmento que devuelve la búsqueda y solo sale su nombre y una huella;
`evidence_body=False` evita que `--evidence` guarde la respuesta original, que trae los fragmentos.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError, ModuleQuota, status_error
from osineitor.modules.domain._util import is_root_domain

API = "https://api.github.com/search/code"
RESULTS = "30"
FINGERPRINT = 16

# Los patrones con grupo `value` separan el secreto del texto que lo rodea. Todas las repeticiones
# están acotadas: los fragmentos son de terceros (ver tests/test_redos.py).
RULES = {
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "github_token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_\w{22,255})"),
    "slack_token": re.compile(r"\bxox[abeoprs]-[A-Za-z0-9-]{10,200}"),
    "google_api_key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]{0,40}PRIVATE KEY-----"),
    "url_credentials": re.compile(r"://[^\s/:@]{1,128}:(?P<value>[^\s/:@]{1,128})@"),
    "assignment": re.compile(
        r"(?i)\b(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?token)\b[\"']?\s{0,3}[:=]"
        r"\s{0,3}[\"']?(?P<value>[^\s\"',;]{6,200})"
    ),
}


def find_secrets(text: str) -> dict[str, str]:
    """{huella: regla} de lo que parece un secreto. La huella es parcial: no permite recuperarlo."""
    found: dict[str, str] = {}
    for rule, pattern in RULES.items():
        for match in pattern.finditer(text):
            value = match.groupdict().get("value") or match[0]
            found[hashlib.sha256(value.encode()).hexdigest()[:FINGERPRINT]] = rule
    return found


class GithubCode(Module):
    name = "github_code"
    description = "Menciones del dominio en código público de GitHub, con reglas de secretos"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.RECORD})
    requires_key = "github"
    canary = "example.com"
    min_interval = 6.0  # la búsqueda de código permite 10 peticiones por minuto

    def accepts(self, entity: Entity) -> bool:
        return is_root_domain(entity)

    def _record(self, entity: Entity, item: dict[str, Any]) -> Entity | None:
        repo = str((item.get("repository") or {}).get("full_name") or "")
        path = str(item.get("path") or "")
        if not repo or not path:
            return None
        secrets: dict[str, str] = {}
        for match in item.get("text_matches") or []:
            if isinstance(match, dict):
                secrets |= find_secrets(str(match.get("fragment") or ""))
        return self.try_emit(
            entity,
            EntityType.RECORD,
            f"github_code:{repo}/{path}",
            repo=repo,
            path=path,
            url=item.get("html_url"),
            rules=sorted(set(secrets.values())),
            fingerprints=sorted(secrets),
        )

    async def run(self, entity: Entity) -> list[Entity]:
        response = await self.ctx.http.get(
            API,
            params={"q": f'"{entity.value}"', "per_page": RESULTS},
            headers={
                "Accept": "application/vnd.github.text-match+json",
                "Authorization": f"Bearer {self.api_key}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            evidence_body=False,
        )
        if response.status_code == 401:
            raise ModuleError("API key de GitHub inválida")
        if response.status_code == 403:
            # GitHub contesta 403, no 429, cuando se agota el límite secundario.
            if "retry-after" in response.headers or (
                response.headers.get("x-ratelimit-remaining") == "0"
            ):
                raise ModuleQuota("api.github.com rechazó la petición por límite de uso")
            raise ModuleError("la key de GitHub no tiene acceso a la búsqueda de código")
        if response.status_code != 200:
            raise status_error("api.github.com", response)
        items = [i for i in response.json().get("items") or [] if isinstance(i, dict)]
        records = (self._record(entity, item) for item in items)
        return [record for record in records if record]
