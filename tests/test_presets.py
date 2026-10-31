"""F3.2: presets de escaneo (`--preset` y `osineitor presets`)."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from osineitor import presets, registry
from osineitor.cli import app
from osineitor.models import EntityType
from tests.test_cli import fake_module, use_modules

runner = CliRunner()
BUILTIN = {"passive", "quick", "domain-recon", "attack-surface", "person", "email-audit", "full"}


def write_preset(name: str, text: str):
    path = presets.user_dir() / f"{name}.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def scan_start(output: str) -> dict:
    events = [json.loads(line) for line in output.splitlines() if line.startswith("{")]
    return next(e for e in events if e["type"] == "scan.start")


@pytest.fixture
def modules(monkeypatch):
    use_modules(
        monkeypatch,
        [
            fake_module("fake_dns", {EntityType.DOMAIN}, EntityType.IP, "9.9.9.9"),
            fake_module("fake_whois", {EntityType.DOMAIN}, EntityType.RECORD, "w:1"),
            fake_module(
                "fake_active", {EntityType.DOMAIN}, EntityType.RECORD, "a:1", passive=False
            ),
        ],
    )


# --- los incluidos ----------------------------------------------------------------------------


def test_the_seven_builtin_presets_load_without_errors():
    found, errors = presets.load_all()
    assert not errors
    assert set(found) >= BUILTIN
    assert {found[n].source for n in BUILTIN} == {"incluido"}


def test_every_module_named_by_a_builtin_preset_exists():
    real = {m.name for m in registry.discover()}
    found, _ = presets.load_all()
    for name in BUILTIN:
        assert set(found[name].modules or ()) <= real, name


def test_only_the_preset_that_says_so_admits_active_modules():
    found, _ = presets.load_all()
    assert {n for n in BUILTIN if found[n].allow_active} == {"attack-surface", "full"}


def test_the_presets_command_lists_them(modules):
    out = runner.invoke(app, ["presets", "--json"])
    assert out.exit_code == 0, out.output
    data = json.loads(out.output)
    assert {p["name"] for p in data["presets"]} >= BUILTIN
    assert data["errors"] == []
    table = runner.invoke(app, ["presets"])
    assert table.exit_code == 0 and "domain-recon" in table.output


# --- los del usuario --------------------------------------------------------------------------


def test_a_user_preset_overrides_a_builtin_and_can_add_new_ones():
    write_preset("quick", "description: Mío\ndepth: 3\nmodules: [dns]\n")
    write_preset("mio", "description: Otro\n")
    found, errors = presets.load_all()
    assert not errors
    assert (found["quick"].source, found["quick"].depth, found["quick"].modules) == (
        "usuario (sobrescribe)",
        3,
        ("dns",),
    )
    assert found["mio"].source == "usuario"
    assert found["passive"].source == "incluido"


@pytest.mark.parametrize(
    "text",
    [
        "depth: 5",
        "depth: 2.0",
        "depth: true",
        "modules: []",
        "modules: [Dns]",
        "modules: dns",
        "allow_active: sí",
        "max_requests: -1",
        "max_requests: 1.5",
        "max_time: -3",
        "max_time: true",
        "color: rojo",
        "- una\n- lista",
        "depth: [",
    ],
)
def test_an_invalid_user_preset_is_reported_not_ignored(text):
    write_preset("roto", text)
    found, errors = presets.load_all()
    assert "roto" in errors and "roto" not in found
    assert set(found) >= BUILTIN  # los demás siguen disponibles
    with pytest.raises(presets.PresetError, match="roto"):
        presets.get("roto")


def test_a_broken_override_does_not_fall_back_to_the_builtin():
    write_preset("quick", "depth: 9")
    with pytest.raises(presets.PresetError):
        presets.get("quick")


def test_a_preset_file_needs_a_clean_name():
    write_preset("Mi Preset", "depth: 1")
    _, errors = presets.load_all()
    assert "Mi Preset" in errors


def test_the_presets_command_fails_when_a_user_file_is_broken():
    write_preset("roto", "depth: 9")
    done = runner.invoke(app, ["presets"])
    assert done.exit_code == 2 and "roto" in done.output


# --- --preset en un scan ----------------------------------------------------------------------


def test_a_preset_fixes_modules_depth_and_budget(modules):
    write_preset(
        "mio",
        "depth: 3\nmodules: [fake_dns]\nmax_entities: 7\nmax_requests: 8\nmax_time: 9\n",
    )
    done = runner.invoke(app, ["domain", "example.com", "--preset", "mio", "--ndjson", "--no-save"])
    assert done.exit_code == 0, done.output
    start = scan_start(done.output)
    assert start["depth"] == 3
    assert start["modules"] == ["fake_dns"]
    assert start["budget"] == {"max_entities": 7, "max_requests": 8, "max_seconds": 9}


def test_what_the_user_types_beats_the_preset(modules):
    write_preset("mio", "depth: 3\nmodules: [fake_dns]\nmax_requests: 8\n")
    args = ["--preset", "mio", "--depth", "2", "-m", "fake_whois", "--max-requests", "50"]
    done = runner.invoke(app, ["domain", "example.com", *args, "--ndjson", "--no-save"])
    start = scan_start(done.output)
    assert (start["depth"], start["modules"], start["budget"]["max_requests"]) == (
        2,
        ["fake_whois"],
        50,
    )


def test_a_preset_overrides_the_default_depth_of_scan(modules):
    write_preset("uno", "depth: 1\n")
    done = runner.invoke(app, ["scan", "example.com", "--preset", "uno", "--ndjson", "--no-save"])
    assert scan_start(done.output)["depth"] == 1


def test_a_preset_without_modules_runs_all_of_them(modules):
    write_preset("todo", "depth: 1\n")
    done = runner.invoke(
        app, ["domain", "example.com", "--preset", "todo", "--ndjson", "--no-save"]
    )
    assert scan_start(done.output)["modules"] == ["fake_dns", "fake_whois"]


def test_a_preset_never_turns_active_modules_on_by_itself(modules):
    write_preset("act", "allow_active: true\ndepth: 1\n")
    done = runner.invoke(app, ["domain", "example.com", "--preset", "act", "--ndjson", "--no-save"])
    start = scan_start(done.output)
    assert "fake_active" not in start["modules"]
    assert [s["module"] for s in start["skipped"]] == ["fake_active"]
    with_flag = runner.invoke(
        app, ["domain", "example.com", "--preset", "act", "--active", "--ndjson", "--no-save"]
    )
    assert "fake_active" in scan_start(with_flag.output)["modules"]


def test_active_with_a_preset_that_forbids_it_is_a_usage_error(modules):
    done = runner.invoke(app, ["domain", "example.com", "--preset", "passive", "--active"])
    assert done.exit_code == 2
    assert "no admite módulos activos" in done.output


def test_an_unknown_preset_lists_the_available_ones(modules):
    done = runner.invoke(app, ["domain", "example.com", "--preset", "nada"])
    assert done.exit_code == 2
    assert "preset desconocido" in done.output and "quick" in done.output


def test_a_preset_naming_an_unknown_module_is_a_usage_error(modules):
    write_preset("mal", "modules: [no_existe]\n")
    done = runner.invoke(app, ["domain", "example.com", "--preset", "mal"])
    assert done.exit_code == 2
    assert "no_existe" in done.output
