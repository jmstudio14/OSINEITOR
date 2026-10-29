"""Reglas de arquitectura de la capa de la GUI, comprobadas sobre el código fuente."""

from __future__ import annotations

import ast
from pathlib import Path

GUI = Path(__file__).parent.parent.parent / "src" / "osineitor_gui"
# Lo único que la GUI puede tomar del motor.
ALLOWED_ENGINE_IMPORTS = {("osineitor.models", "detect_type"), ("osineitor", "__version__")}
QT_PACKAGES = ("PySide6", "PyQt5", "PyQt6", "shiboken6")


def imports(path: Path) -> list[tuple[str, str | None]]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found += [(alias.name, None) for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found += [(node.module, alias.name) for alias in node.names]
    return found


def python_files() -> list[Path]:
    return sorted(GUI.rglob("*.py"))


def test_there_are_files_to_check():
    assert len(python_files()) >= 8


def test_gui_only_imports_the_allowed_parts_of_the_engine():
    for path in python_files():
        for module, name in imports(path):
            if module == "osineitor" or module.startswith("osineitor."):
                assert (module, name) in ALLOWED_ENGINE_IMPORTS, (
                    f"{path.name} importa {module}.{name}: la GUI solo habla con la CLI"
                )


def test_qt_is_confined_to_the_ui_layer():
    """La capa no visual se prueba sin Qt; Qt solo puede aparecer en `ui/` y en `app.py`."""
    for path in python_files():
        relative = path.relative_to(GUI).as_posix()
        if relative.startswith("ui/") or relative == "app.py":
            continue
        for module, _ in imports(path):
            assert not module.startswith(QT_PACKAGES), f"{relative} importa Qt ({module})"


def test_the_checker_itself_catches_a_violation(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("from osineitor.engine import Engine\nimport PySide6.QtCore\n", encoding="utf-8")
    found = imports(bad)
    assert ("osineitor.engine", "Engine") in found and ("PySide6.QtCore", None) in found
    assert ("osineitor.engine", "Engine") not in ALLOWED_ENGINE_IMPORTS
