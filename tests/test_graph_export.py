"""F8.3: exportación del grafo a GraphML, GEXF y Cypher."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from typer.testing import CliRunner

from osineitor import report
from osineitor.cli import app
from osineitor.models import Entity, EntityType, Observation, ScanResult
from osineitor.storage import Storage

runner = CliRunner()
HOSTILE = "a<b>&\"c'\x01\\d\ne"


def make_result() -> ScanResult:
    seed = Entity(type=EntityType.DOMAIN, value="example.com")
    ip = Entity(
        type=EntityType.IP,
        value="1.1.1.1",
        parent=seed.key,
        observations=[Observation(module="dns", query=seed.key)],
        data={"asn": 13335},
    )
    wallet = Entity(
        type=EntityType.RECORD, value=f"x:{HOSTILE}", parent=ip.key, data={"nota": HOSTILE}
    )
    orphan = Entity(type=EntityType.RECORD, value="huerfano", parent="domain:otro.com")
    return ScanResult(target=seed, depth=2, entities=[ip, wallet, orphan], scan_id=1)


def test_graphml_is_well_formed_and_keeps_nodes_edges_and_hostile_text():
    root = ET.fromstring(report.render(make_result(), "graphml"))
    ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
    nodes = root.findall(".//g:node", ns)
    edges = root.findall(".//g:edge", ns)
    assert len(nodes) == 4
    assert len(edges) == 2  # el hijo de un padre desconocido no genera arista
    assert ("domain:example.com", "ip:1.1.1.1") in {
        (e.get("source"), e.get("target")) for e in edges
    }
    values = [d.text for d in root.iterfind(".//g:data[@key='value']", ns)]
    assert f"x:{HOSTILE}".replace("\x01", "") in values  # texto hostil intacto salvo el control


def test_graphml_edges_never_point_to_a_missing_node():
    root = ET.fromstring(report.render(make_result(), "graphml"))
    ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
    ids = {n.get("id") for n in root.findall(".//g:node", ns)}
    for edge in root.findall(".//g:edge", ns):
        assert edge.get("source") in ids and edge.get("target") in ids


def test_gexf_is_well_formed_with_attributes_and_edges():
    root = ET.fromstring(report.render(make_result(), "gexf"))
    ns = {"g": "http://gexf.net/1.3"}
    assert len(root.findall(".//g:node", ns)) == 4
    assert len(root.findall(".//g:edge", ns)) == 2
    assert [a.get("title") for a in root.findall(".//g:attribute", ns)][:2] == ["type", "value"]


def test_cypher_escapes_strings_and_links_known_parents_only():
    script = report.render(make_result(), "cypher")
    assert "CREATE CONSTRAINT" in script
    assert "MERGE (n:Entity:Domain {key: 'domain:example.com'})" in script
    assert script.count("MERGE (a)-[:DISCOVERED]->(b);") == 2
    # Comilla, barra y salto de línea escapados: una línea por sentencia, sin cadenas rotas.
    assert "\\'" in script and "\\\\" in script and "\\n" in script
    assert "\x01" not in script  # los caracteres de control no pasan al script
    assert all(
        line.startswith(("//", "CREATE", "MERGE", "  SET", "MATCH")) for line in script.splitlines()
    )


def test_export_command_uses_the_graph_extensions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # el informe por defecto va a ./reports
    db = tmp_path / "s.db"
    with Storage(db) as storage:
        scan_id = storage.save(make_result())
    for fmt in ("graphml", "gexf", "cypher"):
        result = runner.invoke(app, ["export", str(scan_id), "-f", fmt, "--db", str(db), "--json"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["path"].endswith(f".{fmt}")
