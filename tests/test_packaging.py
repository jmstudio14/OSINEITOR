"""Paquete de Windows (G8): lo que se puede comprobar sin construirlo ni salir de la CI."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
WINDOWS = ROOT / "packaging" / "windows"
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
VERSION = PYPROJECT["project"]["version"]


def load_script(name: str):
    """Importa `packaging/windows/<name>.py` (no es un paquete)."""
    spec = importlib.util.spec_from_file_location(f"packaging_{name}", WINDOWS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# --- pyproject y .spec ------------------------------------------------------------------------


def test_pyinstaller_is_a_build_extra_not_a_runtime_dependency():
    project = PYPROJECT["project"]
    assert not any("pyinstaller" in dep.lower() for dep in project["dependencies"])
    assert any("pyinstaller" in dep.lower() for dep in project["optional-dependencies"]["build"])
    assert not any("pyinstaller" in dep.lower() for dep in project["optional-dependencies"]["gui"])


SPEC = (WINDOWS / "osineitor.spec").read_text(encoding="utf-8")


def spec_value(name: str) -> str:
    return re.search(rf'^{name} = "([^"]+)"', SPEC, re.M).group(1)


def test_spec_names_the_two_executables_without_colliding():
    cli, gui = spec_value("CLI_NAME"), spec_value("GUI_NAME")
    assert (cli, gui) == ("osineitor", "osineitor-gui")  # `locate_cli` busca «osineitor.exe»
    # NTFS no distingue mayúsculas: dos ejecutables en la misma carpeta no pueden diferir solo así.
    assert cli.lower() != gui.lower()


def test_the_cli_has_a_console_and_the_gui_does_not():
    assert SPEC.count("console=True") == 1 and SPEC.count("console=False") == 1
    assert SPEC.index("console=True") < SPEC.index("console=False")  # CLI primero, luego GUI


def test_both_executables_share_one_folder():
    assert SPEC.count("COLLECT(") == 1
    assert SPEC.count("EXE(") == 2 and SPEC.count("exclude_binaries=True") == 2


def test_modules_are_imported_by_name_so_pyinstaller_needs_them_as_hidden_imports():
    assert "MODULES" in SPEC and "hiddenimports" in SPEC
    assert 'collect_data_files("osineitor")' in SPEC


def test_the_gui_entry_point_is_the_installed_one():
    entry = PYPROJECT["project"]["gui-scripts"]["osineitor-gui"]
    assert entry == "osineitor_gui.app:main"
    launcher = (WINDOWS / "entry_gui.py").read_text(encoding="utf-8")
    assert "from osineitor_gui.app import main" in launcher and "entry_gui.py" in SPEC


# --- instalador de Inno Setup -----------------------------------------------------------------

ISS = (WINDOWS / "osineitor.iss").read_text(encoding="utf-8")


def iss_value(key: str) -> str:
    return re.search(rf"^{key}=(.*)$", ISS, re.M).group(1).strip()


def test_iss_installs_per_user_without_elevation():
    assert iss_value("PrivilegesRequired") == "lowest"
    assert "{autopf}" in iss_value("DefaultDirName") or "{localappdata}" in iss_value(
        "DefaultDirName"
    )
    assert "{pf}" not in iss_value("DefaultDirName")


def test_iss_has_a_fixed_app_id_and_takes_the_version_from_the_build():
    assert re.fullmatch(r"\{\{[0-9A-F-]{36}\}", iss_value("AppId"))
    assert "MyAppVersion" in iss_value("AppVersion")
    assert not re.search(r"^#define MyAppVersion \"\d", ISS, re.M)  # no se fija a mano


def test_iss_is_64_bit_only_and_launches_the_gui():
    assert iss_value("ArchitecturesAllowed") == "x64compatible"
    assert "osineitor-gui.exe" in ISS
    assert "CloseApplications=yes" in ISS


def test_iss_never_deletes_user_data():
    assert "{userappdata}" not in ISS and "{localappdata}\\osineitor" not in ISS
    assert "UninstallDelete" not in ISS


def test_iss_offers_the_cli_on_the_user_path_as_an_optional_task():
    assert re.search(r"^Name: \"addtopath\"", ISS, re.M)
    assert "HKCU" in ISS  # solo el PATH del usuario


# --- sumas SHA-256 ----------------------------------------------------------------------------


def test_checksums_format_and_order(tmp_path):
    checksums = load_script("checksums")
    (tmp_path / "b.zip").write_bytes(b"bbb")
    (tmp_path / "a.exe").write_bytes(b"aaa")
    out = tmp_path / "SHA256SUMS.txt"
    checksums.write_checksums([tmp_path / "b.zip", tmp_path / "a.exe"], out)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines == [
        f"{hashlib.sha256(b'aaa').hexdigest()}  a.exe",
        f"{hashlib.sha256(b'bbb').hexdigest()}  b.zip",
    ]


def test_checksums_file_verifies_like_sha256sum(tmp_path):
    checksums = load_script("checksums")
    data = tmp_path / "paquete.bin"
    data.write_bytes(bytes(range(256)) * 100)
    out = tmp_path / "SHA256SUMS.txt"
    checksums.write_checksums([data], out)
    digest, name = out.read_text(encoding="utf-8").strip().split("  ")
    assert name == "paquete.bin" and digest == hashlib.sha256(data.read_bytes()).hexdigest()


def test_checksums_refuses_a_missing_file(tmp_path):
    checksums = load_script("checksums")
    with pytest.raises(FileNotFoundError):
        checksums.write_checksums([tmp_path / "no-existe"], tmp_path / "SHA256SUMS.txt")


# --- prueba de humo ---------------------------------------------------------------------------


class FakeRun:
    """Sustituye a `subprocess.run`: responde según los argumentos de la CLI."""

    def __init__(self, *, version=VERSION, modules=55, presets=("passive",), end="scan.end"):
        self.version, self.modules, self.presets, self.end = version, modules, presets, end
        self.calls: list[list[str]] = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        args = cmd[1:]
        if args[0] == "version":
            out = json.dumps({"version": self.version})
        elif args[0] == "modules":
            out = json.dumps([{"name": f"m{i}"} for i in range(self.modules)])
        elif args[0] == "presets":
            out = json.dumps({"presets": [{"name": n} for n in self.presets], "errors": []})
        else:  # el scan sin red: NDJSON
            events = [{"type": "scan.start"}, {"type": self.end, "exit_code": 0}]
            out = "\n".join(json.dumps(e) for e in events)
        return subprocess.CompletedProcess(cmd, 0, stdout=out.encode(), stderr=b"")


def make_folder(tmp_path: Path) -> Path:
    for name in ("osineitor.exe", "osineitor-gui.exe"):
        (tmp_path / name).write_bytes(b"MZ")
    return tmp_path


def test_smoke_passes_with_a_correct_package(tmp_path):
    smoke = load_script("smoke")
    assert smoke.check_cli(make_folder(tmp_path), run=FakeRun(), expected_modules=55) == []


def test_smoke_reports_a_missing_executable(tmp_path):
    smoke = load_script("smoke")
    problems = smoke.check_cli(tmp_path, run=FakeRun(), expected_modules=55)
    assert any("osineitor.exe" in p for p in problems)
    assert any("osineitor-gui.exe" in p for p in problems)


def test_smoke_reports_a_wrong_version(tmp_path):
    smoke = load_script("smoke")
    problems = smoke.check_cli(
        make_folder(tmp_path), run=FakeRun(version="0.0.1"), expected_modules=55
    )
    assert len(problems) == 1 and "0.0.1" in problems[0] and VERSION in problems[0]


def test_smoke_reports_missing_modules(tmp_path):
    smoke = load_script("smoke")
    problems = smoke.check_cli(make_folder(tmp_path), run=FakeRun(modules=3), expected_modules=55)
    assert len(problems) == 1 and "3" in problems[0] and "55" in problems[0]


def test_smoke_reports_a_missing_preset(tmp_path):
    smoke = load_script("smoke")
    problems = smoke.check_cli(
        make_folder(tmp_path), run=FakeRun(presets=("quick",)), expected_modules=55
    )
    assert len(problems) == 1 and "passive" in problems[0]


def test_smoke_reports_a_scan_that_did_not_finish(tmp_path):
    smoke = load_script("smoke")
    problems = smoke.check_cli(
        make_folder(tmp_path), run=FakeRun(end="module.end"), expected_modules=55
    )
    assert len(problems) == 1 and "scan.end" in problems[0]


def test_smoke_runs_the_scan_offline_with_isolated_directories(tmp_path):
    smoke = load_script("smoke")
    seen = {}

    def run(cmd, **kwargs):
        seen["env"], seen["cmd"] = kwargs["env"], cmd
        return FakeRun()(cmd, **kwargs)

    smoke.check_cli(make_folder(tmp_path), run=run, expected_modules=55)
    assert seen["env"]["OSINEITOR_CONFIG_DIR"] != seen["env"].get("APPDATA")
    assert seen["env"]["OSINEITOR_DATA_DIR"] and seen["cmd"][-1] == "80351110224678912"


class FakeProcess:
    def __init__(self, alive: bool) -> None:
        self.alive, self.terminated, self.returncode = alive, False, None if alive else 1

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.terminated = True


def test_smoke_gui_alive_after_the_wait_passes_and_is_terminated(tmp_path):
    smoke = load_script("smoke")
    proc = FakeProcess(alive=True)
    captured = {}

    def popen(cmd, **kwargs):
        captured["env"] = kwargs["env"]
        return proc

    assert smoke.check_gui(make_folder(tmp_path), popen=popen, wait=0) == []
    assert proc.terminated
    assert captured["env"]["QT_QPA_PLATFORM"] == "offscreen"


def test_smoke_gui_that_exits_early_is_a_problem(tmp_path):
    smoke = load_script("smoke")
    problems = smoke.check_gui(
        make_folder(tmp_path), popen=lambda cmd, **kw: FakeProcess(alive=False), wait=0
    )
    assert len(problems) == 1 and "1" in problems[0]


def test_smoke_gui_starts_past_the_legal_notice(tmp_path):
    """Sin el aviso ya aceptado, la GUI esperaría un diálogo y la prueba no probaría nada."""
    smoke = load_script("smoke")
    seen = {}

    def popen(cmd, **kwargs):
        config = Path(kwargs["env"]["OSINEITOR_GUI_CONFIG_DIR"]) / "settings.json"
        seen["settings"] = json.loads(config.read_text(encoding="utf-8"))
        return FakeProcess(alive=True)

    smoke.check_gui(make_folder(tmp_path), popen=popen, wait=0)
    from osineitor_gui.legal import LEGAL_VERSION

    assert seen["settings"]["legal_accepted"] >= LEGAL_VERSION


def test_smoke_main_returns_1_and_names_the_problem(tmp_path, capsys):
    smoke = load_script("smoke")
    assert smoke.main([str(tmp_path)]) == 1
    assert "osineitor.exe" in capsys.readouterr().err


# --- flujo de lanzamiento ---------------------------------------------------------------------

RELEASE = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")


def job_block(name: str) -> str:
    match = re.search(rf"^  {name}:\n(.*?)(?=^  \S|\Z)", RELEASE, re.M | re.S)
    assert match, f"no existe el job {name}"
    return match.group(1)


def test_release_has_a_windows_job_after_the_checks():
    block = job_block("windows")
    assert "runs-on: windows-latest" in block and "needs: build" in block
    assert "contents: write" in block
    for step in ("build.ps1", "smoke.py", "checksums.py", "ISCC"):
        assert step in block


def test_pypi_does_not_depend_on_the_windows_job_and_has_no_write_permission():
    publish = job_block("publish")
    assert "windows" not in publish and "contents: write" not in publish


def test_the_windows_job_uses_no_signing_secrets():
    block = job_block("windows")
    assert "secrets." not in block.replace("secrets.GITHUB_TOKEN", "")


def test_windows_job_can_run_without_publishing():
    assert "workflow_dispatch" in RELEASE
    assert "github.ref_type == 'tag'" in job_block("windows") or "startsWith" in job_block(
        "windows"
    )
