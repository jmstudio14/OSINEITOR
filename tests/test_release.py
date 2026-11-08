"""F11: paquete, publicación, imagen Docker, sitio de documentación y estabilidad."""

from __future__ import annotations

import importlib.util
import re
import tomllib
from pathlib import Path

import yaml

from osineitor import __all__ as public_names
from osineitor import events, registry

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"


def load_workflow(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- paquete (F11.2) ---------------------------------------------------------------------------


def test_pyproject_is_ready_for_pypi():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    assert project["license"] == "MIT"  # SPDX; la tabla `{file = ...}` está obsoleta
    assert project["license-files"] == ["LICENSE"]
    assert {"Homepage", "Changelog", "Issues"} <= set(project["urls"])
    assert project["classifiers"] and project["keywords"]
    assert int(data["build-system"]["requires"][0].split(">=")[1]) >= 77
    assert "docs" in project["optional-dependencies"]


def test_every_data_file_in_the_package_is_declared():
    """Un fichero de datos sin declarar funciona en el repositorio y falla en el wheel."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = data["tool"]["setuptools"]["package-data"]["osineitor"]
    src = ROOT / "src" / "osineitor"
    declared = {p.relative_to(src) for pattern in patterns for p in src.glob(pattern)}
    shipped = {
        p.relative_to(src)
        for p in src.rglob("*")
        if p.is_file() and p.suffix in {".json", ".yml", ".yaml"} and "__pycache__" not in p.parts
    }
    assert shipped <= declared, sorted(map(str, shipped - declared))


def test_release_workflow_publishes_with_trusted_publishing():
    wf = load_workflow("release.yml")
    assert wf[True]["push"]["tags"] == ["v*"]  # `on:` lo lee YAML como True
    publish = wf["jobs"]["publish"]
    assert publish["needs"] == "build"
    assert publish["permissions"] == {"id-token": "write"}
    assert publish["environment"] == "pypi"
    uses = [s.get("uses", "") for s in publish["steps"]]
    assert any(u.startswith("pypa/gh-action-pypi-publish@") for u in uses)
    step = next(s for s in publish["steps"] if "pypi-publish" in s.get("uses", ""))
    assert step["with"]["attestations"] is True
    assert "password" not in step.get("with", {})  # sin token de PyPI guardado
    assert "id-token" not in str(wf["jobs"]["build"].get("permissions", ""))


def test_release_build_checks_the_tag_matches_the_version():
    steps = load_workflow("release.yml")["jobs"]["build"]["steps"]
    text = "\n".join(str(s.get("run", "")) for s in steps)
    assert "GITHUB_REF_NAME" in text and "pyproject.toml" in text
    for needed in ("pytest", "ruff check", "twine check", "python -m build"):
        assert needed in text


def test_ci_builds_the_package_the_docs_and_the_image():
    jobs = load_workflow("ci.yml")["jobs"]
    assert {"package", "docs", "docker"} <= set(jobs)
    docs = "\n".join(str(s.get("run", "")) for s in jobs["docs"]["steps"])
    assert "mkdocs build --strict" in docs
    docker = "\n".join(str(s.get("run", "")) for s in jobs["docker"]["steps"])
    assert "docker build" in docker and "docker run" in docker


# --- imagen Docker (F11.3) ---------------------------------------------------------------------


def test_dockerfile_is_minimal_and_unprivileged():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert text.count("FROM ") == 2  # construcción aparte: la imagen final no lleva `build`
    final = text.split("FROM ")[2]
    assert "USER osineitor" in final and "useradd" in final
    assert 'ENTRYPOINT ["osineitor"]' in final
    assert "pip install --no-cache-dir /tmp/*.whl" in final
    assert "pip install --no-cache-dir build" not in final
    assert "OSINEITOR_DATA_DIR=/data" in final and "VOLUME /data" in final


def test_dockerignore_keeps_secrets_and_history_out():
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    assert {".git", ".venv", "*.db", "reports"} <= set(ignored)


# --- sitio de documentación (F11.4) ------------------------------------------------------------


def nav_pages() -> list[str]:
    text = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    return re.findall(r":\s+([\w.-]+\.md)\s*$", text, re.M)


def test_every_doc_is_in_the_site_nav_and_every_nav_page_exists():
    pages = set(nav_pages())
    docs = {p.name for p in (ROOT / "docs").glob("*.md")}
    generated = {"referencia-modulos.md"}
    assert docs <= pages, f"docs fuera de la navegación: {sorted(docs - pages)}"
    assert pages - docs <= generated, sorted(pages - docs - generated)


def test_mkdocs_config_excludes_plans_and_uses_the_hook():
    text = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    assert "scripts/mkdocs_hooks.py" in text and "plans/" in text
    assert (ROOT / "scripts" / "mkdocs_hooks.py").exists()


def test_generated_module_reference_lists_every_bundled_module():
    hooks = load_script("mkdocs_hooks")
    page = hooks.modules_reference()
    bundled = [cls for cls in registry.discover() if not registry.is_plugin(cls)]
    assert f"{len(bundled)} módulos" in page
    for cls in bundled:
        assert f"| `{cls.name}` |" in page, cls.name
    assert hooks.PAGE in (ROOT / "mkdocs.yml").read_text(encoding="utf-8")


def test_generated_module_reference_marks_kind_and_key():
    page = load_script("mkdocs_hooks").modules_reference()
    row = next(line for line in page.splitlines() if line.startswith("| `shodan` |"))
    assert "`shodan`" in row.split("|")[-2]  # la columna de API key
    findings = next(line for line in page.splitlines() if line.startswith("| `findings` |"))
    assert "analizador" in findings


# --- compromiso de estabilidad (F11.6) y migración ----------------------------------------------


def test_stability_doc_names_the_public_api():
    doc = (ROOT / "docs" / "ESTABILIDAD.md").read_text(encoding="utf-8")
    for name in public_names:
        assert f"`{name}`" in doc, f"ESTABILIDAD.md no menciona {name}"


def test_stability_doc_lists_every_exit_code():
    doc = (ROOT / "docs" / "ESTABILIDAD.md").read_text(encoding="utf-8")
    codes = {
        value for name, value in vars(events).items() if name.startswith("EXIT_") and value != 0
    }
    listed = {int(n) for n in re.findall(r"`(\d+)`", doc.split("### 2.")[0])}
    assert codes <= listed | {0}, sorted(codes - listed)


def test_stability_doc_states_the_deprecation_policy():
    doc = (ROOT / "docs" / "ESTABILIDAD.md").read_text(encoding="utf-8")
    assert "al menos dos versiones menores" in doc and "siguiente versión mayor" in doc


def test_migration_guide_covers_every_breaking_change_in_the_changelog():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs" / "MIGRACION.md").read_text(encoding="utf-8")
    assert "(antes `0`)" in changelog and "(antes `0`)" in guide
    assert "AS1234" in guide and "--proxy" in guide and "OSINEITOR_CONFIG_DIR" in guide


def test_readme_links_the_new_guides():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for guide in ("TUTORIAL.md", "ESTABILIDAD.md", "MIGRACION.md", "PUBLICACION.md"):
        assert f"docs/{guide}" in text, guide
    assert "docker run" in text
