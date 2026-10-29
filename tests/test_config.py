from __future__ import annotations

import getpass
import os
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from osineitor import config
from osineitor.config import Config, config_dir, config_path, data_dir


def test_directories_honour_the_override_variables(monkeypatch, tmp_path):
    monkeypatch.setenv("OSINEITOR_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("OSINEITOR_DATA_DIR", str(tmp_path / "dat"))
    assert config_dir() == tmp_path / "cfg"
    assert data_dir() == tmp_path / "dat"
    assert config_path() == tmp_path / "cfg" / "config.toml"


def test_default_directories_use_the_platform_standard(monkeypatch):
    monkeypatch.delenv("OSINEITOR_CONFIG_DIR")
    monkeypatch.delenv("OSINEITOR_DATA_DIR")
    for path in (config_dir(), data_dir()):
        assert path.name == "osineitor"
        assert path.is_absolute()
        assert Path.home() in path.parents or path.parent.is_absolute()


def test_save_warns_but_keeps_the_keys_when_chmod_is_not_supported(monkeypatch, tmp_path):
    def refuse(self, mode):
        raise OSError("no soportado")

    monkeypatch.setattr(config, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(Path, "chmod", refuse)
    with pytest.warns(UserWarning, match="No se pudieron restringir"):
        path = Config(keys={"shodan": "abc"}).save(tmp_path / "c.toml")
    assert Config.load(path).keys == {"shodan": "abc"}


def test_save_restricts_the_acl_with_icacls_on_windows(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(config, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(config.getpass, "getuser", lambda: "ana")
    monkeypatch.setattr(config.subprocess, "run", lambda cmd, **kw: calls.append((cmd, kw)))
    path = Config(keys={"shodan": "abc"}).save(tmp_path / "c.toml")
    assert calls == [
        (
            ["icacls", str(path), "/inheritance:r", "/grant:r", "ana:(R,W)"],
            {"check": True, "capture_output": True},
        )
    ]


def test_save_warns_when_icacls_fails(monkeypatch, tmp_path):
    def fail(cmd, **kwargs):
        raise subprocess.CalledProcessError(5, cmd)

    monkeypatch.setattr(config, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(config.subprocess, "run", fail)
    with pytest.warns(UserWarning, match="No se pudieron restringir"):
        path = Config(keys={"shodan": "abc"}).save(tmp_path / "c.toml")
    assert Config.load(path).keys == {"shodan": "abc"}


@pytest.mark.skipif(os.name == "nt", reason="el modo POSIX no aplica en Windows")
@pytest.mark.parametrize("existing", [False, True])
def test_config_file_is_private_on_posix(tmp_path, existing):
    path = tmp_path / "c.toml"
    if existing:
        path.write_text("", encoding="utf-8")
        path.chmod(0o644)
    Config(keys={"shodan": "abc"}).save(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name != "nt", reason="las ACL solo existen en Windows")
def test_config_file_acl_is_limited_to_the_current_user_on_windows(tmp_path):
    path = Config(keys={"shodan": "abc"}).save(tmp_path / "c.toml")
    acl = subprocess.run(["icacls", str(path)], check=True, capture_output=True, text=True).stdout
    assert getpass.getuser().lower() in acl.lower()
    for other in ("Everyone", "BUILTIN\\Users", "Authenticated Users"):
        assert other not in acl


def test_config_is_written_as_utf8(tmp_path):
    path = Config(keys={"x": "ñandú"}).save(tmp_path / "c.toml")
    assert "ñandú" in path.read_text(encoding="utf-8")
    assert Config.load(path).keys["x"] == "ñandú"
