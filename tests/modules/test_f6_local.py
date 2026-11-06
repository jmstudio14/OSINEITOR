"""Fase 6, módulos locales (teléfono, criptomonedas, coordenadas, enlaces y ficheros)."""

from __future__ import annotations

import hashlib
import json
import struct
import zipfile

import httpx
import pytest
import respx
from typer.testing import CliRunner

from osineitor.cli import app
from osineitor.crypto_address import classify
from osineitor.models import Entity, EntityType, detect_type
from osineitor.modules.base import ModuleError, ModuleSkipped
from osineitor.modules.crypto.detect import CryptoDetect
from osineitor.modules.files.hashes import FileHash
from osineitor.modules.files.image_links import ImageLinks
from osineitor.modules.files.meta import FileMeta
from osineitor.modules.geo.point import GeoPoint
from osineitor.modules.phone.parse import PhoneParse
from osineitor.normalize import canonical

BTC_BECH32 = "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq"
BTC_LEGACY = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
ETH = "0x52908400098527886E0F7030069857D2E4169EE7"


def seed(kind: EntityType, value: str) -> Entity:
    return Entity(type=kind, value=value)


# --- reconocimiento de tipos -----------------------------------------------------------------


def test_classify_validates_the_checksum():
    assert classify(BTC_BECH32) == {"chain": "btc", "format": "bech32"}
    assert classify(BTC_LEGACY) == {"chain": "btc", "format": "p2pkh"}
    assert classify("3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy") == {"chain": "btc", "format": "p2sh"}
    assert classify(ETH) == {"chain": "eth", "format": "hex"}
    taproot = "bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqzk5jj0"
    assert classify(taproot) == {"chain": "btc", "format": "bech32m"}


@pytest.mark.parametrize(
    "value",
    [
        "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNb",  # una letra cambiada: la suma no cuadra
        BTC_BECH32[:-1] + "p",
        "bc1QAR0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq",  # mayúsculas y minúsculas mezcladas
        "john",
        "0x1234",
    ],
)
def test_classify_rejects_what_is_not_an_address(value):
    assert classify(value) is None


def test_detect_type_recognises_phones_crypto_coordinates_and_files(tmp_path):
    assert detect_type("+34 612 34 56 78") == EntityType.PHONE
    assert detect_type("0034612345678") == EntityType.PHONE
    assert detect_type(BTC_BECH32) == EntityType.CRYPTO_ADDRESS
    assert detect_type(ETH) == EntityType.CRYPTO_ADDRESS
    assert detect_type("40.4168, -3.7038") == EntityType.LOCATION
    document = tmp_path / "informe.pdf"
    document.write_bytes(b"%PDF-1.4")
    assert detect_type(str(document)) == EntityType.FILE


def test_detect_type_keeps_usernames_and_missing_paths_as_before(tmp_path, monkeypatch):
    assert detect_type("a/b") == EntityType.USERNAME
    assert detect_type("007") == EntityType.USERNAME
    assert detect_type(str(tmp_path / "no-existe.pdf")) == EntityType.USERNAME
    # Sin separador no es una ruta: un fichero llamado `john` no convierte a `john` en FILE.
    (tmp_path / "john").write_bytes(b"x")
    monkeypatch.chdir(tmp_path)
    assert detect_type("john") == EntityType.USERNAME


def test_coordinates_are_canonical_and_validated():
    assert canonical("location", "40.4168 , -3.7038") == "40.416800,-3.703800"
    assert canonical("location", "Madrid,  España") == "Madrid, España"
    with pytest.raises(ValueError, match="fuera de rango"):
        canonical("location", "95.0,10.0")


def test_a_file_path_keeps_its_double_spaces():
    assert canonical("file", " C:/a  b/c.pdf ") == "C:/a  b/c.pdf"


# --- phone_parse, crypto_detect, geo_point, image_links --------------------------------------


async def test_phone_parse_gives_region_line_type_and_formats(ctx):
    [record] = await PhoneParse(ctx).run(seed(EntityType.PHONE, "+34612345678"))
    data = record.data
    assert record.value == "phone:+34612345678"
    assert (data["valid"], data["region"], data["country_code"]) == (True, "ES", 34)
    assert data["line_type"] == "móvil"
    assert data["international"] == "+34 612 34 56 78"
    assert data["rfc3966"] == "tel:+34-612-34-56-78"
    assert "Europe/Madrid" in data["time_zones"]


async def test_phone_parse_flags_an_invalid_number(ctx):
    [record] = await PhoneParse(ctx).run(seed(EntityType.PHONE, "+34999999999"))
    assert record.data["valid"] is False


async def test_crypto_detect_reports_chain_and_how_it_was_checked(ctx):
    [btc] = await CryptoDetect(ctx).run(seed(EntityType.CRYPTO_ADDRESS, BTC_BECH32))
    assert (btc.data["chain"], btc.data["checksum_verified"]) == ("btc", True)
    [eth] = await CryptoDetect(ctx).run(seed(EntityType.CRYPTO_ADDRESS, ETH))
    assert (eth.data["chain"], eth.data["checksum_verified"]) == ("eth", False)
    assert await CryptoDetect(ctx).run(seed(EntityType.CRYPTO_ADDRESS, "a" * 30)) == []


