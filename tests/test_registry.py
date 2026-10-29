from __future__ import annotations

import sys

from osineitor import registry
from osineitor.modules._manifest import MODULES


def test_manifest_matches_modules_on_disk():
    """Empaquetado se usa el manifiesto: si no coincide con el disco, faltarían módulos."""
    assert sorted(MODULES) == registry.module_files()


def test_frozen_discovery_uses_manifest(monkeypatch):
    on_disk = [m.name for m in registry.discover()]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert registry.module_files() == list(MODULES)
    assert [m.name for m in registry.discover()] == on_disk
