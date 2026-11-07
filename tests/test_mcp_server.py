"""F10.4: servidor MCP por stdio, de solo lectura salvo el scan pasivo."""

from __future__ import annotations

import io
import json

import pytest

from osineitor import mcp_server
from osineitor.mcp_server import McpServer
from osineitor.models import Entity, EntityType, ScanResult
from osineitor.storage import Storage

SEED = Entity(type=EntityType.DOMAIN, value="example.com")


def ent(kind, value, parent=SEED, **data) -> Entity:
    return Entity(type=kind, value=value, parent=parent.key, source="fake", data=data)


@pytest.fixture
def server(tmp_path):
    db = tmp_path / "m.db"
    with Storage(db) as store:
        dns = ent(EntityType.RECORD, "dns:example.com")
        store.save(
            ScanResult(
                target=SEED,
                depth=1,
                entities=[
                    ent(EntityType.IP, "203.0.113.7", secret="x" * 5000),
                    dns,
                    Entity(
                        type=EntityType.FINDING,
                        value="spf: example.com",
                        parent=dns.key,
                        data={
                            "rule": "spf",
                            "title": "SPF permisivo",
                            "severity": "high",
                            "recommendation": "Usad -all",
                            "affected": [dns.key],
                        },
                    ),
                ],
            )
        )
    return McpServer(db)


def rpc(server, method, params=None, id=1):
    msg = {"jsonrpc": "2.0", "method": method, "id": id}
    if params is not None:
        msg["params"] = params
    return server.handle(msg)


def call(server, name, arguments=None):
    reply = rpc(server, "tools/call", {"name": name, "arguments": arguments or {}})
    return reply["result"]


def payload(result):
    assert result["isError"] is False, result
    return json.loads(result["content"][0]["text"])


def test_initialize_negotiates_version_and_declares_only_tools(server):
    reply = rpc(server, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})
    result = reply["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert list(result["capabilities"]) == ["tools"]
    assert result["serverInfo"]["name"] == "osineitor"
    assert "no son fiables" in result["instructions"]
    old = rpc(server, "initialize", {"protocolVersion": "1999-01-01"})["result"]
    assert old["protocolVersion"] == mcp_server.PROTOCOL_VERSIONS[0]


def test_notifications_get_no_reply_and_ping_works(server):
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert rpc(server, "ping")["result"] == {}


def test_unknown_method_and_bad_requests(server):
    assert rpc(server, "nope")["error"]["code"] == -32601
    assert server.handle([{"jsonrpc": "2.0", "method": "ping", "id": 1}])["error"]["code"] == -32600
    assert server.handle({"jsonrpc": "2.0", "id": 3})["error"]["code"] == -32600
    assert rpc(server, "tools/call", {"name": "nope"})["error"]["code"] == -32602
    assert rpc(server, "tools/call", {})["error"]["code"] == -32602


def test_tools_list_has_schemas_and_no_way_to_ask_for_active_modules(server):
    tools = rpc(server, "tools/list")["result"]["tools"]
    names = {t["name"] for t in tools}
    assert names == {
        "list_scans",
        "get_scan",
        "get_entity",
        "get_findings",
        "search",
        "suggest_pivots",
        "run_passive_scan",
    }
    for tool in tools:
        assert tool["inputSchema"]["type"] == "object" and tool["description"]
        assert "active" not in tool["inputSchema"].get("properties", {})
    read_only = {t["name"]: t["annotations"]["readOnlyHint"] for t in tools}
    assert read_only["run_passive_scan"] is False and read_only["get_scan"] is True


def test_list_scans_get_scan_and_entity(server):
    [row] = payload(call(server, "list_scans"))["scans"]
    assert row["id"] == 1 and row["target"] == "example.com"
    scan = payload(call(server, "get_scan", {"scan_id": 1}))
    assert scan["counts"] == {"finding": 1, "ip": 1, "record": 1}
    assert all("data" not in e for e in scan["entities"])  # el detalle va aparte
    only = payload(call(server, "get_scan", {"scan_id": 1, "types": ["ip"], "limit": 1}))
    assert [e["type"] for e in only["entities"]] == ["ip"]
    full = payload(call(server, "get_entity", {"scan_id": 1, "key": "ip:203.0.113.7"}))
    assert len(full["data"]["secret"]) <= mcp_server.MAX_TEXT + 1  # el texto largo se recorta


def test_findings_and_search(server):
    [finding] = payload(call(server, "get_findings", {"scan_id": 1}))["findings"]
    assert finding["severity"] == "high" and finding["recommendation"] == "Usad -all"
    hits = payload(call(server, "search", {"value": "203.0.113.7"}))["results"]
    assert hits and hits[0]["scan_id"] == 1
    assert payload(call(server, "search", {"value": "zzz"}))["results"] == []


def test_suggest_pivots_only_proposes(server, monkeypatch):
    monkeypatch.setattr(mcp_server.registry, "discover", lambda: [])
    assert payload(call(server, "suggest_pivots", {"scan_id": 1}))["suggestions"] == []


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("get_scan", {"scan_id": 99}),
        ("get_scan", {"scan_id": "uno"}),
        ("get_scan", {}),
        ("get_scan", {"scan_id": 1, "limit": 10**6}),
        ("get_entity", {"scan_id": 1, "key": "ip:9.9.9.9"}),
        ("search", {"value": ""}),
        ("run_passive_scan", {"target": ""}),
        ("run_passive_scan", {"target": "example.com", "depth": 9}),
        ("run_passive_scan", {"target": "example.com", "active": True}),
        ("run_passive_scan", {"target": "example.com", "modules": "dns"}),
    ],
)
def test_bad_arguments_are_tool_errors_not_crashes(server, tool, args):
    result = call(server, tool, args)
    assert result["isError"] is True and result["content"][0]["type"] == "text"


