"""F3.5: `osineitor update-data` y el registro de datasets (versión, hash y licencia)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
import respx
from typer.testing import CliRunner

from osineitor import datasets
from osineitor.cli import app
from osineitor.config import Config
from osineitor.http import HttpClient
from osineitor.modules.username.sites import load_sites
from tests.test_contract import validate

runner = CliRunner()
URL = "https://data.test/sites.json"
SITES = {
    "$schema": "https://example.test/schema.json",
    "Ejemplo": {"url": "https://ejemplo.test/{}", "errorType": "status_code"},
}


def dataset(**attrs) -> datasets.Dataset:
    base = {
        "name": "sherlock-sites",
        "description": "firmas",
        "url": URL,
        "license": "MIT",
        "filename": "sites.json",
        "prepare": datasets._sherlock,
    }
    return datasets.Dataset(**{**base, **attrs})


@pytest.fixture(autouse=True)
def fresh_sites():
    load_sites.cache_clear()
    yield
    load_sites.cache_clear()


async def update(*catalog, names=None):
    async with HttpClient(Config(), backoff=0) as http:
        return await datasets.update(http, names, catalog)


def serve(body=None, status=200, **headers):
    body = json.dumps(SITES) if body is None else body
    route = respx.get(URL).mock(return_value=httpx.Response(status, content=body, headers=headers))
    return route


@respx.mock
async def test_it_installs_the_dataset_and_records_version_hash_and_license():
    serve(etag='"abc123"')
    [result] = await update(dataset())
    assert result.status == "actualizado"
    path = datasets.datasets_dir() / "sites.json"
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    assert json.loads(path.read_text(encoding="utf-8")).keys() == {"Ejemplo"}  # sin `$schema`
    entry = datasets.manifest()["sherlock-sites"]
    assert (entry["version"], entry["sha256"], entry["license"], entry["url"]) == (
        "abc123",
        sha,
        "MIT",
        URL,
    )
    assert (result.version, result.sha256, result.license) == ("abc123", sha, "MIT")
    assert datasets.installed_path("sherlock-sites") == path


@respx.mock
async def test_a_pinned_hash_installs_only_the_matching_download():
    body = json.dumps(SITES)
    pinned = hashlib.sha256(body.encode()).hexdigest()
    serve(body=body)
    [ok] = await update(dataset(sha256=pinned))
    assert ok.status == "actualizado"
    respx.reset()
    serve(body=json.dumps({"Otro": {"url": "https://otro.test/{}"}}))
    [bad] = await update(dataset(sha256=pinned))
    assert bad.status == "error" and "no coincide" in bad.detail
    assert json.loads(datasets.installed_path("sherlock-sites").read_text("utf-8")).keys() == {
        "Ejemplo"
    }


def test_the_catalog_pins_a_commit_and_a_hash():
    """Lo que no es un feed público que cambia a diario va fijado a un commit y a su hash."""
    for entry in datasets.CATALOG:
        assert "/master/" not in entry.url and "/main/" not in entry.url
        if entry.license == "public-feed":
            assert entry.sha256 == ""
        else:
            assert len(entry.sha256) == 64


@respx.mock
async def test_the_version_falls_back_to_last_modified_and_then_to_the_date():
    serve(**{"last-modified": "Wed, 21 Oct 2026 07:28:00 GMT"})
    [first] = await update(dataset())
    assert first.version == "Wed, 21 Oct 2026 07:28:00 GMT"
    respx.reset()
    serve(body=json.dumps({"Otro": {"url": "https://otro.test/{}"}}))
    [second] = await update(dataset())
    assert second.status == "actualizado" and second.version[:2] == "20"  # fecha ISO


@respx.mock
async def test_an_unchanged_dataset_is_reported_as_such():
    serve()
    await update(dataset())
    before = datasets.manifest()
    [result] = await update(dataset())
    assert result.status == "sin cambios"
    assert datasets.manifest() == before


@respx.mock
async def test_an_incompatible_license_is_rejected_without_downloading():
    route = serve()
    [result] = await update(dataset(name="gpl-data", license="GPL-3.0-only"))
    assert result.status == "rechazado" and "GPL-3.0-only" in result.detail
    assert not route.called
    assert not datasets.datasets_dir().exists()


@pytest.mark.parametrize("license_id", ["", "Proprietary", "CC-BY-SA-4.0", "AGPL-3.0-or-later"])
@respx.mock
async def test_anything_that_is_not_known_to_be_compatible_is_rejected(license_id):
    serve()
    [result] = await update(dataset(license=license_id))
    assert result.status == "rechazado"


@respx.mock
async def test_a_bad_download_is_an_error_and_keeps_the_previous_copy():
    serve()
    await update(dataset())
    previous = (datasets.datasets_dir() / "sites.json").read_bytes()
    for body, status in (
        ("no es json", 200),
        ("{}", 200),
        ('{"x": {"sin": "url"}}', 200),
        ("", 500),
    ):
        respx.reset()
        serve(body=body, status=status)
        [result] = await update(dataset())
        assert result.status == "error", body
        assert (datasets.datasets_dir() / "sites.json").read_bytes() == previous


@respx.mock
async def test_an_oversized_download_is_refused(monkeypatch):
    serve()
    monkeypatch.setattr(datasets, "MAX_BYTES", 10)
    [result] = await update(dataset())
    assert result.status == "error" and "supera" in result.detail


@respx.mock
async def test_one_failing_dataset_does_not_stop_the_others():
    serve()
    respx.get("https://data.test/otro.json").mock(return_value=httpx.Response(404))
    broken = dataset(name="otro", url="https://data.test/otro.json", filename="otro.json")
    results = await update(broken, dataset())
    assert [(r.name, r.status) for r in results] == [
        ("otro", "error"),
        ("sherlock-sites", "actualizado"),
    ]


@respx.mock
async def test_only_the_requested_datasets_are_updated():
    route = serve()
    other = dataset(name="otro", url="https://data.test/otro.json", filename="otro.json")
    results = await update(other, dataset(), names=["sherlock-sites"])
    assert [r.name for r in results] == ["sherlock-sites"] and route.called


# --- quien lee el dataset -----------------------------------------------------------------------


@respx.mock
async def test_the_username_module_uses_the_updated_signatures():
    assert len(load_sites()) > 100  # las que vienen en el paquete
    serve()
    await update(dataset())
    load_sites.cache_clear()
    assert set(load_sites()) == {"Ejemplo"}


@respx.mock
async def test_a_file_that_does_not_match_its_recorded_hash_is_ignored():
    serve()
    await update(dataset())
    (datasets.datasets_dir() / "sites.json").write_text('{"Manipulado": {}}', encoding="utf-8")
    assert datasets.installed_path("sherlock-sites") is None
    load_sites.cache_clear()
    assert len(load_sites()) > 100  # vuelve a las firmas del paquete


def test_nothing_installed_means_no_path():
    assert datasets.installed_path("sherlock-sites") is None
    assert datasets.manifest() == {}


def test_a_corrupt_manifest_counts_as_empty():
    datasets.datasets_dir().mkdir(parents=True)
    (datasets.datasets_dir() / "manifest.json").write_text("{roto", encoding="utf-8")
    assert datasets.manifest() == {} and datasets.installed_path("sherlock-sites") is None


def test_the_catalog_only_holds_compatible_licenses():
    """Si un dataset con otra licencia entra en el catálogo, `update-data` lo rechazaría siempre."""
    assert {d.license for d in datasets.CATALOG} <= datasets.COMPATIBLE_LICENSES


# --- feeds de rangos de IP (cloud_attribution) --------------------------------------------------

AWS = {
    "prefixes": [
        {"ip_prefix": "3.5.140.0/22", "service": "AMAZON"},
        {"ip_prefix": "3.5.140.0/22", "service": "S3"},
        {"ip_prefix": "52.95.0.5/16", "service": "EC2"},  # con bits de host: se normaliza
    ],
    "ipv6_prefixes": [{"ipv6_prefix": "2600:1f00::/24", "service": "AMAZON"}],
}
GCP = {"prefixes": [{"ipv4Prefix": "34.64.0.0/10"}, {"ipv6Prefix": "2600:1900::/35"}]}
FEEDS = {
    "aws-ip-ranges": (json.dumps(AWS), ["2600:1f00::/24", "3.5.140.0/22", "52.95.0.0/16"]),
    "gcp-ip-ranges": (json.dumps(GCP), ["2600:1900::/35", "34.64.0.0/10"]),
    "cloudflare-ips-v4": (
        "173.245.48.0/20\n103.21.244.0/22\n",
        ["103.21.244.0/22", "173.245.48.0/20"],
    ),
    "cloudflare-ips-v6": ("2400:cb00::/32\n", ["2400:cb00::/32"]),
}


def feed(name: str) -> datasets.Dataset:
    return next(d for d in datasets.CATALOG if d.name == name)


@pytest.mark.parametrize("name", FEEDS)
@respx.mock
async def test_each_ip_range_feed_installs_as_a_sorted_list_of_networks(name):
    body, expected = FEEDS[name]
    entry = feed(name)
    respx.get(entry.url).mock(return_value=httpx.Response(200, content=body))
    [result] = await update(entry)
    assert (result.status, result.license) == ("actualizado", "public-feed")
    assert json.loads(datasets.installed_path(name).read_text("utf-8")) == expected


@respx.mock
async def test_an_ip_range_feed_that_changes_is_updated_and_the_manifest_follows():
    entry = feed("cloudflare-ips-v6")
    respx.get(entry.url).mock(return_value=httpx.Response(200, content="2400:cb00::/32\n"))
    await update(entry)
    first = datasets.manifest()["cloudflare-ips-v6"]["sha256"]
    respx.reset()
    respx.get(entry.url).mock(
        return_value=httpx.Response(200, content="2400:cb00::/32\n2606:4700::/32\n")
    )
    [result] = await update(entry)
    assert result.status == "actualizado" and result.sha256 != first
    assert datasets.installed_path("cloudflare-ips-v6")


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("aws-ip-ranges", "no es json"),
        ("aws-ip-ranges", "[]"),
        (
            "aws-ip-ranges",
            json.dumps({"prefixes": [{"ip_prefix": "no-es-red"}], "ipv6_prefixes": []}),
        ),
        ("aws-ip-ranges", json.dumps({"prefixes": [], "ipv6_prefixes": []})),
        ("gcp-ip-ranges", json.dumps({"prefixes": [{"servicio": "x"}]})),
        ("gcp-ip-ranges", json.dumps({"otra": []})),
        ("cloudflare-ips-v4", "<html>Access denied</html>"),
        ("cloudflare-ips-v4", ""),
    ],
)
@respx.mock
async def test_an_ip_range_feed_in_an_unexpected_format_is_an_error_and_keeps_the_copy(name, body):
    entry = feed(name)
    good, _ = FEEDS[name]
    respx.get(entry.url).mock(return_value=httpx.Response(200, content=good))
    await update(entry)
    previous = (datasets.datasets_dir() / entry.filename).read_bytes()
    respx.reset()
    respx.get(entry.url).mock(return_value=httpx.Response(200, content=body))
    [result] = await update(entry)
    assert result.status == "error", body
    assert (datasets.datasets_dir() / entry.filename).read_bytes() == previous


# --- Azure: URL que cambia cada semana ----------------------------------------------------------

AZURE_BASE = "https://download.microsoft.com/download/7/1/d/71d86715-5596-4529-9b13-da13a5de5b63/"
AZURE_JSON = json.dumps(
    {
        "changeNumber": 1,
        "values": [
            {"name": "ActionGroup", "properties": {"addressPrefixes": ["4.145.74.52/30"]}},
            {
                "name": "AzureCloud",
                "properties": {"addressPrefixes": ["20.33.0.0/16", "2603:1000::/40"]},
            },
        ],
    }
)


def azure_page(*dates: str) -> str:
    links = "".join(
        f'<a href="{AZURE_BASE}ServiceTags_Public_{d}.json" class="dlcdetail">Download</a>'
        for d in dates
    )
    return f"<html><body>{links}</body></html>"


def serve_azure(date: str, body: str = AZURE_JSON) -> respx.Route:
    respx.get(datasets.AZURE_PAGE).mock(return_value=httpx.Response(200, text=azure_page(date)))
    return respx.get(f"{AZURE_BASE}ServiceTags_Public_{date}.json").mock(
        return_value=httpx.Response(200, content=body)
    )


@respx.mock
async def test_azure_finds_the_current_url_and_installs_the_azurecloud_ranges():
    serve_azure("20261102")
    [result] = await update(feed("azure-ip-ranges"))
    assert (result.status, result.license) == ("actualizado", "public-feed")
    path = datasets.installed_path("azure-ip-ranges")
    assert json.loads(path.read_text("utf-8")) == ["20.33.0.0/16", "2603:1000::/40"]
    assert datasets.manifest()["azure-ip-ranges"]["url"].endswith(
        "ServiceTags_Public_20261102.json"
    )


@respx.mock
async def test_azure_with_the_same_url_does_not_download_again():
    serve_azure("20261102")
    await update(feed("azure-ip-ranges"))
    before = datasets.manifest()
    respx.reset()
    download = serve_azure("20261102")
    [result] = await update(feed("azure-ip-ranges"))
    assert result.status == "sin cambios" and not download.called
    assert result.sha256 == before["azure-ip-ranges"]["sha256"]
    assert datasets.manifest() == before


@respx.mock
async def test_azure_with_a_new_url_replaces_the_installed_ranges():
    serve_azure("20261102")
    await update(feed("azure-ip-ranges"))
    respx.reset()
    newer = AZURE_JSON.replace("20.33.0.0/16", "20.34.0.0/16")
    serve_azure("20261109", newer)
    [result] = await update(feed("azure-ip-ranges"))
    assert result.status == "actualizado"
    assert datasets.manifest()["azure-ip-ranges"]["url"].endswith("_20261109.json")
    ranges = json.loads(datasets.installed_path("azure-ip-ranges").read_text("utf-8"))
    assert "20.34.0.0/16" in ranges and "20.33.0.0/16" not in ranges


@respx.mock
async def test_a_new_azure_url_with_the_same_ranges_is_recorded_so_it_is_not_fetched_again():
    serve_azure("20261102")
    await update(feed("azure-ip-ranges"))
    respx.reset()
    serve_azure("20261109")
    await update(feed("azure-ip-ranges"))
    assert datasets.manifest()["azure-ip-ranges"]["url"].endswith("_20261109.json")


@respx.mock
async def test_azure_takes_the_most_recent_link_on_the_page():
    respx.get(datasets.AZURE_PAGE).mock(
        return_value=httpx.Response(200, text=azure_page("20261026", "20261102", "20261019"))
    )
    route = respx.get(f"{AZURE_BASE}ServiceTags_Public_20261102.json").mock(
        return_value=httpx.Response(200, content=AZURE_JSON)
    )
    [result] = await update(feed("azure-ip-ranges"))
    assert result.status == "actualizado" and route.called


@pytest.mark.parametrize(
    ("page_status", "page", "body"),
    [
        (200, "<html>sin enlace</html>", AZURE_JSON),
        (503, "", AZURE_JSON),
        (200, None, json.dumps({"values": [{"name": "ActionGroup", "properties": {}}]})),
        (200, None, "no es json"),
    ],
)
@respx.mock
async def test_azure_errors_keep_the_installed_copy(page_status, page, body):
    serve_azure("20261102")
    await update(feed("azure-ip-ranges"))
    previous = (datasets.datasets_dir() / "azure-ip-ranges.json").read_bytes()
    respx.reset()
    if page is None:
        serve_azure("20261109", body)
    else:
        respx.get(datasets.AZURE_PAGE).mock(return_value=httpx.Response(page_status, text=page))
        respx.head(url__regex=AZURE_FILE).mock(return_value=httpx.Response(404))  # sin plan B
    [result] = await update(feed("azure-ip-ranges"))
    assert result.status == "error"
    assert (datasets.datasets_dir() / "azure-ip-ranges.json").read_bytes() == previous


# --- Azure: plan B si la página de Microsoft deja de traer el enlace ---------------------------

AZURE_FILE = r"ServiceTags_Public_\d{8}\.json$"
TODAY = date(2026, 11, 7)


@pytest.fixture
def today(monkeypatch):
    monkeypatch.setattr(datasets, "_today", lambda: TODAY)


def serve_guess(
    existing: dict[str, str], base: str = AZURE_BASE, page_status: int = 200
) -> list[str]:
    """La página no trae el enlace; en la ruta conocida solo existen `existing` (fecha→cuerpo)."""
    probed: list[str] = []

    def head(request):
        probed.append(str(request.url))
        name = str(request.url).rsplit("_", 1)[1].removesuffix(".json")
        return httpx.Response(
            200 if name in existing and str(request.url).startswith(base) else 404
        )

    respx.get(datasets.AZURE_PAGE).mock(
        return_value=httpx.Response(page_status, text="<html>nueva</html>")
    )
    respx.head(url__regex=AZURE_FILE).mock(side_effect=head)
    for day, body in existing.items():
        respx.get(f"{base}ServiceTags_Public_{day}.json").mock(
            return_value=httpx.Response(200, content=body)
        )
    return probed


@pytest.mark.parametrize("page_status", [200, 503])
@respx.mock
async def test_without_the_link_the_known_path_is_tried_newest_first(today, page_status):
    probed = serve_guess({"20261105": AZURE_JSON, "20261029": AZURE_JSON}, page_status=page_status)
    [result] = await update(feed("azure-ip-ranges"))
    assert result.status == "actualizado"
    assert datasets.manifest()["azure-ip-ranges"]["url"].endswith("_20261105.json")
    assert [u.rsplit("_", 1)[1] for u in probed] == [
        "20261107.json",
        "20261106.json",
        "20261105.json",
    ]


@respx.mock
async def test_the_known_path_comes_from_the_installed_url(today):
    other = "https://download.microsoft.com/download/0/0/0/otra-ruta/"
    respx.get(datasets.AZURE_PAGE).mock(
        return_value=httpx.Response(200, text=f'<a href="{other}ServiceTags_Public_20261101.json">')
    )
    respx.get(f"{other}ServiceTags_Public_20261101.json").mock(
        return_value=httpx.Response(200, content=AZURE_JSON)
    )
    await update(feed("azure-ip-ranges"))
    respx.reset()
    probed = serve_guess({"20261101": AZURE_JSON}, base=other)
    [result] = await update(feed("azure-ip-ranges"))
    assert result.status == "sin cambios"
    assert probed and all(u.startswith(other) for u in probed)


@respx.mock
async def test_with_no_file_in_the_window_the_error_says_so(today):
    probed = serve_guess({"20261020": AZURE_JSON})  # hace 18 días: fuera de la ventana
    [result] = await update(feed("azure-ip-ranges"))
    assert result.status == "error" and "últimos 14 días" in result.detail
    assert len(probed) == datasets.AZURE_GUESS_DAYS


@respx.mock
async def test_a_network_error_on_the_page_does_not_try_the_known_path(today):
    respx.get(datasets.AZURE_PAGE).mock(side_effect=httpx.ConnectError("sin red"))
    head = respx.head(url__regex=AZURE_FILE).mock(return_value=httpx.Response(200))
    [result] = await update(feed("azure-ip-ranges"))
    assert result.status == "error" and not head.called


@respx.mock
async def test_the_published_date_of_the_installed_ranges():
    assert datasets.azure_published() is None
    serve_azure("20261102")
    await update(feed("azure-ip-ranges"))
    assert datasets.azure_published() == date(2026, 11, 2)
    entries = datasets.manifest()
    entries["azure-ip-ranges"]["url"] = "https://otro.test/rangos.json"
    datasets._write(datasets.datasets_dir() / datasets.MANIFEST, json.dumps(entries).encode())
    assert datasets.azure_published() is None


# --- comprobación automática al arrancar --------------------------------------------------------


async def auto_update():
    async with HttpClient(Config(), backoff=0) as http:
        return await datasets.auto_update(http)


def stamp(when: datetime) -> None:
    datasets._write(
        datasets.datasets_dir() / datasets.AUTO_UPDATE_STAMP,
        json.dumps({"checked_at": when.isoformat()}).encode(),
    )


@respx.mock
async def test_auto_update_checks_azure_and_then_waits_a_day():
    serve_azure("20261102")
    [result] = await auto_update()
    assert (result.name, result.status) == ("azure-ip-ranges", "actualizado")
    respx.reset()
    page = respx.get(datasets.AZURE_PAGE).mock(return_value=httpx.Response(200))
    assert await auto_update() == [] and not page.called


@respx.mock
async def test_auto_update_checks_again_once_the_day_has_passed():
    stamp(datetime.now(UTC) - timedelta(days=1, minutes=1))
    serve_azure("20261102")
    assert [r.status for r in await auto_update()] == ["actualizado"]


@pytest.mark.parametrize("content", ["{roto", '{"checked_at": "ayer"}', "[]"])
@respx.mock
async def test_an_unreadable_stamp_means_checking(content):
    datasets._write(datasets.datasets_dir() / datasets.AUTO_UPDATE_STAMP, content.encode())
    serve_azure("20261102")
    assert [r.status for r in await auto_update()] == ["actualizado"]


@respx.mock
async def test_a_stamp_from_the_future_does_not_block_the_check():
    stamp(datetime.now(UTC) + timedelta(days=30))
    serve_azure("20261102")
    assert [r.status for r in await auto_update()] == ["actualizado"]


@respx.mock
async def test_a_failed_check_also_waits_a_day():
    respx.get(datasets.AZURE_PAGE).mock(return_value=httpx.Response(500))
    [result] = await auto_update()
    assert result.status == "error"
    assert await auto_update() == []


# --- la orden -----------------------------------------------------------------------------------


@respx.mock
def test_the_command_installs_and_prints_the_registry(monkeypatch):
    serve(etag='"v1"')
    monkeypatch.setattr(datasets, "CATALOG", (dataset(),))
    done = runner.invoke(app, ["update-data", "--json"])
    assert done.exit_code == 0, done.output
    validate("update_data_output", json.loads(done.output))
    [row] = json.loads(done.output)
    assert (row["name"], row["status"], row["license"], row["version"]) == (
        "sherlock-sites",
        "actualizado",
        "MIT",
        "v1",
    )
    assert datasets.installed_path("sherlock-sites")


@respx.mock
def test_the_command_exits_with_an_error_when_a_dataset_is_rejected(monkeypatch):
    serve()
    monkeypatch.setattr(datasets, "CATALOG", (dataset(license="GPL-3.0-only"),))
    done = runner.invoke(app, ["update-data", "--json"])
    assert done.exit_code == 3
    assert json.loads(done.output)[0]["status"] == "rechazado"


def test_the_command_rejects_unknown_dataset_names():
    done = runner.invoke(app, ["update-data", "nada"])
    assert done.exit_code == 2 and "sherlock-sites" in done.output


# --- la comprobación al arrancar la CLI ---------------------------------------------------------


@pytest.mark.parametrize(
    ("env", "subcommand", "argv", "allowed"),
    [
        ("", "ip", ["ip", "1.1.1.1"], True),
        ("0", "scan", ["scan", "x.test", "--json"], True),
        ("1", "ip", ["ip", "1.1.1.1"], False),
        ("true", "ip", ["ip", "1.1.1.1"], False),
        ("", "mcp", ["mcp"], False),
        ("", "update-data", ["update-data"], False),
        ("", "ip", ["ip", "1.1.1.1", "--proxy", "socks5://127.0.0.1:9050"], False),
        ("", "domain", ["domain", "x.test", "--proxy=socks5://127.0.0.1:9050"], False),
    ],
)
def test_when_the_cli_checks_datasets_on_start(monkeypatch, env, subcommand, argv, allowed):
    from osineitor.cli import _auto_update_allowed

    monkeypatch.setenv("OSINEITOR_NO_AUTO_UPDATE", env)
    assert _auto_update_allowed(subcommand, argv) is allowed


def fake_auto_update(monkeypatch, *results: datasets.Result, error: Exception | None = None):
    calls = []

    async def run(http):
        calls.append(http)
        if error:
            raise error
        return list(results)

    monkeypatch.delenv("OSINEITOR_NO_AUTO_UPDATE")
    monkeypatch.setattr(datasets, "auto_update", run)
    monkeypatch.setattr("sys.argv", ["osineitor", "version", "--json"])
    return calls


def test_the_cli_checks_on_start_and_reports_an_update_on_stderr(monkeypatch):
    done = datasets.Result("azure-ip-ranges", "actualizado", version="Tue, 03 Nov 2026")
    calls = fake_auto_update(monkeypatch, done)
    result = runner.invoke(app, ["version", "--json"])
    assert result.exit_code == 0 and len(calls) == 1
    assert json.loads(result.stdout)["version"]  # stdout sigue siendo JSON válido
    assert "azure-ip-ranges actualizado" in result.stderr


def install_azure(published: date) -> None:
    """Azure instalado como lo dejaría `update-data`, con el fichero de la fecha `published`."""
    data = b'["20.33.0.0/16"]'
    datasets._write(datasets.datasets_dir() / "azure-ip-ranges.json", data)
    entry = {
        "filename": "azure-ip-ranges.json",
        "sha256": hashlib.sha256(data).hexdigest(),
        "url": f"{AZURE_BASE}ServiceTags_Public_{published:%Y%m%d}.json",
    }
    datasets._write(
        datasets.datasets_dir() / datasets.MANIFEST,
        json.dumps({"azure-ip-ranges": entry}).encode(),
    )


def test_a_failed_check_is_reported_on_stderr_and_does_not_change_the_command(monkeypatch):
    install_azure(datetime.now(UTC).date() - timedelta(days=3))
    fake_auto_update(monkeypatch, datasets.Result("azure-ip-ranges", "error", "DatasetError: x"))
    result = runner.invoke(app, ["version", "--json"])
    assert result.exit_code == 0 and json.loads(result.stdout)["version"]
    stderr = " ".join(result.stderr.split())  # Rich parte las líneas largas
    assert "no se pudo comprobar azure-ip-ranges (DatasetError: x)" in stderr
    assert "se siguen usando los rangos del" in stderr
    assert stderr.count("Aviso") == 1


def test_a_failed_check_without_ranges_says_there_are_none(monkeypatch):
    fake_auto_update(monkeypatch, datasets.Result("azure-ip-ranges", "error", "sin red"))
    assert "no hay rangos de Azure" in runner.invoke(app, ["version"]).stderr


def test_an_exception_during_the_check_is_reported_and_does_not_break_the_command(monkeypatch):
    fake_auto_update(monkeypatch, error=RuntimeError("config rota"))
    result = runner.invoke(app, ["version", "--json"])
    assert result.exit_code == 0 and json.loads(result.stdout)["version"]
    assert "config rota" in result.stderr


def test_the_check_is_skipped_with_proxy(monkeypatch):
    calls = fake_auto_update(monkeypatch)
    # El callback no ve los argumentos de la orden: los lee de sys.argv.
    monkeypatch.setattr("sys.argv", ["osineitor", "version", "--proxy", "socks5://h:1"])
    runner.invoke(app, ["version"])
    assert calls == []


@pytest.mark.parametrize("proxy", [False, True])
def test_stale_ranges_are_reported_even_when_the_check_already_ran(monkeypatch, proxy):
    install_azure(datetime.now(UTC).date() - timedelta(days=20))
    calls = fake_auto_update(monkeypatch)  # el sello ya es de hoy: no hay resultados
    if proxy:
        monkeypatch.setattr("sys.argv", ["osineitor", "version", "--proxy", "socks5://h:1"])
    result = runner.invoke(app, ["version", "--json"])
    assert result.exit_code == 0 and json.loads(result.stdout)["version"]
    assert "los rangos de IP de Azure son del" in result.stderr
    assert "update-data azure-ip-ranges" in result.stderr
    assert len(calls) == (0 if proxy else 1)


def test_recent_ranges_are_not_reported(monkeypatch):
    install_azure(datetime.now(UTC).date() - timedelta(days=6))
    fake_auto_update(monkeypatch)
    assert runner.invoke(app, ["version"]).stderr == ""


def test_disabling_the_check_also_silences_the_stale_warning(monkeypatch):
    install_azure(datetime.now(UTC).date() - timedelta(days=20))
    calls = fake_auto_update(monkeypatch)
    monkeypatch.setenv("OSINEITOR_NO_AUTO_UPDATE", "1")
    assert runner.invoke(app, ["version"]).stderr == "" and calls == []


def test_a_failed_check_with_stale_ranges_warns_once(monkeypatch):
    install_azure(datetime.now(UTC).date() - timedelta(days=20))
    fake_auto_update(monkeypatch, datasets.Result("azure-ip-ranges", "error", "sin red"))
    stderr = runner.invoke(app, ["version"]).stderr
    assert stderr.count("Aviso") == 1 and "no se pudo comprobar" in stderr
