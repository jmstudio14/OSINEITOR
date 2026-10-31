"""F3.5: `osineitor update-data` y el registro de datasets (versión, hash y licencia)."""

from __future__ import annotations

import hashlib
import json

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
