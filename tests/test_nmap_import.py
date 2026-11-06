"""Importación de un XML de Nmap (`osineitor import nmap`): solo lectura local, sin red."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from osineitor import nmap_import
from osineitor.cli import app
from osineitor.models import EntityType
from osineitor.nmap_import import NmapImportError, parse_nmap
from osineitor.storage import Storage

runner = CliRunner()

XML = """<?xml version="1.0"?>
<nmaprun scanner="nmap" args="nmap -sV --script-args pass=secreto 192.0.2.10" version="7.94">
<host><status state="up" reason="syn-ack"/>
<address addr="192.0.2.10" addrtype="ipv4"/>
<address addr="00:11:22:33:44:55" addrtype="mac"/>
<hostnames>
<hostname name="WWW.Example.com" type="PTR"/>
<hostname name="no es un host" type="user"/>
</hostnames>
<ports>
<port protocol="tcp" portid="22"><state state="open" reason="syn-ack"/>
<service name="ssh" product="OpenSSH" version="9.2p1" extrainfo="protocol 2.0">
<cpe>cpe:/a:openbsd:openssh:9.2p1</cpe></service></port>
<port protocol="tcp" portid="23"><state state="closed"/><service name="telnet"/></port>
<port protocol="udp" portid="53"><state state="open|filtered"/></port>
<port protocol="tcp" portid="80"><state state="open"/></port>
</ports></host>
<host><status state="down"/><address addr="192.0.2.11" addrtype="ipv4"/></host>
<host><status state="up"/><address addr="999.1.1.1" addrtype="ipv4"/></host>
<host><status state="up"/><address addr="2001:db8::1" addrtype="ipv6"/>
<ports><port protocol="tcp" portid="443"><state state="open"/>
<service name="http" tunnel="ssl"/></port></ports></host>
</nmaprun>
"""


@pytest.fixture
def xml_file(tmp_path: Path) -> Path:
    path = tmp_path / "scan.xml"
    path.write_text(XML, encoding="utf-8")
    return path


def by_key(result):
    return {e.key: e for e in result.entities}


def test_only_hosts_that_are_up_become_ips_with_their_valid_hostnames(xml_file):
    found = by_key(parse_nmap(xml_file))
    assert {k for k in found if k.startswith("ip:")} == {"ip:192.0.2.10", "ip:2001:db8::1"}
    assert "domain:www.example.com" in found
    assert not any("no es un host" in k for k in found)
    assert found["domain:www.example.com"].parent == "ip:192.0.2.10"
    assert found["domain:www.example.com"].data["hostname_type"] == "PTR"


def test_only_open_ports_become_services_with_the_internetdb_key(xml_file):
    found = by_key(parse_nmap(xml_file))
    services = {k for k, e in found.items() if e.type is EntityType.SERVICE}
    assert services == {"service:192.0.2.10:22", "service:192.0.2.10:80", "service:2001:db8::1:443"}
    ssh = found["service:192.0.2.10:22"]
    assert ssh.parent == "ip:192.0.2.10"
    assert ssh.data["port"] == 22
    assert ssh.data["transport"] == "tcp"
    assert ssh.data["name"] == "ssh"
    assert ssh.data["product"] == "OpenSSH"
    assert ssh.data["version"] == "9.2p1"
    assert ssh.data["cpe"] == ["cpe:/a:openbsd:openssh:9.2p1"]
    assert found["service:2001:db8::1:443"].data["tunnel"] == "ssl"


def test_every_entity_is_marked_as_imported_and_linked_to_the_target(xml_file):
    result = parse_nmap(xml_file)
    for entity in result.entities:
        assert entity.source == "import_nmap"
        assert [o.module for o in entity.observations] == ["import_nmap"]
    ips = [e for e in result.entities if e.type is EntityType.IP]
    assert all(e.parent == result.target.key for e in ips)


def test_target_is_a_record_with_the_file_hash_and_no_command_line(xml_file):
    result = parse_nmap(xml_file)
    assert result.target.type is EntityType.RECORD
    assert result.target.value == "nmap:scan.xml"
    assert result.target.data["sha256"] == hashlib.sha256(xml_file.read_bytes()).hexdigest()
    assert result.target.data["nmap_version"] == "7.94"
    assert result.target.data["hosts_up"] == 3
    assert "secreto" not in result.model_dump_json()
    assert str(xml_file.parent) not in result.model_dump_json()


def test_discarded_values_are_reported_not_silent(xml_file):
    result = parse_nmap(xml_file)
    assert [(e.kind, e.module) for e in result.events] == [("skipped", "import_nmap")]
    assert "2" in result.events[0].message  # IP 999.1.1.1 y el hostname no válido
    assert result.runs[0].module == "import_nmap"
    assert result.runs[0].status == "ok"
    assert result.runs[0].entities == len(result.entities)
    assert result.status == "complete"


def test_a_file_without_up_hosts_is_empty_not_an_error(tmp_path):
    path = tmp_path / "vacio.xml"
    path.write_text('<nmaprun><host><status state="down"/></host></nmaprun>', encoding="utf-8")
    result = parse_nmap(path)
    assert result.entities == []
    assert result.runs[0].status == "empty"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("<html></html>", "no es un XML de Nmap"),
        ("esto no es xml", "XML no válido"),
        ('<!DOCTYPE x [<!ENTITY a "b">]><nmaprun/>', "DOCTYPE"),
        ('<!doctype nmaprun><nmaprun scanner="nmap"/>', "DOCTYPE"),
    ],
)
def test_invalid_input_is_a_clear_error(tmp_path, content, message):
    path = tmp_path / "malo.xml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(NmapImportError, match=message):
        parse_nmap(path)


def test_missing_and_oversized_files_are_errors(tmp_path, monkeypatch):
    with pytest.raises(NmapImportError, match="no se puede leer"):
        parse_nmap(tmp_path / "no_existe.xml")
    monkeypatch.setattr(nmap_import, "MAX_XML_BYTES", 100)
    big = tmp_path / "grande.xml"
    big.write_bytes(b"<nmaprun>" + b" " * 100 + b"</nmaprun>")
    with pytest.raises(NmapImportError, match="demasiado grande"):
        parse_nmap(big)


# --- CLI -------------------------------------------------------------------------------------


def test_cli_saves_a_scan_that_show_and_history_can_read(xml_file, tmp_path):
    db = tmp_path / "t.db"
    out = runner.invoke(app, ["import", "nmap", str(xml_file), "--db", str(db)])
    assert out.exit_code == 0, out.output
    with Storage(db) as storage:
        loaded = storage.load(1)
    assert loaded is not None
    assert loaded.target.value == "nmap:scan.xml"
    assert len(loaded.entities) == 6
    shown = runner.invoke(app, ["show", "1", "--db", str(db), "--json"])
    assert json.loads(shown.stdout)["target"]["value"] == "nmap:scan.xml"


def test_cli_json_prints_the_scan_result_and_no_save_does_not_write(xml_file, tmp_path):
    db = tmp_path / "t.db"
    out = runner.invoke(
        app, ["import", "nmap", str(xml_file), "--db", str(db), "--json", "--no-save"]
    )
    assert out.exit_code == 0, out.output
    assert json.loads(out.stdout)["target"]["type"] == "record"
    with Storage(db) as storage:
        assert storage.list_scans() == []


def test_cli_reports_a_bad_file_as_a_usage_error(tmp_path):
    bad = tmp_path / "malo.xml"
    bad.write_text("<html/>", encoding="utf-8")
    out = runner.invoke(app, ["import", "nmap", str(bad), "--db", str(tmp_path / "t.db")])
    assert out.exit_code == 2
    assert "no es un XML de Nmap" in out.output
