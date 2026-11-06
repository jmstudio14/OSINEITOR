"""Agrupación de módulos por API key (capa sin Qt)."""

from __future__ import annotations

from osineitor_gui.keys import KeyRow, group_keys
from tests.test_contract import validate


def module(name: str, key: str | None, configured: bool = False) -> dict:
    return {
        "name": name,
        "description": "",
        "consumes": [],
        "produces": [],
        "passive": True,
        "analyzer": False,
        "plugin": False,
        "requires_key": key,
        "key_configured": configured,
        "timeout": 30,
    }


def test_modules_without_key_are_ignored():
    assert group_keys([module("dns", None), module("rdap", None)]) == []


def test_modules_sharing_a_key_make_one_row():
    rows = group_keys([module("hibp_pastes", "hibp"), module("hibp", "hibp")])
    assert rows == [KeyRow("hibp", ("hibp", "hibp_pastes"), False)]


def test_rows_are_sorted_by_key_name():
    rows = group_keys([module("a", "shodan"), module("b", "abuseipdb"), module("c", "hibp")])
    assert [row.name for row in rows] == ["abuseipdb", "hibp", "shodan"]


def test_configured_needs_every_module_configured():
    both = group_keys([module("a", "hibp", True), module("b", "hibp", True)])
    one = group_keys([module("a", "hibp", True), module("b", "hibp", False)])
    assert both[0].configured is True and one[0].configured is False


def test_input_validates_against_the_contract():
    modules = [module("hibp", "hibp", True), module("dns", None)]
    validate("modules_output", modules)
    assert [row.name for row in group_keys(modules)] == ["hibp"]
