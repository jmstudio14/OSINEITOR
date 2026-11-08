"""Captura de una URL como evidencia: cuerpo, cabeceras, WARC y pantallazo con huella SHA-256.

La petición principal va por `ctx.http` (guardia de red, presupuesto, proxy y evidencia). El
pantallazo sale de un navegador *headless* opcional (`osineitor[capture]`) que queda fuera de ese
cliente: su red se vigila aparte y, con `--proxy`, no se abre.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from osineitor import netguard
from osineitor.config import data_dir
from osineitor.errors import NetworkGuardError
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module

SAVE_PAGE_NOW = "https://web.archive.org/save"
SCREENSHOT = "screenshot.png"
BROWSER_TIMEOUT = 30_000  # milisegundos
# httpx entrega el cuerpo ya descomprimido: estas cabeceras dejarían de describirlo.
BODY_HEADERS = frozenset({b"content-encoding", b"content-length", b"transfer-encoding"})


def _warc_record(kind: str, at: datetime, content_type: str, block: bytes, **fields: str) -> bytes:
    headers = {
        "WARC-Type": kind,
        "WARC-Record-ID": f"<urn:uuid:{uuid.uuid4()}>",
        "WARC-Date": at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        **{name.replace("_", "-"): value for name, value in fields.items()},
        "WARC-Block-Digest": f"sha256:{hashlib.sha256(block).hexdigest()}",
        "Content-Type": content_type,
        "Content-Length": str(len(block)),
    }
    head = "WARC/1.1\r\n" + "".join(f"{k}: {v}\r\n" for k, v in headers.items()) + "\r\n"
    return head.encode() + block + b"\r\n\r\n"


def to_warc(response: httpx.Response, at: datetime) -> bytes:
    """Fichero WARC 1.1 con la respuesta definitiva, con el cuerpo ya descomprimido."""
    body = response.content
    lines = [f"{response.http_version} {response.status_code} {response.reason_phrase}".encode()]
    lines += [
        name + b": " + value
        for name, value in response.headers.raw
        if name.lower() not in BODY_HEADERS
    ]
    lines.append(b"Content-Length: " + str(len(body)).encode())
    block = b"\r\n".join(lines) + b"\r\n\r\n" + body
    info = b"software: osineitor\r\nformat: WARC File Format 1.1\r\n"
    return _warc_record("warcinfo", at, "application/warc-fields", info) + _warc_record(
        "response",
        at,
        "application/http;msgtype=response",
        block,
        WARC_Target_URI=str(response.url),
        WARC_Payload_Digest=f"sha256:{hashlib.sha256(body).hexdigest()}",
    )


def _write(folder: Path, files: dict[str, bytes]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (folder / name).write_bytes(content)


def _digests(folder: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(folder.iterdir())
    }


class Capture(Module):
    name = "capture"
    description = "Guarda una URL como evidencia: cuerpo, cabeceras, WARC y pantallazo (activo)"
    consumes = frozenset({EntityType.URL})
    produces = frozenset({EntityType.RECORD})
    passive = False
    authority = "authoritative"
    probe_url = "https://example.com"
    timeout = 120.0

    def accepts(self, entity: Entity) -> bool:
        # Solo la URL que pide el usuario: el histórico de Wayback abriría cientos de navegadores.
        return (
            entity.type == EntityType.URL
            and entity.parent is None
            and urlsplit(entity.value).scheme in ("http", "https")
        )

    async def _allowed(self, url: str) -> bool:
        if not self.ctx.http.guarded or urlsplit(url).scheme not in ("http", "https"):
            return True
        try:
            await netguard.ensure_public(url)
        except (NetworkGuardError, httpx.HTTPError):
            return False
        return True

    async def _screenshot(self, url: str, path: Path) -> str | None:
        """Hace el pantallazo; devuelve el motivo si no se ha hecho."""
        if self.ctx.http.proxy:
            return "con --proxy no se abre el navegador: su tráfico no pasaría por el proxy"
        try:
            from playwright.async_api import Error, async_playwright
        except ImportError:
            return "falta Playwright: pip install 'osineitor[capture]'"

        async def guard(route) -> None:
            if await self._allowed(route.request.url):
                await route.continue_()
            else:
                await route.abort()

        # `route` no ve los saltos de una redirección: solo se pueden detectar cuando ya han salido.
        hops: list[asyncio.Task[bool]] = []

        def watch(request) -> None:
            if request.redirected_from is not None:
                hops.append(asyncio.create_task(self._allowed(request.url)))

        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                try:
                    context = await browser.new_context(
                        service_workers="block", user_agent=self.ctx.config.user_agent
                    )
                    page = await context.new_page()
                    page.on("request", watch)
                    await page.route("**/*", guard)
                    await page.goto(url, wait_until="load", timeout=BROWSER_TIMEOUT)
                    if not all(await asyncio.gather(*hops)):
                        return "una redirección del navegador apuntaba a una red no pública"
                    await page.screenshot(path=str(path), full_page=True, timeout=BROWSER_TIMEOUT)
                finally:
                    await browser.close()
        except Error as exc:
            return f"el navegador falló: {str(exc).splitlines()[0][:200]}"
        return None

    async def _save_page_now(self, url: str) -> dict[str, str]:
        """Solo con la key `archive_org`: publica la URL en la Wayback Machine."""
        key = self.ctx.config.key("archive_org")
        if not key:
            return {}
        try:
            response = await self.ctx.http.post(
                SAVE_PAGE_NOW,
                data={"url": url},
                headers={"Accept": "application/json", "Authorization": f"LOW {key}"},
            )
            job = response.json().get("job_id") if response.status_code == 200 else None
        except (httpx.HTTPError, ValueError) as exc:
            return {"save_page_now_error": type(exc).__name__}
        if job:
            return {"save_page_now_job": str(job)}
        return {"save_page_now_error": f"respondió {response.status_code}"}

    async def run(self, entity: Entity) -> list[Entity]:
        response = await self.ctx.http.get(entity.value)
        at = datetime.now(UTC)
        tag = hashlib.sha256(entity.value.encode()).hexdigest()[:12]
        folder = data_dir() / "captures" / f"{at:%Y%m%dT%H%M%SZ}-{tag}"
        content_type = response.headers.get("content-type", "")
        headers = [[k.decode("latin-1"), v.decode("latin-1")] for k, v in response.headers.raw]
        await asyncio.to_thread(
            _write,
            folder,
            {
                "page.html" if "html" in content_type else "body.bin": response.content,
                "headers.json": json.dumps(headers, ensure_ascii=False, indent=1).encode(),
                "capture.warc": to_warc(response, at),
            },
        )
        skipped = await self._screenshot(str(response.url), folder / SCREENSHOT)
        return [
            self.emit(
                entity,
                EntityType.RECORD,
                f"capture:{entity.value}",
                directory=str(folder),
                sha256=await asyncio.to_thread(_digests, folder),
                final_url=str(response.url),
                status=response.status_code,
                content_type=content_type,
                size=len(response.content),
                captured_at=at.isoformat().replace("+00:00", "Z"),
                screenshot_skipped=skipped,
                **await self._save_page_now(str(response.url)),
            )
        ]
