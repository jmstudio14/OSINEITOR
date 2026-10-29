"""La documentación no se pudre: enlaces que resuelven y órdenes de los ejemplos que existen."""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

import pytest
import typer

from osineitor.cli import app

ROOT = Path(__file__).parent.parent
DOCS = sorted([*ROOT.glob("*.md"), *(ROOT / "docs").glob("*.md")])
# Documentos cuyos ejemplos de órdenes deben ser ejecutables tal cual.
COMMAND_DOCS = [ROOT / "README.md", ROOT / "docs" / "USO.md"]

LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")
FENCE_RE = re.compile(r"^```(\w*)\n(.*?)^```", re.M | re.S)


def slug(heading: str) -> str:
    """Ancla que genera GitHub para un título."""
    text = re.sub(r"[`*_]", "", heading.strip().lower())
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(path: Path) -> set[str]:
    text = FENCE_RE.sub("", path.read_text(encoding="utf-8"))
    return {slug(m.group(1)) for m in re.finditer(r"^#{1,6}\s+(.+)$", text, re.M)}


def links(path: Path) -> list[str]:
    text = FENCE_RE.sub("", path.read_text(encoding="utf-8"))
    return LINK_RE.findall(text)


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_relative_links_and_anchors_resolve(doc):
    broken = []
    for target in links(doc):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        path_part, _, anchor = target.partition("#")
        dest = (doc.parent / path_part).resolve() if path_part else doc
        if not dest.exists():
            broken.append(f"{target}: no existe {dest.relative_to(ROOT)}")
        elif anchor and dest.suffix == ".md" and anchor not in anchors(dest):
            broken.append(f"{target}: no hay un título con esa ancla en {dest.name}")
    assert not broken, f"{doc.name}: " + "; ".join(broken)


def test_slug_matches_github_for_titles_with_symbols():
    assert slug("Hito G · Aplicación de escritorio para Windows") == (
        "hito-g--aplicación-de-escritorio-para-windows"
    )
    assert slug("Ejemplo de módulo") == "ejemplo-de-módulo"
    assert slug("`doctor` y más") == "doctor-y-más"


# --- órdenes de los ejemplos -------------------------------------------------------------------


def command_lines(path: Path) -> list[str]:
    lines = []
    for lang, body in FENCE_RE.findall(path.read_text(encoding="utf-8")):
        if lang in ("python", "json", "text"):
            continue
        for raw in body.splitlines():
            line = raw.strip()
            if line.startswith("osineitor "):
                lines.append(re.split(r"\s+#\s", line)[0])
    return lines


def option_names(cmd: Any) -> set[str]:
    names = {"--help"}
    for param in cmd.params:
        names.update(param.opts)
        names.update(param.secondary_opts)
    return names


def check(line: str) -> str | None:
    """Motivo por el que la orden no existe, o `None` si es válida."""
    root = typer.main.get_command(app)
    tokens = shlex.split(line)[1:]
    cmd: Any = root
    chain = [root]
    for token in tokens:
        if token.startswith("-"):
            continue
        # Typer trae su propio click: se distingue un grupo por tener subcomandos.
        subcommands = getattr(cmd, "commands", None)
        if subcommands is None:
            continue  # argumento posicional
        if token not in subcommands:
            return f"orden desconocida {token!r}"
        cmd = subcommands[token]
        chain.append(cmd)
    if getattr(cmd, "commands", None) is not None and cmd is not root:
        return "falta la subórden"
    known = set().union(*(option_names(c) for c in chain))
    for token in tokens:
        if token.startswith("-") and token != "--" and token.split("=")[0] not in known:
            return f"opción desconocida {token!r}"
    return None


@pytest.mark.parametrize("doc", COMMAND_DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_documented_commands_exist(doc):
    lines = command_lines(doc)
    assert lines, f"{doc.name} no tiene ejemplos de órdenes"
    problems = [f"{line!r}: {why}" for line in lines if (why := check(line))]
    assert not problems, "; ".join(problems)


def test_the_command_checker_rejects_nonexistent_things():
    assert check("osineitor scan example.com --depth 2") is None
    assert check("osineitor --no-color scan example.com") is None
    assert check("osineitor cache clear") is None
    assert check("osineitor config set shodan --stdin") is None
    assert check("osineitor escanear example.com") is not None
    assert check("osineitor scan example.com --profundidad 2") is not None
    assert check("osineitor cache vaciar") is not None
    assert check("osineitor cache") is not None  # grupo sin subórden


def test_numbers_quoted_in_the_readme_are_true():
    import json
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, "-m", "osineitor", "modules", "--json"], capture_output=True, check=True
    ).stdout
    modules = json.loads(out)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"{len(modules)} módulos" in readme
    table_modules = set(re.findall(r"^\| \w+ \| `(\w+)` \|", readme, re.M))
    assert table_modules == {m["name"] for m in modules}  # la tabla lista exactamente los reales
