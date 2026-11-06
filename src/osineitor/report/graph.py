"""Grafo interactivo del informe HTML: nodos = entidades, aristas = pivoteo padre → hija.

Todo va en línea (datos JSON + JS sin librerías): el informe sigue siendo un solo fichero y no
carga nada de Internet. El diseño es el de fuerzas clásico (repulsión entre nodos, muelle en
cada arista, gravedad al centro) sobre un `<canvas>`; con ~500 entidades se asienta en un par
de segundos.
"""

from __future__ import annotations

import json
from html import escape

from osineitor.models import ScanResult

MAX_NODES = 1500

SCRIPT = r"""
(() => {
  const data = JSON.parse(document.getElementById('graph-data').textContent);
  const canvas = document.getElementById('graph-canvas'), ctx = canvas.getContext('2d');
  const tip = document.getElementById('graph-tip');
  const css = getComputedStyle(document.documentElement);
  const color = (v) => css.getPropertyValue(v).trim();
  const dpr = window.devicePixelRatio || 1;
  const types = [...new Set(data.nodes.map(n => n.type))];
  const hue = (t) => 360 * (types.indexOf(t) / types.length);
  const nodes = data.nodes.map((n, i) => ({...n, x: Math.cos(i) * 40 * Math.sqrt(i + 1),
    y: Math.sin(i) * 40 * Math.sqrt(i + 1), vx: 0, vy: 0, on: true}));
  const edges = data.edges;
  const off = {type: new Set(), source: new Set()};
  const view = {x: 0, y: 0, k: 1};
  let alpha = 1, running = false;

  function visible(n) {
    return !off.type.has(n.type) && (!n.sources.length || n.sources.some(s => !off.source.has(s)));
  }
  function filters() {
    for (const [kind, list] of [['type', types], ['source', data.sources]]) {
      const box = document.getElementById('graph-' + kind);
      for (const name of list) {
        const label = document.createElement('label'), input = document.createElement('input');
        input.type = 'checkbox'; input.checked = true;
        input.addEventListener('change', () => {
          if (input.checked) off[kind].delete(name); else off[kind].add(name);
          nodes.forEach(n => { n.on = visible(n); }); reheat();
        });
        label.append(input, ' ' + name); box.append(label);
      }
    }
  }
  function tick() {
    const live = nodes.filter(n => n.on);
    for (let a = 0; a < live.length; a++) {
      const p = live[a];
      for (let b = a + 1; b < live.length; b++) {
        const q = live[b];
        const dx = p.x - q.x, dy = p.y - q.y, d2 = dx * dx + dy * dy || 0.01;
        if (d2 > 90000) continue;
        const f = 900 * alpha / d2;
        p.vx += dx * f; p.vy += dy * f; q.vx -= dx * f; q.vy -= dy * f;
      }
      p.vx -= p.x * 0.01 * alpha; p.vy -= p.y * 0.01 * alpha;
    }
    for (const [s, t] of edges) {
      const p = nodes[s], q = nodes[t];
      if (!p.on || !q.on) continue;
      const dx = q.x - p.x, dy = q.y - p.y, d = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const f = (d - 60) * 0.05 * alpha / d;
      p.vx += dx * f; p.vy += dy * f; q.vx -= dx * f; q.vy -= dy * f;
    }
    for (const n of live) { n.vx *= 0.6; n.vy *= 0.6; n.x += n.vx; n.y += n.vy; }
    alpha *= 0.985;
  }
  function draw() {
    const w = canvas.width, h = canvas.height;
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, w, h);
    ctx.setTransform(view.k * dpr, 0, 0, view.k * dpr, w / 2 + view.x, h / 2 + view.y);
    ctx.strokeStyle = color('--line'); ctx.lineWidth = 1 / view.k; ctx.beginPath();
    for (const [s, t] of edges) {
      const p = nodes[s], q = nodes[t];
      if (p.on && q.on) { ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); }
    }
    ctx.stroke();
    for (const n of nodes) {
      if (!n.on) continue;
      ctx.beginPath(); ctx.arc(n.x, n.y, n.root ? 8 : 4, 0, 6.2832);
      ctx.fillStyle = n.root ? color('--acc') : 'hsl(' + hue(n.type) + ' 65% 55%)'; ctx.fill();
    }
  }
  function loop() {
    for (let i = 0; i < 3 && alpha > 0.01; i++) tick();
    draw();
    if (alpha > 0.01) requestAnimationFrame(loop); else running = false;
  }
  function reheat() { alpha = 1; if (!running) { running = true; requestAnimationFrame(loop); } }
  function resize() {
    canvas.width = canvas.clientWidth * dpr; canvas.height = canvas.clientHeight * dpr; draw();
  }
  function at(ev) {
    const r = canvas.getBoundingClientRect();
    const x = ((ev.clientX - r.left) * dpr - canvas.width / 2 - view.x) / (view.k * dpr);
    const y = ((ev.clientY - r.top) * dpr - canvas.height / 2 - view.y) / (view.k * dpr);
    const reach = (8 / view.k) ** 2;
    return nodes.find(n => n.on && (n.x - x) ** 2 + (n.y - y) ** 2 < reach);
  }
  let drag = null;
  canvas.addEventListener('pointerdown', e => { drag = {x: e.clientX, y: e.clientY}; });
  addEventListener('pointerup', () => { drag = null; });
  canvas.addEventListener('pointermove', e => {
    if (drag) {
      view.x += (e.clientX - drag.x) * dpr; view.y += (e.clientY - drag.y) * dpr;
      drag = {x: e.clientX, y: e.clientY}; draw(); return;
    }
    const n = at(e);
    tip.hidden = !n;
    if (n) {
      const src = n.sources.length ? ' (' + n.sources.join(', ') + ')' : '';
      tip.textContent = n.type + ': ' + n.value + src;
      tip.style.left = e.offsetX + 12 + 'px'; tip.style.top = e.offsetY + 12 + 'px';
    }
  });
  canvas.addEventListener('wheel', e => {
    e.preventDefault(); view.k *= e.deltaY < 0 ? 1.15 : 1 / 1.15; draw();
  }, {passive: false});
  addEventListener('resize', resize);
  filters(); resize(); reheat();
})();
"""

