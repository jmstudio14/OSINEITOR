from __future__ import annotations

import pytest

from osineitor_gui.events import ScanStart
from osineitor_gui.process import CliProcess
from osineitor_gui.scan_request import (
    ConfirmationRequired,
    InvalidRequest,
    ScanRequest,
    detect_kind,
)
from tests.gui.fakecli import CLI, driver_env


def test_auto_scan_pivots_by_default():
    assert ScanRequest("example.com").to_args() == [
        "--no-color",
        "scan",
        "--depth",
        "2",
        "--ndjson",
        "--control-stdin",
        "--",
        "example.com",
    ]


def test_explicit_kind_and_all_options():
    request = ScanRequest(
        " 1.1.1.1 ",
        kind="ip",
        depth=3,
        modules=("ipinfo", "internetdb"),
        max_entities=0,
        max_requests=500,
        max_time=2.5,
        no_cache=True,
        no_save=True,
    )
    assert request.to_args() == [
        "--no-color",
        "ip",
        "--depth",
        "3",
        "--ndjson",
        "--control-stdin",
        "-m",
        "ipinfo",
        "-m",
        "internetdb",
        "--max-entities",
        "0",
        "--max-requests",
        "500",
        "--max-time",
        "2.5",
        "--no-cache",
        "--no-save",
        "--",
        "1.1.1.1",
    ]


def test_risky_options_need_explicit_confirmation():
    with pytest.raises(ConfirmationRequired, match="activos"):
        ScanRequest("example.com", active=True).to_args()
    with pytest.raises(ConfirmationRequired, match="privadas"):
        ScanRequest("10.0.0.1", kind="ip", allow_private=True).to_args()
    args = ScanRequest("example.com", active=True, confirm_active=True).to_args()
    assert "--active" in args
    # Confirmar una opción no confirma la otra.
    with pytest.raises(ConfirmationRequired):
        ScanRequest("x", active=True, confirm_active=True, allow_private=True).to_args()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"target": "   "},
        {"target": "x", "kind": "otra"},
        {"target": "x", "depth": 0},
        {"target": "x", "depth": 5},
        {"target": "x", "modules": ("dns; rm -rf",)},
        {"target": "x", "modules": ("--active",)},
        {"target": "x", "max_time": -1},
        {"target": "x", "no_cache": True, "refresh": True},
    ],
)
def test_invalid_requests(kwargs):
    with pytest.raises(InvalidRequest):
        ScanRequest(**kwargs).to_args()


def test_a_target_starting_with_a_dash_is_not_an_option():
    """Sin `--` antes del objetivo, «--active» se leería como la opción y no como un username."""
    args = ScanRequest("--active", kind="username", no_save=True).to_args()
    assert args[-2:] == ["--", "--active"]
    seen = []
    proc = CliProcess(args, cli=CLI, env=driver_env("fast"), on_event=seen.append)
    proc.start()
    assert proc.wait(30) == 0
    start = next(e for e in seen if isinstance(e, ScanStart))
    assert (start.target_type, start.target_value) == ("username", "--active")


def test_detect_kind_matches_the_cli():
    assert detect_kind("example.com") == "domain"
    assert detect_kind("1.1.1.1") == "ip"
    assert detect_kind("alguien@example.com") == "email"
    assert detect_kind("johndoe") == "username"
