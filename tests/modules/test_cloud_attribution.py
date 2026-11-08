"""F4.17: `cloud_attribution` etiqueta CDN y nube por CNAME, huella HTTP y rangos de IP."""

from __future__ import annotations

import hashlib
import json

from osineitor import datasets
from osineitor.models import Entity, EntityType
from osineitor.modules.domain.cloud_attribution import RANGE_DATASETS, CloudAttribution


def install(name: str, networks: list[str]) -> None:
    """Deja instalado un dataset de rangos como lo haría `update-data`."""
    data = json.dumps(networks).encode()
    datasets._write(datasets.datasets_dir() / f"{name}.json", data)
    entries = datasets.manifest()
    entries[name] = {"filename": f"{name}.json", "sha256": hashlib.sha256(data).hexdigest()}
    datasets._write(datasets.datasets_dir() / datasets.MANIFEST, json.dumps(entries).encode())


def ip(value: str) -> Entity:
    return Entity(type=EntityType.IP, value=value)


async def attribution(ctx, entity: Entity) -> dict[str, dict]:
    return {e.value: e.data for e in await CloudAttribution(ctx).run(entity)}


async def test_an_ip_inside_a_provider_range_is_labelled(ctx):
    install("aws-ip-ranges", ["3.0.0.0/15", "2600:1f00::/24"])
    install("gcp-ip-ranges", ["34.64.0.0/10"])
    install("cloudflare-ips-v4", ["104.16.0.0/13"])
    install("cloudflare-ips-v6", ["2606:4700::/32"])
    assert await attribution(ctx, ip("3.1.2.3")) == {
        "Amazon Web Services": {
            "category": "cloud",
            "evidence": ["IP 3.1.2.3 en 3.0.0.0/15"],
            "signatures": 1,
        }
    }
    assert set(await attribution(ctx, ip("2600:1f00::1"))) == {"Amazon Web Services"}
    assert set(await attribution(ctx, ip("34.100.0.1"))) == {"Google Cloud"}
    install("azure-ip-ranges", ["20.33.0.0/16"])
    azure = await attribution(ctx, ip("20.33.1.2"))
    assert azure == {
        "Microsoft Azure": {
            "category": "cloud",
            "evidence": ["IP 20.33.1.2 en 20.33.0.0/16"],
            "signatures": 1,
        }
    }
    cloudflare = await attribution(ctx, ip("104.17.0.1"))
    assert cloudflare["Cloudflare"]["category"] == "cdn"
    assert set(await attribution(ctx, ip("2606:4700::1111"))) == {"Cloudflare"}


async def test_an_ip_outside_every_range_gets_nothing(ctx):
    install("aws-ip-ranges", ["3.0.0.0/15"])
    install("cloudflare-ips-v6", ["2606:4700::/32"])
    assert await attribution(ctx, ip("8.8.8.8")) == {}
    assert await attribution(ctx, ip("2001:db8::1")) == {}


async def test_without_installed_datasets_an_ip_gets_nothing_and_nothing_fails(ctx):
    assert await attribution(ctx, ip("3.1.2.3")) == {}


async def test_a_dataset_that_does_not_match_its_hash_is_ignored(ctx):
    install("aws-ip-ranges", ["3.0.0.0/15"])
    (datasets.datasets_dir() / "aws-ip-ranges.json").write_text('["0.0.0.0/0"]', encoding="utf-8")
    assert await attribution(ctx, ip("3.1.2.3")) == {}


async def test_one_instance_reads_the_datasets_once(ctx, monkeypatch):
    install("aws-ip-ranges", ["3.0.0.0/15"])
    module = CloudAttribution(ctx)
    await module.run(ip("3.1.2.3"))
    monkeypatch.setattr(datasets, "installed_path", lambda name: 1 / 0)
    assert [e.value for e in await module.run(ip("3.1.2.4"))] == ["Amazon Web Services"]


async def test_the_cloudflare_cname_and_its_ranges_share_the_provider_name(ctx):
    install("cloudflare-ips-v4", ["104.16.0.0/13"])
    by_ip = await attribution(ctx, ip("104.17.0.1"))
    record = Entity(
        type=EntityType.RECORD, value="dns:x.test", data={"CNAME": ["x.cdn.cloudflare.net."]}
    )
    by_cname = await attribution(ctx, record)
    assert set(by_ip) == set(by_cname) == {"Cloudflare"}


async def test_cname_and_http_fingerprint_still_work(ctx):
    dns = Entity(
        type=EntityType.RECORD,
        value="dns:x.test",
        data={"CNAME": ["d1.CLOUDFRONT.net.", "app.herokuapp.com"]},
    )
    found = await attribution(ctx, dns)
    assert {name: d["category"] for name, d in found.items()} == {
        "Amazon CloudFront": "cdn",
        "Heroku": "cloud",
    }
    assert found["Amazon CloudFront"]["evidence"] == ["CNAME d1.cloudfront.net"]
    http = Entity(
        type=EntityType.RECORD, value="http:x.test", data={"technologies": ["AWS CloudFront"]}
    )
    assert (await attribution(ctx, http))["Amazon CloudFront"]["evidence"] == ["huella HTTP"]


def test_it_reads_ips_and_dns_or_http_records_only(ctx):
    module = CloudAttribution(ctx)
    assert module.accepts(ip("1.1.1.1")) and module.accepts(ip("2606:4700::1"))
    assert module.accepts(Entity(type=EntityType.RECORD, value="dns:x.test"))
    assert module.accepts(Entity(type=EntityType.RECORD, value="http:x.test"))
    assert not module.accepts(Entity(type=EntityType.RECORD, value="rdap:x.test"))
    assert not module.accepts(Entity(type=EntityType.DOMAIN, value="x.test"))


def test_every_range_dataset_is_in_the_catalog():
    catalog = {d.name for d in datasets.CATALOG}
    assert {name for _, _, names in RANGE_DATASETS for name in names} <= catalog
