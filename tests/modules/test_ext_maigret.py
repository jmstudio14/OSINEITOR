"""Adaptador de Maigret (F5.15): el informe JSON se escribe en un fichero, no en stdout."""

from __future__ import annotations

import json
import shutil
import sys

import pytest

from osineitor.errors import ModuleError, ModuleSkipped
from osineitor.models import Entity, EntityType
from osineitor.modules.username.ext_maigret import ExtMaigret

USER = Entity(type=EntityType.USERNAME, value="ana")
REPORT = {
    "GitHub": {
        "username": "ana",
        "url_user": "https://github.com/ana",
        "status": {"status": "Claimed"},
    },
    "Reddit": {"username": "ana", "url_user": "https://reddit.com/u/ana", "status": "Claimed"},
    "Nada": {"username": "ana", "url_user": "https://nada.test/ana", "status": "Available"},
    "Raro": {"username": "ana", "url_user": "javascript:alert(1)", "status": "Claimed"},
    "Repetido": {"username": "ana", "url_user": "https://github.com/ana", "status": "Claimed"},
}


def fake_maigret(monkeypatch, body: str, exit_code: int = 0):
    """Sustituye el binario por Python: escribe `body` donde Maigret escribiría su informe."""
    script = (
        "import pathlib, sys\n"
        "folder, user = sys.argv[1], sys.argv[2]\n"
        f"pathlib.Path(folder, 'report_' + user + '_simple.json').write_text({body!r})\n"
        f"sys.exit({exit_code})\n"
    )
    monkeypatch.setattr(ExtMaigret, "binary", sys.executable)
    monkeypatch.setattr(ExtMaigret, "min_version", None)
    monkeypatch.setattr(
        ExtMaigret, "args", lambda self, entity, folder: ["-c", script, folder, entity.value]
    )


def test_the_arguments_ask_for_a_simple_report_without_recursion_and_end_with_the_target():
    args = ExtMaigret.args(ExtMaigret(None), USER, "/tmp/informe")
    assert args[args.index("--json") + 1] == "simple"
    assert args[args.index("-fo") + 1] == "/tmp/informe"
    assert "--no-recursion" in args and "--no-extracting" in args
    assert args[-2:] == ["--", "ana"]


async def test_reads_the_claimed_profiles_from_the_report_file(ctx, monkeypatch):
    fake_maigret(monkeypatch, json.dumps(REPORT))
    out = await ExtMaigret(ctx).run(USER)
    assert [(e.type, e.value) for e in out] == [
        (EntityType.PROFILE, "https://github.com/ana"),
        (EntityType.PROFILE, "https://reddit.com/u/ana"),
    ]
    assert out[0].data["site"] == "GitHub" and out[0].data["via"] == "maigret"
    assert "verified" not in out[0].data  # Maigret no confirma que sea la misma persona


async def test_without_the_binary_the_module_is_skipped(ctx, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(ModuleSkipped, match="maigret no está instalado"):
        await ExtMaigret(ctx).run(USER)


async def test_a_missing_report_is_an_error(ctx, monkeypatch):
    fake_maigret(monkeypatch, "{}")
    monkeypatch.setattr(
        ExtMaigret, "args", lambda self, entity, folder: ["-c", "pass", folder, entity.value]
    )
    with pytest.raises(ModuleError, match="informe"):
        await ExtMaigret(ctx).run(USER)


async def test_an_unreadable_report_is_an_error(ctx, monkeypatch):
    fake_maigret(monkeypatch, "esto no es json")
    with pytest.raises(ModuleError):
        await ExtMaigret(ctx).run(USER)


async def test_a_failing_binary_is_an_error(ctx, monkeypatch):
    fake_maigret(monkeypatch, json.dumps(REPORT), exit_code=3)
    with pytest.raises(ModuleError, match="código 3"):
        await ExtMaigret(ctx).run(USER)