async def test_geo_point_formats_and_links(ctx):
    module = GeoPoint(ctx)
    assert module.accepts(seed(EntityType.LOCATION, "40.4168,-3.7038"))
    assert not module.accepts(seed(EntityType.LOCATION, "Madrid"))
    [record] = await module.run(seed(EntityType.LOCATION, "40.4168,-3.7038"))
    assert record.data["dms"] == "40°25'00.48\"N 3°42'13.68\"W"
    assert "mlat=40.4168&mlon=-3.703" in record.data["openstreetmap"]
    assert "query=40.416800%2C-3.703800" in record.data["google_maps"]


async def test_image_links_only_for_images_and_encode_the_url(ctx):
    module = ImageLinks(ctx)
    assert module.accepts(seed(EntityType.URL, "https://example.com/a/foto.JPG?x=1"))
    assert not module.accepts(seed(EntityType.URL, "https://example.com/index.html"))
    [record] = await module.run(seed(EntityType.URL, "https://example.com/a b/foto.png"))
    assert "url=https%3A%2F%2Fexample.com%2Fa%20b%2Ffoto.png" in record.data["tineye"]


# --- ficheros --------------------------------------------------------------------------------


def exif_jpeg(lat=(40, 25, 0), lon=(3, 42, 14), lat_ref=b"N\x00", lon_ref=b"W\x00") -> bytes:
    """JPEG mínimo con un EXIF little-endian: marca, modelo y GPS."""
    make, model = b"ACME\x00", b"Cam 1\x00"
    entries_ifd0 = 3
    ifd0_size = 2 + entries_ifd0 * 12 + 4
    make_off = 8 + ifd0_size
    model_off = make_off + len(make)
    gps_off = model_off + len(model)
    gps_size = 2 + 4 * 12 + 4
    rat_lat = gps_off + gps_size
    rat_lon = rat_lat + 24

    def entry(tag, kind, count, value):
        return struct.pack("<HHI", tag, kind, count) + value

    ifd0 = struct.pack("<H", entries_ifd0)
    ifd0 += entry(0x010F, 2, len(make), struct.pack("<I", make_off))
    ifd0 += entry(0x0110, 2, len(model), struct.pack("<I", model_off))
    ifd0 += entry(0x8825, 4, 1, struct.pack("<I", gps_off)) + struct.pack("<I", 0)
    gps = struct.pack("<H", 4)
    gps += entry(1, 2, 2, lat_ref + b"\x00\x00")
    gps += entry(2, 5, 3, struct.pack("<I", rat_lat))
    gps += entry(3, 2, 2, lon_ref + b"\x00\x00")
    gps += entry(4, 5, 3, struct.pack("<I", rat_lon)) + struct.pack("<I", 0)

    def rationals(values):
        return b"".join(struct.pack("<II", v, 1) for v in values)

    tiff = b"II*\x00" + struct.pack("<I", 8) + ifd0 + make + model + gps
    tiff += rationals(lat) + rationals(lon)
    app1 = b"Exif\x00\x00" + tiff
    return b"\xff\xd8\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1 + b"\xff\xda\x00\x02"


async def test_file_hash_matches_hashlib(ctx, tmp_path):
    path = tmp_path / "datos.bin"
    path.write_bytes(b"hola" * 1000)
    [record] = await FileHash(ctx).run(seed(EntityType.FILE, str(path)))
    expected = hashlib.sha256(b"hola" * 1000).hexdigest()
    assert record.value == f"file_hash:{expected}"
    assert record.data["md5"] == hashlib.md5(b"hola" * 1000).hexdigest()
    assert record.data["size"] == 4000


async def test_file_modules_skip_a_missing_file(ctx, tmp_path):
    ghost = seed(EntityType.FILE, str(tmp_path / "no-existe.pdf"))
    for module in (FileHash(ctx), FileMeta(ctx)):
        with pytest.raises(ModuleSkipped):
            await module.run(ghost)


async def test_file_meta_reads_exif_and_emits_the_gps_location(ctx, tmp_path):
    path = tmp_path / "foto.jpg"
    path.write_bytes(exif_jpeg())
    out = await FileMeta(ctx).run(seed(EntityType.FILE, str(path)))
    record, location = out
    assert (record.data["format"], record.data["camera_make"]) == ("jpeg", "ACME")
    assert record.data["camera_model"] == "Cam 1"
    assert (location.type, location.value) == (EntityType.LOCATION, "40.416667,-3.703889")


async def test_file_meta_southern_and_eastern_hemispheres(ctx, tmp_path):
    path = tmp_path / "sur.jpg"
    path.write_bytes(exif_jpeg(lat_ref=b"S\x00", lon_ref=b"E\x00"))
    out = await FileMeta(ctx).run(seed(EntityType.FILE, str(path)))
    assert out[1].value == "-40.416667,3.703889"


