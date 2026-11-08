"""Prueba de humo del paquete de Windows: `python smoke.py dist/OSINEITOR`.

Sale con 0 si el paquete funciona y con 1 (motivo en stderr) si no. No usa la red.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLI, GUI = "osineitor.exe", "osineitor-gui.exe"
OFFLINE_SCAN = [
    "scan", "--depth", "1", "--no-save", "--ndjson", "-m", "discord_snowflake",
    "--", "80351110224678912",
]  # fmt: skip


def project_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def count_modules() -> int:
    from osineitor import registry

    return len(registry.discover())


def check_cli(folder: Path, run=subprocess.run, expected_modules: int | None = None) -> list[str]:
    """Comprueba la CLI empaquetada; devuelve los problemas encontrados (vacío = bien)."""
    missing = [f"falta {name} en {folder}" for name in (CLI, GUI) if not (folder / name).exists()]
    if missing:
        return missing
    cli = str(folder / CLI)
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        env = {
            **os.environ,
            "OSINEITOR_CONFIG_DIR": str(Path(tmp, "config")),
            "OSINEITOR_DATA_DIR": str(Path(tmp, "data")),
        }

        def call(*args: str) -> subprocess.CompletedProcess:
            return run([cli, *args], capture_output=True, env=env, timeout=120)

        version = json.loads(call("version", "--json").stdout)["version"]
        if version != project_version():
            problems.append(f"versión {version}, esperada {project_version()}")

        expected = count_modules() if expected_modules is None else expected_modules
        found = len(json.loads(call("modules", "--json").stdout))
        if found != expected:
            problems.append(f"{found} módulos descubiertos, esperados {expected}")

        names = [p["name"] for p in json.loads(call("presets", "--json").stdout)["presets"]]
        if "passive" not in names:
            problems.append(f"falta el preset «passive» (hay: {', '.join(names) or 'ninguno'})")

        scan = call(*OFFLINE_SCAN)
        kinds = [json.loads(line)["type"] for line in scan.stdout.decode().splitlines() if line]
        if "scan.end" not in kinds:
            problems.append(f"el scan sin red no terminó en scan.end (eventos: {kinds})")
    return problems


def check_gui(
    folder: Path, popen=subprocess.Popen, wait: float = 3.0
) -> list[str]:  # fmt: skip
    """La GUI debe seguir viva tras `wait` segundos (sin pantalla: Qt offscreen)."""
    from osineitor_gui.legal import LEGAL_VERSION

    with tempfile.TemporaryDirectory() as tmp:
        # Con el aviso legal ya aceptado: si no, la GUI esperaría el diálogo y no probaría nada.
        Path(tmp, "settings.json").write_text(
            json.dumps({"legal_accepted": LEGAL_VERSION}), encoding="utf-8"
        )
        env = {
            **os.environ,
            "QT_QPA_PLATFORM": "offscreen",
            "OSINEITOR_GUI_CONFIG_DIR": tmp,
            "OSINEITOR_DATA_DIR": tmp,  # el panel lee el historial: nunca el del usuario
        }
        proc = popen([str(folder / GUI)], env=env)
        time.sleep(wait)
        code = proc.poll()
        if code is not None:
            return [f"{GUI} terminó con código {code} antes de {wait:g} s"]
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    return []


def check_assets(folder: Path) -> list[str]:
    """Una fuente o un icono ausentes no impiden arrancar: hay que mirarlo aquí."""
    assets = next(folder.rglob("osineitor_gui/ui/assets"), None)
    if assets is None:
        return ["el paquete no incluye osineitor_gui/ui/assets"]
    expected = {"theme.qss": 1, "fonts/*.ttf": 5, "icons/*.svg": 20, "qss/*.svg": 8}
    return [
        f"faltan assets de la GUI: {pattern}"
        for pattern, count in expected.items()
        if len(list(assets.glob(pattern))) < count
    ]


def main(argv: list[str]) -> int:
    folder = Path(argv[0])
    problems = check_cli(folder)
    if not problems:
        problems = check_assets(folder) or check_gui(folder)
    for problem in problems:
        print(f"FALLO: {problem}", file=sys.stderr)
    if not problems:
        print(f"OK: {folder}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
