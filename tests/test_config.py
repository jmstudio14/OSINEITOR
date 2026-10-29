from __future__ import annotations

from pathlib import Path

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


def test_save_works_when_chmod_is_not_supported(monkeypatch, tmp_path):
    def refuse(self, mode):
        raise OSError("no soportado")

    monkeypatch.setattr(Path, "chmod", refuse)
    path = Config(keys={"shodan": "abc"}).save(tmp_path / "c.toml")
    assert Config.load(path).keys == {"shodan": "abc"}


def test_config_is_written_as_utf8(tmp_path):
    path = Config(keys={"x": "ñandú"}).save(tmp_path / "c.toml")
    assert "ñandú" in path.read_text(encoding="utf-8")
    assert Config.load(path).keys["x"] == "ñandú"
