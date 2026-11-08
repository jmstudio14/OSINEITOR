"""Fase 6: `capture`, `doc_harvest`, `cloud_storage_refs` y `ext_exiftool`, sin red real."""

from __future__ import annotations

import hashlib
import http.server
import json
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from osineitor import netguard
from osineitor.cli import app
from osineitor.config import Config
from osineitor.http import HttpClient
from osineitor.models import Entity, EntityType
from osineitor.modules._external import find_executable
from osineitor.modules.base import Context, ModuleError, ModuleSkipped
from osineitor.modules.domain.capture import Capture, to_warc
from osineitor.modules.domain.cloud_storage_refs import (
    CloudStorageRefs,
    classify_access,
    parse_reference,
)
from osineitor.modules.domain.doc_harvest import DocHarvest
from osineitor.modules.files.ext_exiftool import ExtExifTool
from tests.modules.test_f6_local import exif_jpeg
from tests.test_cli import use_modules

runner = CliRunner()
URL = "https://example.com/pagina"
HTML = b"<html><title>Prueba</title></html>"


def url_entity(value: str = URL, **data) -> Entity:
    return Entity(type=EntityType.URL, value=value, data=data)


@pytest.fixture
def no_browser(monkeypatch):
    """Sin Playwright, aunque esté instalado: los tests no abren un navegador."""
    monkeypatch.setitem(sys.modules, "playwright.async_api", None)


# --- capture ---------------------------------------------------------------------------------


def test_capture_only_takes_the_url_the_user_asked_for(ctx):
    module = Capture(ctx)
    assert module.accepts(url_entity())
    assert not module.accepts(url_entity().model_copy(update={"parent": "domain:example.com"}))
    assert not module.accepts(url_entity("ftp://example.com/x"))
    assert not Capture.passive


@respx.mock
async def test_capture_saves_files_with_their_hash(ctx, no_browser):
    respx.get(URL).mock(
        return_value=httpx.Response(200, content=HTML, headers={"content-type": "text/html"})
    )
    [record] = await Capture(ctx).run(url_entity())
    folder = Path(record.data["directory"])
    assert (folder / "page.html").read_bytes() == HTML
    assert set(record.data["sha256"]) == {"page.html", "headers.json", "capture.warc"}
    for name, expected in record.data["sha256"].items():
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == expected
    assert ["content-type", "text/html"] in json.loads((folder / "headers.json").read_text())
    assert record.data["final_url"] == URL
    assert "Playwright" in record.data["screenshot_skipped"]


@respx.mock
async def test_capture_of_something_else_is_not_saved_as_html(ctx, no_browser):
    respx.get(URL).mock(return_value=httpx.Response(200, content=b"\x00binario"))
    [record] = await Capture(ctx).run(url_entity())
    assert "body.bin" in record.data["sha256"]


def parse_warc(data: bytes) -> list[tuple[dict[str, str], bytes]]:
    records = []
    while data:
        head, _, rest = data.partition(b"\r\n\r\n")
        lines = head.decode().split("\r\n")
        assert lines[0] == "WARC/1.1"
        fields = dict(line.split(": ", 1) for line in lines[1:])
        length = int(fields["Content-Length"])
        block, tail = rest[:length], rest[length:]
        assert tail.startswith(b"\r\n\r\n")
        records.append((fields, block))
        data = tail[4:]
    return records


def test_warc_describes_the_body_it_contains():
    request = httpx.Request("GET", URL)
    response = httpx.Response(
        200,
        content=HTML,
        request=request,
        headers={"content-type": "text/html", "content-length": "9999", "X-Prueba": "1"},
    )
    (info, _), (fields, block) = parse_warc(to_warc(response, datetime(2026, 1, 2, tzinfo=UTC)))
    assert info["WARC-Type"] == "warcinfo"
    assert fields["WARC-Type"] == "response"
    assert fields["WARC-Target-URI"] == URL
    assert fields["WARC-Date"] == "2026-01-02T00:00:00Z"
    assert fields["WARC-Block-Digest"] == f"sha256:{hashlib.sha256(block).hexdigest()}"
    assert fields["WARC-Payload-Digest"] == f"sha256:{hashlib.sha256(HTML).hexdigest()}"
    head, body = block.split(b"\r\n\r\n", 1)
    assert body == HTML
    assert head.startswith(b"HTTP/1.1 200 OK\r\n")
    assert b"x-prueba: 1" in head.lower()
    assert f"content-length: {len(HTML)}".encode() in head.lower()  # no el 9999 de origen
    assert b"9999" not in head


