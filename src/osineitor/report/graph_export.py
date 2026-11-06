"""Exportación del grafo de entidades a GraphML, GEXF (Gephi) y un script Cypher (Neo4j).

Nodos = la semilla y las entidades; aristas = pivoteo padre → hija (`Entity.parent`).
"""

from __future__ import annotations

import json
import re
from xml.sax.saxutils import escape, quoteattr

from osineitor.models import Entity, ScanResult

# Control salvo \n y \r (que el script Cypher escapa): ni Neo4j ni una terminal los quieren.
_CONTROL = re.compile("[\x00-\x09\x0b\x0c\x0e-\x1f\x7f]")
# XML 1.0 no admite la mayoría de caracteres de control, y los valores vienen de terceros.
_XML_ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def _nodes_and_edges(result: ScanResult) -> tuple[list[Entity], list[tuple[str, str]]]:
    nodes = [result.target, *result.entities]
    keys = {e.key for e in nodes}
    edges = sorted(
        {(e.parent, e.key) for e in result.entities if e.parent in keys and e.parent != e.key}
    )
    return nodes, edges  # type: ignore[return-value]


def _text(value: object) -> str:
    return escape(_XML_ILLEGAL.sub("", str(value)))


def _attr(value: object) -> str:
    return quoteattr(_XML_ILLEGAL.sub("", str(value)))


def _fields(entity: Entity) -> dict[str, str]:
    return {
        "type": entity.type.value,
        "value": entity.value,
        "sources": ";".join(entity.sources),
        "confidence": entity.confidence or "",
        "data": json.dumps(entity.data, ensure_ascii=False, default=str) if entity.data else "",
    }


def to_graphml(result: ScanResult) -> str:
    nodes, edges = _nodes_and_edges(result)
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
    ]
    out += [
        f'  <key id="{k}" for="node" attr.name="{k}" attr.type="string"/>'
        for k in _fields(nodes[0])
    ]
    out.append('  <graph id="osineitor" edgedefault="directed">')
    for entity in nodes:
        out.append(f"    <node id={_attr(entity.key)}>")
        out += [f'      <data key="{k}">{_text(v)}</data>' for k, v in _fields(entity).items()]
        out.append("    </node>")
    out += [
        f'    <edge id="e{i}" source={_attr(a)} target={_attr(b)}/>'
        for i, (a, b) in enumerate(edges)
    ]
    out += ["  </graph>", "</graphml>"]
    return "\n".join(out) + "\n"


def to_gexf(result: ScanResult) -> str:
    nodes, edges = _nodes_and_edges(result)
    names = list(_fields(nodes[0]))
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gexf xmlns="http://gexf.net/1.3" version="1.3">',
        '  <graph defaultedgetype="directed">',
        '    <attributes class="node">',
    ]
    out += [f'      <attribute id="{i}" title="{n}" type="string"/>' for i, n in enumerate(names)]
    out += ["    </attributes>", "    <nodes>"]
    for entity in nodes:
        out.append(f"      <node id={_attr(entity.key)} label={_attr(entity.value)}>")
        out.append("        <attvalues>")
        out += [
            f'          <attvalue for="{i}" value={_attr(v)}/>'
            for i, v in enumerate(_fields(entity).values())
        ]
        out += ["        </attvalues>", "      </node>"]
    out += ["    </nodes>", "    <edges>"]
    out += [
        f'      <edge id="{i}" source={_attr(a)} target={_attr(b)}/>'
        for i, (a, b) in enumerate(edges)
    ]
    out += ["    </edges>", "  </graph>", "</gexf>"]
    return "\n".join(out) + "\n"


def _cypher_string(value: object) -> str:
    text = _CONTROL.sub("", str(value)).replace("\\", "\\\\").replace("'", "\\'")
    return "'" + text.replace("\n", "\\n").replace("\r", "\\r") + "'"


def _label(entity: Entity) -> str:
    """Etiqueta de Neo4j: el tipo en CamelCase (`crypto_address` → `CryptoAddress`)."""
    return "".join(part.title() for part in entity.type.value.split("_"))


def to_cypher(result: ScanResult) -> str:
    """Script para `cypher-shell`: crea (o reutiliza) los nodos por su clave y enlaza los padres."""
    nodes, edges = _nodes_and_edges(result)
    out = [
        "// OSINEITOR: grafo de entidades. Ejecutar con cypher-shell o el navegador de Neo4j.",
        "CREATE CONSTRAINT osineitor_key IF NOT EXISTS FOR (n:Entity) REQUIRE n.key IS UNIQUE;",
    ]
    for entity in nodes:
        props = {"key": entity.key, **_fields(entity)}
        body = ", ".join(f"{k}: {_cypher_string(v)}" for k, v in props.items() if v != "")
        out.append(f"MERGE (n:Entity:{_label(entity)} {{key: {_cypher_string(entity.key)}}})")
        out.append(f"  SET n += {{{body}}};")
    out += [
        f"MATCH (a:Entity {{key: {_cypher_string(a)}}}), (b:Entity {{key: {_cypher_string(b)}}}) "
        "MERGE (a)-[:DISCOVERED]->(b);"
        for a, b in edges
    ]
    return "\n".join(out) + "\n"
