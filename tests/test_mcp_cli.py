"""F10.4: `osineitor mcp` de extremo a extremo, como lo lanzaría un cliente MCP."""

from __future__ import annotations

import json
import subprocess
import sys

from osineitor.models import Entity, EntityType, ScanResult
from osineitor.storage import Storage


def test_mcp_command_speaks_json_rpc_on_stdio_and_prints_nothing_else(tmp_path):
    db = tmp_path / "m.db"
    with Storage(db) as store:
        store.save(ScanResult(target=Entity(type=EntityType.DOMAIN, value="example.com"), depth=1))
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_scans"}},
    ]
    done = subprocess.run(
        [sys.executable, "-m", "osineitor", "mcp", "--db", str(db)],
        input="\n".join(json.dumps(m) for m in messages) + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert done.returncode == 0, done.stderr
    replies = [json.loads(line) for line in done.stdout.splitlines()]
    assert [r["id"] for r in replies] == [1, 2]
    assert replies[0]["result"]["serverInfo"]["name"] == "osineitor"
    scans = json.loads(replies[1]["result"]["content"][0]["text"])["scans"]
    assert scans[0]["target"] == "example.com"