CSS = """
#graph { position:relative; }
#graph-canvas { width:100%; height:520px; border:1px solid var(--line); touch-action:none;
  cursor:grab; } #graph-tip { position:absolute; background:var(--head);
  border:1px solid var(--line); padding:2px 6px; pointer-events:none; max-width:420px;
  overflow-wrap:anywhere; } .graph-filters { display:flex; flex-wrap:wrap; gap:4px 14px;
  margin:6px 0; } .graph-filters label { white-space:nowrap; }
"""


def graph_data(result: ScanResult) -> dict[str, object]:
    """Nodos (la semilla y las entidades) y aristas como pares de índices, sin repetir."""
    entities = [result.target, *result.entities][:MAX_NODES]
    index = {e.key: i for i, e in enumerate(entities)}
    edges = sorted(
        {(index[e.parent], i) for i, e in enumerate(entities) if e.parent in index and i != 0}
        - {(i, i) for i in range(len(entities))}
    )
    return {
        "nodes": [
            {"type": e.type.value, "value": e.value[:200], "sources": e.sources, "root": i == 0}
            for i, e in enumerate(entities)
        ],
        "edges": [list(edge) for edge in edges],
        "sources": sorted({s for e in entities for s in e.sources}),
    }


def render_graph(result: ScanResult) -> str:
    """Sección HTML con el grafo; las tablas de debajo siguen siendo la versión accesible."""
    data = graph_data(result)
    # Los datos son de terceros: un `<` sin escapar (`</script>`, `<!--`) rompería el <script>.
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    total = len(result.entities) + 1
    note = (
        f"<p class='muted'>Se dibujan las primeras {MAX_NODES} de {total} entidades.</p>"
        if total > MAX_NODES
        else ""
    )
    label = escape("Grafo de entidades; la misma información está en las tablas")
    return (
        f"<h2>Grafo</h2>{note}"
        "<p class='muted'>Cada nodo es una entidad y cada línea, el pivoteo que la descubrió. "
        "Arrastra para mover, rueda para ampliar; marca o desmarca tipos y fuentes.</p>"
        "<div id='graph'><div class='graph-filters' id='graph-type'></div>"
        "<div class='graph-filters' id='graph-source'></div>"
        f"<canvas id='graph-canvas' role='img' aria-label='{label}'></canvas>"
        "<div id='graph-tip' hidden></div></div>"
        f"<script type='application/json' id='graph-data'>{payload}</script>"
        f"<script>{SCRIPT}</script>"
    )
