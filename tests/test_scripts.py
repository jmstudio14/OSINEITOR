"""Tests de las funciones puras de scripts/ (sin red)."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rdap = load_script("rdap_coverage")
baseline = load_script("fp_baseline")

BOOTSTRAP = {
    "publication": "2026-10-28T22:00:04Z",
    "services": [
        [["COM", "net"], ["https://rdap.verisign.com/com/v1/"]],
        [["fr"], ["https://rdap.nic.fr/"]],
    ],
}


def test_tld_servers_lowercases_and_flattens():
    servers = rdap.tld_servers(BOOTSTRAP)
    assert set(servers) == {"com", "net", "fr"}
    assert servers["com"] == ["https://rdap.verisign.com/com/v1/"]


def test_rdap_report_marks_missing_tlds():
    text = rdap.render(BOOTSTRAP, "prueba")
    assert "**Fuente:** prueba" in text
    assert "**TLD con servidor RDAP:** 3" in text
    assert "| `.fr` | sí | https://rdap.nic.fr/ |" in text
    assert "| `.es` | **no** | - |" in text
    assert "<summary>Los 3 TLD con RDAP</summary>" in text


def test_rdap_main_writes_file(tmp_path, capsys):
    source = tmp_path / "dns.json"
    source.write_text('{"publication": "x", "services": [[["es"], ["https://r.example/"]]]}')
    out = tmp_path / "salida.md"
    assert rdap.main(["--input", str(source), "--output", str(out)]) == 0
    assert "| `.es` | sí | https://r.example/ |" in out.read_text(encoding="utf-8")
    assert "copia local `dns.json`" in out.read_text(encoding="utf-8")


def test_random_username_is_valid_and_unique():
    names = {baseline.random_username() for _ in range(50)}
    assert len(names) == 50
    for name in names:
        assert re.fullmatch(r"[a-z][a-z0-9]{13}", name)


def test_evaluable_sites_respects_regex_check():
    everything = baseline.evaluable_sites("abcdefghijklmn")
    narrow = baseline.evaluable_sites("a")
    assert len(narrow) < len(everything)


def test_summarize_rate_and_systematic_sites():
    found = {"u1": ["A", "B"], "u2": ["A"], "u3": ["A", "C"]}
    summary = baseline.summarize(found, {"u1": 100, "u2": 100, "u3": 100})
    assert summary["checks"] == 300
    assert summary["false_positives"] == 5
    assert summary["rate"] == pytest.approx(5 / 300)
    assert summary["systematic"] == ["A"]
    assert summary["by_site"][0] == ("A", 3)


def test_summarize_with_no_data_does_not_divide_by_zero():
    assert baseline.summarize({}, {})["rate"] == 0.0


def test_baseline_report():
    summary = baseline.summarize({"u1": ["A"], "u2": ["A"]}, {"u1": 10, "u2": 10})
    text = baseline.render(summary)
    assert "**Tasa:** 10.00%" in text
    assert "| A | 2 |" in text
    assert "error sistemático" in text
    clean = baseline.render(baseline.summarize({"u1": []}, {"u1": 10}))
    assert "Ninguno." in clean