@respx.mock
async def test_capture_does_not_open_the_browser_behind_a_proxy(config, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("no debe abrir el navegador")

    monkeypatch.setattr(Capture, "_allowed", fail)
    respx.get(URL).mock(return_value=httpx.Response(200, content=HTML))
    async with HttpClient(config, proxy="http://127.0.0.1:9") as http:
        monkeypatch.setattr(netguard, "ensure_public", _allow_all)
        [record] = await Capture(Context(config=config, http=http)).run(url_entity())
    assert "--proxy" in record.data["screenshot_skipped"]


async def _allow_all(url, *, resolve=True):
    return None


@respx.mock
async def test_save_page_now_needs_its_own_key(ctx, no_browser):
    respx.get(URL).mock(return_value=httpx.Response(200, content=HTML))
    save = respx.post("https://web.archive.org/save").mock(return_value=httpx.Response(200))
    [record] = await Capture(ctx).run(url_entity())
    assert not save.called
    assert "save_page_now_job" not in record.data


@respx.mock
async def test_save_page_now_with_key_returns_the_job(no_browser):
    config = Config(keys={"archive_org": "clave:secreto"})
    respx.get(URL).mock(return_value=httpx.Response(200, content=HTML))
    save = respx.post("https://web.archive.org/save").mock(
        return_value=httpx.Response(200, json={"url": URL, "job_id": "ac58789b"})
    )
    async with HttpClient(config, backoff=0) as http:
        [record] = await Capture(Context(config=config, http=http)).run(url_entity())
    assert record.data["save_page_now_job"] == "ac58789b"
    assert save.calls.last.request.headers["authorization"] == "LOW clave:secreto"


@respx.mock
async def test_a_failed_save_page_now_does_not_lose_the_capture(no_browser):
    config = Config(keys={"archive_org": "clave:secreto"})
    respx.get(URL).mock(return_value=httpx.Response(200, content=HTML))
    respx.post("https://web.archive.org/save").mock(return_value=httpx.Response(401, text="no"))
    async with HttpClient(config, backoff=0) as http:
        [record] = await Capture(Context(config=config, http=http)).run(url_entity())
    assert record.data["save_page_now_error"] == "respondió 401"
    assert record.data["sha256"]
    assert "save_page_now_job" not in record.data


def _capture_scan(monkeypatch, db: Path) -> dict:
    use_modules(monkeypatch, [Capture])
    monkeypatch.setitem(sys.modules, "playwright.async_api", None)
    with respx.mock:
        respx.get(URL).mock(
            return_value=httpx.Response(200, content=HTML, headers={"content-type": "text/html"})
        )
        result = runner.invoke(app, ["scan", URL, "--active", "--db", str(db), "--json"])
    assert result.exit_code == 0, result.output
    entities = json.loads(result.output)["entities"]
    return next(e for e in entities if e["value"].startswith("capture:"))


def test_verify_detects_a_changed_or_missing_capture(monkeypatch, tmp_path):
    """Criterio de la fase 6: una captura se puede comprobar con `osineitor verify`."""
    db = tmp_path / "scans.sqlite"
    record = _capture_scan(monkeypatch, db)
    page = Path(record["data"]["directory"]) / "page.html"

    good = runner.invoke(app, ["verify", "1", "--db", str(db), "--json"])
    assert good.exit_code == 0, good.output
    assert json.loads(good.output)["checked"] == 3

    page.write_bytes(HTML + b"!")
    changed = runner.invoke(app, ["verify", "1", "--db", str(db), "--json"])
    assert changed.exit_code == 5
    [mismatch] = json.loads(changed.output)["mismatches"]
    assert mismatch["module"] == "capture"
    assert mismatch["url"] == str(page)
    assert mismatch["expected"] == record["data"]["sha256"]["page.html"]

    page.unlink()
    missing = runner.invoke(app, ["verify", "1", "--db", str(db), "--json"])
    assert missing.exit_code == 5
    assert json.loads(missing.output)["mismatches"][0]["actual"] == "ausente"


def test_capture_reports_export_with_its_data(monkeypatch, tmp_path):
    db = tmp_path / "scans.sqlite"
    _capture_scan(monkeypatch, db)
    for fmt in ("html", "md", "json", "csv"):
        out = tmp_path / f"informe.{fmt}"
        result = runner.invoke(app, ["export", "1", "-f", fmt, "--db", str(db), "-o", str(out)])
        assert result.exit_code == 0, result.output
        assert "capture:" in out.read_text(encoding="utf-8")


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{self.server.server_address[1]}/x")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(HTML)

    def log_message(self, *args):
        pass


@pytest.fixture
def web_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


async def test_browser_takes_a_real_screenshot(web_server, config):
    pytest.importorskip("playwright")
    url = f"http://127.0.0.1:{web_server}/"
    async with HttpClient(config, allow_private=True) as http_client:
        [record] = await Capture(Context(config=config, http=http_client)).run(url_entity(url))
    if record.data.get("screenshot_skipped"):
        pytest.skip(record.data["screenshot_skipped"])  # Playwright sin Chromium descargado
    shot = Path(record.data["directory"]) / "screenshot.png"
    assert shot.read_bytes().startswith(b"\x89PNG")
    assert "screenshot.png" in record.data["sha256"]


async def test_browser_refuses_a_private_address_when_guarded(web_server, config, tmp_path):
    pytest.importorskip("playwright")
    async with HttpClient(config, allow_private=True) as http_client:
        module = Capture(Context(config=config, http=http_client))
        module.ctx.http._guard = True  # solo el navegador: la petición principal no pasa por aquí
        reason = await module._screenshot(f"http://127.0.0.1:{web_server}/", tmp_path / "s.png")
    assert reason is not None
    assert not (tmp_path / "s.png").exists()


async def test_browser_discards_the_screenshot_after_a_redirect_to_a_private_address(
    web_server, config, tmp_path, monkeypatch
):
    """`route` no ve el salto: se detecta y el pantallazo no se conserva."""
    pytest.importorskip("playwright")

    async def only_localhost(url, *, resolve=True):
        if httpx.URL(url).host != "localhost":
            raise netguard.NetworkGuardError("no pública")

    monkeypatch.setattr(netguard, "ensure_public", only_localhost)
    async with HttpClient(config, allow_private=True) as http_client:
        module = Capture(Context(config=config, http=http_client))
        module.ctx.http._guard = True
        reason = await module._screenshot(
            f"http://localhost:{web_server}/redirect", tmp_path / "s.png"
        )
    if reason and "Executable" in reason:
        pytest.skip(reason)
    assert reason == "una redirección del navegador apuntaba a una red no pública"
    assert not (tmp_path / "s.png").exists()


# --- doc_harvest -----------------------------------------------------------------------------


CDX = "https://web.archive.org/cdx/search/cdx"
DOC = "https://www.example.com/informe.pdf"
PDF = b"%PDF-1.4\n1 0 obj << /Author (Ana Ruiz) /Producer (Word) >> endobj\n"


def test_doc_harvest_takes_root_domains_and_documents_only(ctx):
    module = DocHarvest(ctx)
    assert module.accepts(Entity(type=EntityType.DOMAIN, value="example.com"))
    assert not module.accepts(
        Entity(type=EntityType.DOMAIN, value="a.example.com", data={"subdomain": True})
    )
    assert module.accepts(url_entity(DOC, document=True))
    assert not module.accepts(url_entity(DOC))
    assert not DocHarvest.passive


@respx.mock
async def test_doc_harvest_discovers_documents_in_wayback(ctx):
    route = respx.get(CDX).mock(
        return_value=httpx.Response(200, json=[["original"], [DOC], ["https://example.com/b.docx"]])
    )
    found = await DocHarvest(ctx).run(Entity(type=EntityType.DOMAIN, value="example.com"))
    assert [e.value for e in found] == [DOC, "https://example.com/b.docx"]
    assert all(e.data["document"] for e in found)
    params = route.calls.last.request.url.params
    assert params["url"] == "example.com/*"
    assert params["limit"] == "20"
    assert params["filter"].startswith("mimetype:application/(pdf|")


@respx.mock
async def test_doc_harvest_reports_when_wayback_does_not_answer(ctx):
    respx.get(CDX).mock(side_effect=httpx.ReadTimeout("lento"))
    with pytest.raises(ModuleError, match="a tiempo"):
        await DocHarvest(ctx).run(Entity(type=EntityType.DOMAIN, value="example.com"))


@respx.mock
async def test_doc_harvest_reads_the_document_and_deletes_it(ctx, tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    respx.get(DOC).mock(return_value=httpx.Response(200, content=PDF))
    [record] = await DocHarvest(ctx).run(url_entity(DOC, document=True))
    assert record.value == f"doc_harvest:{DOC}"
    assert record.data["author"] == "Ana Ruiz"
    assert record.data["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert record.data["size"] == len(PDF)
    assert list(tmp_path.iterdir()) == []


@respx.mock
async def test_doc_harvest_reports_the_gps_of_a_photo_as_location(ctx):
    respx.get(DOC).mock(return_value=httpx.Response(200, content=exif_jpeg()))
    found = await DocHarvest(ctx).run(url_entity(DOC, document=True))
    assert "40.416667,-3.703889" in [e.value for e in found]


@respx.mock
async def test_a_document_that_is_gone_is_not_an_error(ctx):
    respx.get(DOC).mock(return_value=httpx.Response(404))
    assert await DocHarvest(ctx).run(url_entity(DOC, document=True)) == []


@respx.mock
async def test_a_file_that_fails_while_reading_is_deleted_too(ctx, tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    respx.get(DOC).mock(return_value=httpx.Response(200, content=b"PK\x03\x04roto"))
    with pytest.raises(Exception, match="dañado"):
        await DocHarvest(ctx).run(url_entity(DOC, document=True))
    assert list(tmp_path.iterdir()) == []


# --- cloud_storage_refs ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "provider", "bucket", "probe"),
    [
        (
            "https://acme.s3.amazonaws.com/a/b.png",
            "s3",
            "acme",
            "https://acme.s3.amazonaws.com/",
        ),
        (
            "https://acme.s3.eu-west-1.amazonaws.com/x",
            "s3",
            "acme",
            "https://acme.s3.eu-west-1.amazonaws.com/",
        ),
        (
            "https://acme.s3-eu-west-1.amazonaws.com/x",
            "s3",
            "acme",
            "https://acme.s3-eu-west-1.amazonaws.com/",
        ),
        (
            "https://s3.eu-west-1.amazonaws.com/acme/x",
            "s3",
            "acme",
            "https://s3.eu-west-1.amazonaws.com/acme",
        ),
        (
            "https://a.b.c.s3.amazonaws.com/x",
            "s3",
            "a.b.c",
            "https://s3.amazonaws.com/a.b.c",
        ),
        (
            "https://storage.googleapis.com/acme/x",
            "gcs",
            "acme",
            "https://storage.googleapis.com/acme",
        ),
        (
            "https://acme.storage.googleapis.com/x",
            "gcs",
            "acme",
            "https://storage.googleapis.com/acme",
        ),
        (
            "https://cuenta.blob.core.windows.net/fotos/x.png?sv=1&sig=TOKEN",
            "azure",
            "cuenta/fotos",
            "https://cuenta.blob.core.windows.net/fotos",
        ),
    ],
)
def test_parse_reference_recognises_each_provider(url, provider, bucket, probe):
    reference = parse_reference(url)
    assert (reference.provider, reference.bucket, reference.url) == (provider, bucket, probe)
    assert "TOKEN" not in reference.url


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/s3.amazonaws.com/x",
        "https://evil-s3.amazonaws.com.example.com/x",
        "https://s3.amazonaws.com/",
        "https://storage.googleapis.com/",
        "https://cuenta.blob.core.windows.net/",
        "ftp://acme.s3.amazonaws.com/x",
        "no es una url",
    ],
)
def test_a_url_without_a_bucket_is_not_a_reference(url, ctx):
    assert parse_reference(url) is None
    assert not CloudStorageRefs(ctx).accepts(url_entity(url))


@pytest.mark.parametrize(
    ("provider", "status", "body", "access"),
    [
        ("s3", 200, "<ListBucketResult></ListBucketResult>", "public_list"),
        ("s3", 403, "<Code>AccessDenied</Code>", "denied"),
        ("s3", 404, "<Code>NoSuchBucket</Code>", "absent"),
        ("s3", 301, "<Code>PermanentRedirect</Code>", "unknown"),
        ("s3", 200, "<html></html>", "unknown"),
        ("gcs", 200, "<ListBucketResult></ListBucketResult>", "public_list"),
        ("gcs", 403, "AccessDenied", "denied"),
        ("gcs", 404, "NoSuchBucket", "absent"),
        ("azure", 200, "<EnumerationResults></EnumerationResults>", "public_list"),
        ("azure", 404, "<Code>ResourceNotFound</Code>", "unknown"),
        ("azure", 409, "<Code>PublicAccessNotPermitted</Code>", "denied"),
        ("azure", 500, "", "unknown"),
    ],
)
def test_classify_access(provider, status, body, access):
    assert classify_access(provider, status, body) == access


@respx.mock
async def test_each_bucket_is_probed_only_once(ctx):
    route = respx.get("https://acme.s3.amazonaws.com/").mock(
        return_value=httpx.Response(200, text="<ListBucketResult></ListBucketResult>")
    )
    module = CloudStorageRefs(ctx)
    [record] = await module.run(url_entity("https://acme.s3.amazonaws.com/a.png"))
    assert await module.run(url_entity("https://acme.s3.amazonaws.com/b.png")) == []
    assert route.call_count == 1
    assert record.value == "cloud_storage:s3:acme"
    assert record.data["access"] == "public_list"
    params = route.calls.last.request.url.params
    assert (params["list-type"], params["max-keys"]) == ("2", "1")


@respx.mock
async def test_the_token_of_a_url_goes_nowhere(ctx):
    route = respx.get("https://cuenta.blob.core.windows.net/fotos").mock(
        return_value=httpx.Response(404, text="<Code>ResourceNotFound</Code>")
    )
    url = "https://cuenta.blob.core.windows.net/fotos/x.png?sig=TOKEN"
    [record] = await CloudStorageRefs(ctx).run(url_entity(url))
    assert "TOKEN" not in str(route.calls.last.request.url)
    assert "TOKEN" not in json.dumps(record.data)


@respx.mock
async def test_an_azure_account_without_dns_does_not_exist(ctx):
    respx.get("https://nadie.blob.core.windows.net/fotos").mock(
        side_effect=httpx.ConnectError("no resuelve")
    )
    url = "https://nadie.blob.core.windows.net/fotos/x.png"
    [record] = await CloudStorageRefs(ctx).run(url_entity(url))
    assert record.data["access"] == "absent"


# --- ext_exiftool ----------------------------------------------------------------------------


def file_entity(path) -> Entity:
    return Entity(type=EntityType.FILE, value=str(path))


def test_exiftool_takes_the_path_from_stdin_and_never_as_an_argument():
    args = ExtExifTool.args(ExtExifTool(None), file_entity("a.heic"))
    assert args[-2:] == ["-@", "-"]
    assert "a.heic" not in args


def test_exiftool_that_prints_nothing_is_an_error_not_an_empty_result():
    with pytest.raises(ModuleError):
        ExtExifTool(None).parse(file_entity("a.heic"), [])


def test_exiftool_parse_drops_what_describes_the_analyst_computer():
    tags = {
        "SourceFile": "C:/Users/ana/a.heic",
        "ExifTool:ExifToolVersion": 12.8,
        "File:FileName": "a.heic",
        "File:Directory": "C:/Users/ana",
        "File:MIMEType": "image/heic",
        "EXIF:Make": "Apple",
        "XMP:Title": "x" * 1000,
        "Composite:GPSLatitude": 40.5,
        "Composite:GPSLongitude": -3.25,
    }
    record, location = ExtExifTool(None).parse(file_entity("a.heic"), [[tags]])
    assert record.data["EXIF:Make"] == "Apple"
    assert record.data["File:MIMEType"] == "image/heic"
    assert len(record.data["XMP:Title"]) == 500
    for name in ("SourceFile", "File:FileName", "File:Directory", "ExifTool:ExifToolVersion"):
        assert name not in record.data
    assert location.value == "40.500000,-3.250000"


def test_exiftool_without_document_metadata_is_empty():
    tags = {"SourceFile": "a.bin", "File:FileName": "a.bin", "File:MIMEType": "text/plain"}
    assert ExtExifTool(None).parse(file_entity("a.bin"), [[tags]]) == []


async def test_exiftool_skips_a_file_that_is_not_here(ctx, tmp_path):
    with pytest.raises(ModuleSkipped):
        await ExtExifTool(ctx).run(file_entity(tmp_path / "no-existe.bin"))


def test_exiftool_runs_behind_a_proxy_because_it_does_not_use_the_network():
    assert ExtExifTool.direct_dns is False


needs_exiftool = pytest.mark.skipif(
    find_executable("exiftool") is None, reason="ExifTool no está instalado"
)


@needs_exiftool
@pytest.mark.parametrize("name", ["foto.jpg", "fotografía con tildes ñ.jpg"])
async def test_real_exiftool_reads_a_jpeg(ctx, tmp_path, name):
    path = tmp_path / name
    path.write_bytes(exif_jpeg())
    found = await ExtExifTool(ctx).run(file_entity(path))
    values = [e.value for e in found]
    assert f"ext_exiftool:{path}" in values
    assert "40.416667,-3.703889" in values


@needs_exiftool
async def test_real_exiftool_with_a_format_it_does_not_know(ctx, tmp_path):
    path = tmp_path / "datos.xyz"
    path.write_bytes(b"\x00\x01nada reconocible")
    assert await ExtExifTool(ctx).run(file_entity(path)) == []