def test_local_files_are_refused_and_never_reach_the_scanner(server, monkeypatch, tmp_path):
    def boom(**kwargs):
        raise AssertionError("no debe llegar al Scanner")

    monkeypatch.setattr(mcp_server, "Scanner", boom)
    secret = tmp_path / "secreto.txt"
    secret.write_text("x", encoding="utf-8")
    result = call(server, "run_passive_scan", {"target": str(secret)})
    assert result["isError"] is True and "ficheros locales" in result["content"][0]["text"]


def test_passive_scan_never_activates_active_modules_and_saves(server, monkeypatch):
    seen = {}

    class FakeScanner:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        def scan(self, target, type=None):
            return ScanResult(
                target=Entity(type=EntityType.DOMAIN, value=target),
                depth=seen["depth"],
                entities=[ent(EntityType.IP, "203.0.113.9")],
            )

    monkeypatch.setattr(mcp_server, "Scanner", FakeScanner)
    out = payload(call(server, "run_passive_scan", {"target": "example.org", "depth": 2}))
    assert seen["active"] is False and seen["depth"] == 2
    assert seen["max_seconds"] <= mcp_server.MAX_SCAN_SECONDS
    assert out["scan_id"] == 2 and out["status"] == "complete" and out["entities"] == 1
    assert payload(call(server, "get_scan", {"scan_id": 2}))["target"] == "domain:example.org"


def test_scan_input_errors_come_back_as_tool_errors(server, monkeypatch):
    from osineitor.scanner import ScanInputError

    class Refuses:
        def __init__(self, **kwargs): ...

        def scan(self, target, type=None):
            raise ScanInputError("fuera del alcance")

    monkeypatch.setattr(mcp_server, "Scanner", Refuses)
    result = call(server, "run_passive_scan", {"target": "example.org"})
    assert result["isError"] is True and "fuera del alcance" in result["content"][0]["text"]


def test_stdio_loop_answers_line_by_line_and_survives_garbage(server):
    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}),
        "esto no es json",
        "",
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
    ]
    out = io.StringIO()
    mcp_server.serve(server, io.StringIO("\n".join(lines) + "\n"), out)
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [r.get("id") for r in replies] == [1, None, 2]
    assert replies[1]["error"]["code"] == -32700
    assert all("\n" not in line for line in out.getvalue().splitlines())
