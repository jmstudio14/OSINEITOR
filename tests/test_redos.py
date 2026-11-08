"""Las expresiones que leen datos del objetivo no tienen coste cuadrático (ReDoS)."""

from __future__ import annotations

import time

import pytest

from osineitor.modules.domain import github_code, http_fingerprint, tech_detect, web_meta
from osineitor.modules.domain.cloud_storage_refs import parse_reference
from osineitor.modules.files import meta

LIMIT = 1.0  # segundos; con los patrones anteriores estas entradas tardaban de segundos a minutos


def _elapsed(fn, *args) -> float:
    start = time.perf_counter()
    fn(*args)
    return time.perf_counter() - start


@pytest.mark.parametrize(
    ("fn", "text"),
    [
        (tech_detect._meta_tags, "<meta " + "a" * 500_000),
        (tech_detect._meta_tags, "<meta " * 80_000),
        (tech_detect.SCRIPT_SRC.findall, "<script " * 62_500),
        (http_fingerprint.TITLE.search, "<title>" * 71_000),
        (web_meta.LOC.findall, "<loc>a" + " " * 1_000_000 + "b"),
        (github_code.find_secrets, "password" + " " * 200_000),
        (github_code.find_secrets, "://" + "a" * 200_000),
        (github_code.find_secrets, "-----BEGIN " + "A " * 100_000),
        (parse_reference, "https://" + "a." * 5_000 + "s3.amazonaws.com/x"),
        (parse_reference, "https://" + "s3." * 5_000 + "amazonaws.com/x"),
    ],
    ids=[
        "meta-atributo",
        "meta-sin-cerrar",
        "script",
        "title",
        "loc",
        "secreto-asignacion",
        "secreto-url",
        "secreto-clave",
        "bucket-host",
        "bucket-endpoint",
    ],
)
def test_html_patterns_are_linear(fn, text):
    assert _elapsed(fn, text) < LIMIT


@pytest.mark.parametrize(
    "head",
    [b"/Title(" * 75_000, b"/Title<0" * 65_000, b"/Title(" + b"\\a" * 260_000],
    ids=["literal", "hex", "escapes"],
)
def test_pdf_info_is_linear(head):
    assert _elapsed(meta.parse_pdf, head, b"") < LIMIT


def test_patterns_still_read_normal_html():
    assert tech_detect._meta_tags('<meta name="generator" content="WordPress 6.4">') == {
        "generator": "WordPress 6.4"
    }
    page = '<script data-src="/x.js" src="/a.js"></script>'
    assert tech_detect.SCRIPT_SRC.findall(page) == ["/a.js"]
    assert http_fingerprint.TITLE.search("<title lang=es>Hola</title>")[1] == "Hola"
    assert web_meta.LOC.findall("<loc> https://a.test/ </loc>") == [" https://a.test/ "]


def test_pdf_last_readable_value_wins():
    head = rb"/Title (Primero) /Author (Ana)"
    tail = rb"/Title (Segundo\) final) /Title (sin cerrar"
    assert meta.parse_pdf(head, tail) == {"title": "Segundo) final", "author": "Ana"}
