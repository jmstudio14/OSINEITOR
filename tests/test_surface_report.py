"""F7.12 y F7.7: informes de superficie de ataque y ejecutivo."""

from __future__ import annotations

from typer.testing import CliRunner

from osineitor import report
from osineitor.cli import app
from osineitor.models import Entity, EntityType, ModuleRun, ScanResult
from osineitor.storage import Storage

runner = CliRunner()
SEED = Entity(type=EntityType.DOMAIN, value="example.com")


def ent(kind, value, parent=None, confidence="alto", **data) -> Entity:
    return Entity(type=kind, value=value, parent=parent, confidence=confidence, data=data)


def finding(rule, severity, affected, title="t", recommendation="") -> Entity:
    return Entity(
        type=EntityType.FINDING,
        value=f"{rule}: {affected.value}",
        parent=affected.key,
        data={
            "rule": rule,
            "title": title,
            "severity": severity,
            "affected": [affected.key],
            "recommendation": recommendation,
        },
    )


def populated() -> ScanResult:
    ip = ent(EntityType.IP, "203.0.113.7", SEED.key)
    service = ent(EntityType.SERVICE, "203.0.113.7:3389", ip.key, port=3389, product="RDP")
    sub = ent(EntityType.DOMAIN, "dev.example.com", SEED.key, subdomain=True)
    tech = ent(EntityType.TECHNOLOGY, "nginx", sub.key, version="1.18", category="Servidor web")
    cert = ent(EntityType.CERTIFICATE, "ab" * 32, sub.key, issuer="R3", not_after="2027-01-01")
    return ScanResult(
        target=SEED,
        depth=2,
        purpose="auditoría propia",
        entities=[
            ip,
            service,
            sub,
            tech,
            cert,
            finding("rdp", "high", service, "RDP expuesto", "Cerrad el puerto 3389."),
            finding("old", "low", tech, "nginx antiguo"),
        ],
        runs=[
            ModuleRun(module="dns", status="ok"),
            ModuleRun(module="shodan", status="error", message="boom"),
        ],
    )


def test_formats_are_registered_as_markdown():
    assert report.FORMATS["attack-surface"][0] == "attack-surface.md"
    assert report.FORMATS["executive"][0] == "executive.md"


def test_attack_surface_has_inventory_and_prioritised_findings():
    text = report.render(populated(), "attack-surface")
    for section in (
        "# Superficie de ataque",
        "## Resumen",
        "## Hallazgos priorizados",
        "## Dominios y subdominios",
        "## Direcciones IP y servicios",
        "## Tecnologías",
        "## Certificados",
        "## Límites de este inventario",
    ):
        assert section in text
    assert "dev.example.com" in text and "203.0.113.7" in text and "3389 (RDP)" in text
    assert text.index("RDP expuesto") < text.index("nginx antiguo")  # la severidad manda
    assert "Propósito: auditoría propia" in text
    assert "`shodan`" in text  # fuente con error en los límites


def test_executive_report_summarises_and_lists_limits_and_annexes():
    text = report.render(populated(), "executive")
    for section in (
        "# Informe ejecutivo",
        "## Resumen",
        "## Hallazgos clave",
        "## Activos con más riesgo",
        "## Nivel de confianza",
        "## Límites del análisis",
        "## Anexo A · Fuentes consultadas",
        "## Anexo B · Evidencias",
    ):
        assert section in text
    assert "1 de severidad alta o crítica" in text
    assert "RDP expuesto" in text and "Cerrad el puerto 3389." in text
    key = text.split("## Hallazgos clave")[1].split("## Activos")[0]
    assert "nginx antiguo" not in key  # los `low` no son hallazgos clave
    assert "heurística" in text
    assert "no guardó evidencias" in text


def test_hostile_values_cannot_break_the_tables():
    sub = ent(EntityType.TECHNOLOGY, "a|b\nc", SEED.key)
    result = ScanResult(
        target=SEED,
        depth=1,
        entities=[sub, finding("x", "high", sub, "malo | feo\ny", "r|s")],
    )
    for fmt in ("attack-surface", "executive"):
        text = report.render(result, fmt)
        assert "malo \\| feo y" in text and "r\\|s" in text
        assert "a\\|b c" in text and "\nc " not in text and "\ny |" not in text


def test_empty_scan_still_renders_every_section():
    result = ScanResult(target=SEED, depth=1)
    surface = report.render(result, "attack-surface")
    executive = report.render(result, "executive")
    assert "_Sin datos._" in surface and "_Sin datos._" in executive
    assert "0 hallazgo(s)." in executive
    assert "Todas las fuentes consultadas respondieron." in executive


def test_truncated_scan_is_called_out():
    result = ScanResult(target=SEED, depth=1, truncated=True)
    assert "truncated" in report.render(result, "executive")


def test_cli_export_writes_the_new_formats(tmp_path):
    db = tmp_path / "s.db"
    with Storage(db) as store:
        store.save(populated())
    for fmt in ("attack-surface", "executive"):
        out = tmp_path / f"{fmt}.md"
        res = runner.invoke(
            app, ["export", "1", "--db", str(db), "--format", fmt, "--output", str(out)]
        )
        assert res.exit_code == 0, res.stdout
        assert out.read_text(encoding="utf-8").startswith("# ")
