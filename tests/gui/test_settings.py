from __future__ import annotations

import json

from osineitor_gui.legal import LEGAL_VERSION
from osineitor_gui.settings import GuiSettings, settings_dir


def test_defaults_when_there_is_no_file(tmp_path):
    settings = GuiSettings.load(tmp_path / "nope.json")
    assert settings == GuiSettings()
    assert settings.needs_legal


def test_roundtrip(tmp_path):
    path = tmp_path / "sub" / "settings.json"
    settings = GuiSettings(theme="dark", last_kind="ip", last_export_dir="C:\\informes")
    settings.accept_legal()
    settings.save(path)
    loaded = GuiSettings.load(path)
    assert loaded == settings and not loaded.needs_legal and loaded.legal_accepted == LEGAL_VERSION
    assert not list(path.parent.glob("*.tmp"))  # sin restos del guardado atómico


def test_corrupt_or_hand_edited_files_do_not_break_startup(tmp_path):
    path = tmp_path / "settings.json"
    for content in ("{no es json", "[1, 2]", "", '"texto"'):
        path.write_text(content, encoding="utf-8")
        assert GuiSettings.load(path) == GuiSettings()
    path.write_text(
        json.dumps({"theme": "neon", "legal_accepted": "sí", "last_kind": 3}), encoding="utf-8"
    )
    loaded = GuiSettings.load(path)
    assert (loaded.theme, loaded.legal_accepted, loaded.last_kind) == ("system", 0, "auto")


def test_a_new_legal_version_asks_again():
    settings = GuiSettings(legal_accepted=LEGAL_VERSION - 1)
    assert settings.needs_legal
    settings.accept_legal()
    assert not settings.needs_legal


def test_directory_override(tmp_path, monkeypatch):
    monkeypatch.setenv("OSINEITOR_GUI_CONFIG_DIR", str(tmp_path / "gui"))
    assert settings_dir() == tmp_path / "gui"