async def test_file_meta_reads_pdf_info_literals_and_hex(ctx, tmp_path):
    path = tmp_path / "doc.pdf"
    path.write_bytes(
        b"%PDF-1.4\n1 0 obj<</Author (Ana \\(G\\)) /Creator <4D6F7264> "
        b"/CreationDate (D:20240131120000+01'00') /Producer (\xfe\xff\x00P\x00D\x00F)>>endobj\n"
    )
    [record] = await FileMeta(ctx).run(seed(EntityType.FILE, str(path)))
    data = record.data
    assert data["author"] == "Ana (G)"
    assert data["software"] == "Mord"
    assert data["created"] == "2024-01-31T12:00:00"
    assert data["producer"] == "PDF"


async def test_file_meta_reads_office_properties(ctx, tmp_path):
    path = tmp_path / "informe.docx"
    core = (
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/'
        'core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:creator>Ana García</dc:creator><cp:lastModifiedBy>Luis</cp:lastModifiedBy>"
        "</cp:coreProperties>"
    )
    app = (
        '<Properties xmlns="x"><Application>Microsoft Office Word</Application>'
        "<Company>ACME</Company></Properties>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("docProps/core.xml", core)
        archive.writestr("docProps/app.xml", app)
    [record] = await FileMeta(ctx).run(seed(EntityType.FILE, str(path)))
    assert record.data["format"] == "ooxml"
    assert (record.data["author"], record.data["last_modified_by"]) == ("Ana García", "Luis")
    assert (record.data["software"], record.data["company"]) == ("Microsoft Office Word", "ACME")


async def test_file_meta_reads_opendocument(ctx, tmp_path):
    path = tmp_path / "nota.odt"
    meta = (
        '<office:document-meta xmlns:office="o" xmlns:meta="m" xmlns:dc="d">'
        "<office:meta><meta:initial-creator>Ana</meta:initial-creator>"
        "<meta:generator>LibreOffice</meta:generator></office:meta></office:document-meta>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        archive.writestr("meta.xml", meta)
    [record] = await FileMeta(ctx).run(seed(EntityType.FILE, str(path)))
    assert (record.data["author"], record.data["software"]) == ("Ana", "LibreOffice")


async def test_file_meta_refuses_xml_with_entities(ctx, tmp_path):
    path = tmp_path / "malo.docx"
    bomb = (
        '<!DOCTYPE x [<!ENTITY a "aaaa">]><cp:coreProperties xmlns:cp="c">&a;</cp:coreProperties>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("docProps/core.xml", bomb)
    with pytest.raises(ModuleError, match="entidades"):
        await FileMeta(ctx).run(seed(EntityType.FILE, str(path)))


async def test_file_meta_without_metadata_is_empty(ctx, tmp_path):
    path = tmp_path / "plano.txt"
    path.write_text("nada que ver")
    assert await FileMeta(ctx).run(seed(EntityType.FILE, str(path))) == []


@respx.mock
async def test_file_modules_never_touch_the_network(ctx, tmp_path):
    """Criterio de la fase 6: el contenido de un fichero no sale del equipo."""
    path = tmp_path / "foto.jpg"
    path.write_bytes(exif_jpeg())
    catch_all = respx.route().mock(return_value=httpx.Response(200))
    entity = seed(EntityType.FILE, str(path))
    await FileHash(ctx).run(entity)
    await FileMeta(ctx).run(entity)
    assert not catch_all.called


# --- scan de punta a punta -------------------------------------------------------------------

runner = CliRunner()


def test_scan_detects_a_phone_and_requires_purpose_when_configured(monkeypatch):
    monkeypatch.setenv("OSINEITOR_REQUIRE_PURPOSE", "1")
    result = runner.invoke(app, ["scan", "+34612345678", "--no-save"])
    assert result.exit_code == 2
    assert "--purpose" in result.output


def test_scan_of_a_phone_runs_phone_parse(monkeypatch):
    result = runner.invoke(app, ["scan", "+34612345678", "--no-save", "--json"])
    assert result.exit_code == 0, result.output
    records = [e["value"] for e in json.loads(result.output)["entities"]]
    assert "phone:+34612345678" in records


def test_scan_of_a_local_file_hashes_it_without_network(tmp_path):
    path = tmp_path / "foto.jpg"
    path.write_bytes(exif_jpeg())
    with respx.mock(assert_all_called=False) as router:
        any_call = router.route().mock(return_value=httpx.Response(200))
        result = runner.invoke(app, ["scan", str(path), "--no-save", "--json"])
    assert result.exit_code == 0, result.output
    values = [e["value"] for e in json.loads(result.output)["entities"]]
    assert any(v.startswith("file_hash:") for v in values)
    assert "40.416667,-3.703889" in values  # el GPS del EXIF pasa a `location` y a `geo_point`
    assert any(v.startswith("geo:40.416667") for v in values)
    assert not any_call.called
