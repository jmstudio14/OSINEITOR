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


def test_sources_with_a_documented_rate_limit_declare_it():
    """F1.6: el límite oficial de cada fuente va en el módulo; el cliente HTTP lo respeta."""
    from osineitor.registry import discover

    modules = {cls.name: cls for cls in discover()}
    documented = {
        "shodan": 1.0,  # ~1 petición/s por key
        "hibp": 12.0,  # 10/min en el plan más bajo, repartidos con hibp_pastes
        "hibp_pastes": 12.0,
        "hunter_verify": 0.1,  # 10/s
        "hunter_domain": 0.1,  # 15/s
        "wayback": 1.0,  # CDX: 60/min
        "crtsh": 1.0,
    }
    for name, minimum in documented.items():
        assert modules[name].min_interval >= minimum, name
