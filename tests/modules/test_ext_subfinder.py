from __future__ import annotations

import json
import shutil
import sys

import pytest

from osineitor.errors import ModuleSkipped
from osineitor.models import Entity, EntityType
from osineitor.modules.domain.ext_subfinder import ExtSubfinder

DOMAIN = Entity(type=EntityType.DOMAIN, value="example.com")
LINES = [
    {"host": "www.example.com", "input": "example.com", "source": ["crtsh", "alienvault"]},
    {"host": "WWW.example.com", "input": "example.com", "source": ["hackertarget"]},
    {"host": "api.example.com", "input": "example.com", "source": "crtsh"},
    {"host": "evil.test", "input": "example.com", "source": ["crtsh"]},
    {"host": "example.com", "input": "example.com", "source": ["crtsh"]},
    {"host": "no valid", "source": []},
    "no es un objeto",
]


def test_the_arguments_are_passive_and_end_the_target_as_an_option_value():
    args = ExtSubfinder.args(ExtSubfinder(None), DOMAIN)
    assert args == ["-d", "example.com", "-silent", "-json"]
    assert "-active" not in args


def test_parse_keeps_only_subdomains_of_the_target_and_merges_sources():
    out = ExtSubfinder(None).parse(DOMAIN, LINES)
    assert [(e.value, e.data) for e in out] == [
        ("api.example.com", {"subdomain": True, "sources": ["crtsh"]}),
        (
            "www.example.com",
            {"subdomain": True, "sources": ["alienvault", "crtsh", "hackertarget"]},
        ),
    ]


async def test_without_the_binary_the_module_is_skipped(ctx, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert ExtSubfinder.unavailable() == "subfinder no está instalado"
    with pytest.raises(ModuleSkipped, match="no está instalado"):
        await ExtSubfinder(ctx).run(DOMAIN)


async def test_runs_the_binary_and_parses_its_ndjson(ctx, monkeypatch):
    script = "import sys\nfor line in sys.argv[1:]:\n    print(line)\n"
    payload = [json.dumps(LINES[0]), json.dumps(LINES[3])]

    monkeypatch.setattr(ExtSubfinder, "binary", sys.executable)
    monkeypatch.setattr(ExtSubfinder, "min_version", None)
    monkeypatch.setattr(ExtSubfinder, "args", lambda self, entity: ["-c", script, *payload])
    out = await ExtSubfinder(ctx).run(DOMAIN)
    assert [e.value for e in out] == ["www.example.com"]


def test_only_the_investigated_domain_is_accepted():
    sub = Entity(type=EntityType.DOMAIN, value="a.example.com", data={"subdomain": True})
    assert ExtSubfinder(None).accepts(DOMAIN)
    assert not ExtSubfinder(None).accepts(sub)
