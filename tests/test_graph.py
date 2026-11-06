"""F7.1: grafo interactivo del informe HTML."""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from osineitor import report
from osineitor.models import Entity, EntityType, Observation, ScanResult
from osineitor.report.graph import MAX_NODES, SCRIPT, graph_data


def scan(count: int) -> ScanResult:
    seed = Entity(type=EntityType.DOMAIN, value="example.com")
    entities = [
        Entity(
            type=EntityType.RECORD,
            value=f"r:{i}",
            parent=seed.key if i % 2 else f"record:r:{i - 1}",
            observations=[Observation(module="dns" if i % 3 else "crtsh", query=seed.key)],
        )
        for i in range(count)
    ]
    return ScanResult(target=seed, depth=2, entities=entities)


def embedded_raw(html: str) -> str:
    match = re.search(r"<script type='application/json' id='graph-data'>(.*?)</script>", html, re.S)
    assert match
    return match.group(1)


def embedded(html: str) -> dict:
    return json.loads(embedded_raw(html))


def test_graph_data_has_the_seed_as_root_and_one_edge_per_known_parent():
    data = graph_data(scan(4))
    assert [n["root"] for n in data["nodes"]] == [True, False, False, False, False]
    assert data["sources"] == ["crtsh", "dns"]
    # Cada arista une dos nodos que existen y ninguna sale de la semilla hacia sí misma.
    assert data["edges"] and all(a != b and max(a, b) < 5 for a, b in data["edges"])


def test_an_unknown_parent_adds_no_edge():
    result = scan(1)
    result.entities[0].parent = "domain:otro.com"
    assert graph_data(result)["edges"] == []


def test_html_report_embeds_the_graph_without_external_resources():
    html = report.render(scan(3), "html")
    assert "id='graph-canvas'" in html and "<h2>Grafo</h2>" in html
    assert embedded(html)["nodes"][0]["value"] == "example.com"
    assert not re.search(r"(src|href)=['\"]https?://", html)


def test_values_cannot_close_the_script_tag():
    result = scan(1)
    result.entities[0] = Entity(
        type=EntityType.RECORD,
        value="x</script><img src=x onerror=alert(1)>",
        parent="domain:example.com",
    )
    html = report.render(result, "html")
    assert html.count("</script>") == 2  # el JSON y el programa; el valor no añade ninguno
    assert any("</script>" in n["value"] for n in embedded(html)["nodes"])


def test_a_comment_opener_cannot_swallow_the_closing_tag():
    result = scan(1)
    result.entities[0] = Entity(
        type=EntityType.RECORD, value="<!--<script>", parent="domain:example.com"
    )
    assert "<!--" not in embedded_raw(report.render(result, "html"))


def test_large_scans_are_capped_and_say_so():
    html = report.render(scan(MAX_NODES + 50), "html")
    assert len(embedded(html)["nodes"]) == MAX_NODES
    assert f"primeras {MAX_NODES}" in html


# DOM mínimo para ejecutar el JS real fuera de un navegador.
HARNESS = r"""
const data = __DATA__;
const drawn = {arcs: 0};
const ctx = new Proxy({}, {
  get: (t, k) => k === 'arc' ? () => drawn.arcs++ : (k in t ? t[k] : () => {}),
  set: (t, k, v) => (t[k] = v, true),
});
const el = () => ({addEventListener() {}, append() {}, style: {}, clientWidth: 800,
  clientHeight: 520, getContext: () => ctx, getBoundingClientRect: () => ({left: 0, top: 0})});
global.document = {
  getElementById: (id) => id === 'graph-data' ? {textContent: JSON.stringify(data)} : el(),
  createElement: el, documentElement: {},
};
global.getComputedStyle = () => ({getPropertyValue: () => '#000'});
global.window = {devicePixelRatio: 1};
global.addEventListener = () => {};
let frames = 0;
global.requestAnimationFrame = (f) => { if (++frames < 5000) setImmediate(f); };
__SCRIPT__
setTimeout(() => {
  console.log(JSON.stringify({frames, arcs: drawn.arcs}));
  process.exit(0);
}, 3000);
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="Node no está instalado")
def test_the_script_settles_500_entities_without_errors(tmp_path):
    """Ejecuta el JS real con 500 entidades y comprueba que el diseño converge y pinta."""
    harness = HARNESS.replace("__DATA__", json.dumps(graph_data(scan(500))))
    script = tmp_path / "harness.js"
    script.write_text(harness.replace("__SCRIPT__", SCRIPT), encoding="utf-8")
    out = subprocess.run(
        ["node", str(script)], capture_output=True, text=True, timeout=60, check=False
    )
    assert out.returncode == 0, out.stderr
    stats = json.loads(out.stdout.strip().splitlines()[-1])
    assert 1 < stats["frames"] < 5000  # converge: deja de pedir fotogramas
    assert stats["arcs"] >= 501  # al menos un dibujo completo (500 entidades + la semilla)
