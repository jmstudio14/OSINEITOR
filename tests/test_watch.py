"""F9.1–F9.3: vigilancia continua, reglas de alerta y notificaciones."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from osineitor import registry, watch
from osineitor.cli import app
from osineitor.errors import ModuleError
from osineitor.models import EntityType
from osineitor.modules.base import Module
from osineitor.storage import Storage

runner = CliRunner()
T0 = datetime(2026, 11, 4, 8, 0, tzinfo=UTC)


class World:
    """Lo que «existe» en Internet en cada ejecución: los módulos falsos lo leen de aquí."""

    subdomains: list[str] = []
    fail = False


def make_module() -> type[Module]:
    class Subs(Module):
        name = "fake_subs"
        description = "subdominios falsos"
        consumes = frozenset({EntityType.DOMAIN})
        produces = frozenset({EntityType.DOMAIN})
        canary = "example.com"

        async def run(self, entity):
            if World.fail:
                raise ModuleError("fuente caída")
            return [
                self.emit(entity, EntityType.DOMAIN, name, subdomain=True)
                for name in World.subdomains
            ]

    return Subs


@pytest.fixture(autouse=True)
def world(monkeypatch):
    World.subdomains, World.fail = ["www.example.com"], False
    subs = make_module()
    monkeypatch.setattr(registry, "discover", lambda: [subs])
    return World


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "watch.yml"
    path.write_text(text, encoding="utf-8")
    return path


BASE = """
targets:
  - target: example.com
    depth: 1
    every: 1d
    notify: [log]
notifiers:
  log: {type: file, path: LOGPATH}
"""


@pytest.fixture
def config(tmp_path):
    log = tmp_path / "alerts.ndjson"
    return watch.load_config(write(tmp_path, BASE.replace("LOGPATH", log.as_posix()))), log


def lines(path: Path) -> list[dict]:
    return (
        [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
        if path.exists()
        else []
    )


async def run(storage, config, when: datetime, **kwargs):
    return await watch.run_watch(config, storage, now=when, **kwargs)


# --- criterio de aceptación de la fase -----------------------------------------------------------


async def test_one_simulated_change_raises_exactly_one_alert_and_it_does_not_repeat(
    tmp_path, config
):
    cfg, log = config
    with Storage(tmp_path / "s.db") as storage:
        [first] = await run(storage, cfg, T0)
        assert first.baseline and first.alerts == [] and first.ran

        World.subdomains = ["www.example.com", "vpn.example.com"]  # el cambio simulado
        [second] = await run(storage, cfg, T0 + timedelta(days=1))
        assert [a.rule for a in second.alerts] == ["new-subdomain"]
        assert second.alerts[0].entity == "domain:vpn.example.com"
        assert [d["ok"] for d in second.deliveries] == [True]
        assert len(lines(log)) == 1

        [third] = await run(storage, cfg, T0 + timedelta(days=2))
        assert third.alerts == [] and len(lines(log)) == 1  # no se repite


async def test_baseline_run_stays_silent_even_with_many_entities(tmp_path, config):
    cfg, log = config
    World.subdomains = [f"s{i}.example.com" for i in range(30)]
    with Storage(tmp_path / "s.db") as storage:
        [report] = await run(storage, cfg, T0)
    assert report.baseline and report.alerts == [] and lines(log) == []


async def test_an_entity_that_disappears_and_returns_alerts_again(tmp_path, config):
    cfg, log = config
    with Storage(tmp_path / "s.db") as storage:
        await run(storage, cfg, T0)
        World.subdomains = ["www.example.com", "dev.example.com"]
        await run(storage, cfg, T0 + timedelta(days=1))
        World.subdomains = ["www.example.com"]
        await run(storage, cfg, T0 + timedelta(days=2))  # desaparece en un scan limpio
        World.subdomains = ["www.example.com", "dev.example.com"]
        await run(storage, cfg, T0 + timedelta(days=3))
    assert [x["entity"] for x in lines(log)] == ["domain:dev.example.com"] * 2


async def test_a_run_with_module_errors_does_not_forget_what_it_failed_to_see(tmp_path, config):
    cfg, log = config
    with Storage(tmp_path / "s.db") as storage:
        World.subdomains = ["www.example.com", "dev.example.com"]
        await run(storage, cfg, T0)
        World.fail = True  # el módulo falla: el scan no ve nada, pero eso no es «desapareció»
        await run(storage, cfg, T0 + timedelta(days=1))
        World.fail = False
        [report] = await run(storage, cfg, T0 + timedelta(days=2))
    assert report.alerts == [] and lines(log) == []


async def test_new_findings_alert_with_their_own_severity(tmp_path, monkeypatch):
    from osineitor.modules.analysis.findings import Findings

    class Dns(Module):
        name = "fake_dns"
        description = "dns falso"
        consumes = frozenset({EntityType.DOMAIN})
        produces = frozenset({EntityType.RECORD})
        canary = "example.com"

        async def run(self, entity):
            if entity.value != "example.com":
                return []
            spf = "v=spf1 +all" if World.subdomains else "v=spf1 -all"
            return [
                self.emit(
                    entity,
                    EntityType.RECORD,
                    "dns:example.com",
                    SPF=spf,
                    DMARC="v=DMARC1; p=reject",
                )
            ]

    monkeypatch.setattr(registry, "discover", lambda: [Dns, Findings])
    log = tmp_path / "a.ndjson"
    cfg = watch.load_config(write(tmp_path, BASE.replace("LOGPATH", log.as_posix())))
    with Storage(tmp_path / "s.db") as storage:
        World.subdomains = []
        await run(storage, cfg, T0)
        World.subdomains = ["x"]  # ahora el SPF es permisivo
        [report] = await run(storage, cfg, T0 + timedelta(days=1))
    assert [(a.rule, a.severity) for a in report.alerts] == [("spf-permissive", "high")]


async def test_targets_not_due_are_skipped_unless_forced(tmp_path, config):
    cfg, _ = config
    with Storage(tmp_path / "s.db") as storage:
        await run(storage, cfg, T0)
        [early] = await run(storage, cfg, T0 + timedelta(hours=3))
        assert not early.due and not early.ran
        [forced] = await run(storage, cfg, T0 + timedelta(hours=3), force=True)
        assert forced.ran
        # Un cron cada hora llega unos minutos antes de las 24 h exactas: cuenta.
        [near] = await run(
            storage, cfg, T0 + timedelta(hours=3) + timedelta(days=1) - timedelta(minutes=5)
        )
        assert near.ran


async def test_an_undeliverable_alert_is_kept_for_the_next_run(tmp_path, monkeypatch):
    cfg = watch.load_config(
        write(
            tmp_path,
            "targets: [{target: example.com, depth: 1, notify: [hook]}]\n"
            "notifiers: {hook: {type: webhook, url: 'https://hooks.example.test/x'}}\n",
        )
    )
    with Storage(tmp_path / "s.db") as storage, respx.mock:
        route = respx.post("https://hooks.example.test/x").mock(return_value=httpx.Response(500))
        await run(storage, cfg, T0)
        World.subdomains = ["www.example.com", "new.example.com"]
        [down] = await run(storage, cfg, T0 + timedelta(days=1))
        assert [d["ok"] for d in down.deliveries] == [False] and "HTTP 500" in down.deliveries[0][
            "error"
        ]
        route.mock(return_value=httpx.Response(200))
        [up] = await run(storage, cfg, T0 + timedelta(days=2))
    assert [a.entity for a in up.alerts] == ["domain:new.example.com"]  # se reintentó y llegó
    assert up.deliveries[0]["ok"] is True


# --- notificadores -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fmt", "key"),
    [("slack", "text"), ("teams", "text"), ("discord", "content"), ("generic", "alerts")],
)
async def test_webhook_formats(tmp_path, fmt, key):
    cfg = watch.load_config(
        write(
            tmp_path,
            f"targets: [{{target: example.com, depth: 1}}]\n"
            f"notifiers: {{hook: {{type: webhook, format: {fmt}, url: 'https://hooks.example.test/x'}}}}\n",
        )
    )
    with Storage(tmp_path / "s.db") as storage, respx.mock:
        route = respx.post("https://hooks.example.test/x").mock(return_value=httpx.Response(204))
        await run(storage, cfg, T0)
        World.subdomains = ["www.example.com", "new.example.com"]
        await run(storage, cfg, T0 + timedelta(days=1))
    body = json.loads(route.calls.last.request.content)
    assert key in body and "new.example.com" in json.dumps(body)


async def test_webhook_url_from_env_and_secret_never_in_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("HOOK_URL", "https://hooks.example.test/SECRETTOKEN")
    cfg = watch.load_config(
        write(
            tmp_path,
            "targets: [{target: example.com, depth: 1}]\n"
            "notifiers: {hook: {type: webhook, url_env: HOOK_URL}}\n",
        )
    )
    with Storage(tmp_path / "s.db") as storage, respx.mock:
        respx.post("https://hooks.example.test/SECRETTOKEN").mock(
            side_effect=httpx.ConnectError("no route to https://hooks.example.test/SECRETTOKEN")
        )
        await run(storage, cfg, T0)
        World.subdomains = ["www.example.com", "new.example.com"]
        [report] = await run(storage, cfg, T0 + timedelta(days=1))
    assert "SECRETTOKEN" not in json.dumps(report.as_dict())


async def test_missing_env_var_is_a_delivery_failure_not_a_crash(tmp_path):
    cfg = watch.load_config(
        write(
            tmp_path,
            "targets: [{target: example.com, depth: 1}]\n"
            "notifiers: {hook: {type: webhook, url_env: NO_SUCH_VARIABLE_X}}\n",
        )
    )
    with Storage(tmp_path / "s.db") as storage:
        await run(storage, cfg, T0)
        World.subdomains = ["www.example.com", "new.example.com"]
        [report] = await run(storage, cfg, T0 + timedelta(days=1))
    assert (
        report.deliveries[0]["ok"] is False
        and "NO_SUCH_VARIABLE_X" in report.deliveries[0]["error"]
    )


async def test_min_severity_filters_what_a_notifier_receives(tmp_path):
    log = tmp_path / "a.ndjson"
    cfg = watch.load_config(
        write(
            tmp_path,
            "targets: [{target: example.com, depth: 1}]\n"
            f"notifiers: {{log: {{type: file, path: '{log.as_posix()}', min_severity: high}}}}\n",
        )
    )
    with Storage(tmp_path / "s.db") as storage:
        await run(storage, cfg, T0)
        World.subdomains = ["www.example.com", "new.example.com"]
        [report] = await run(storage, cfg, T0 + timedelta(days=1))
    assert len(report.alerts) == 1 and lines(log) == []  # new-subdomain es `low`


async def test_email_is_sent_over_smtp(tmp_path, monkeypatch):
    sent: dict = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["host"], sent["port"] = host, port

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self, context=None):
            sent["tls"] = True

        def login(self, user, password):
            sent["login"] = (user, password)

        def send_message(self, msg):
            sent["msg"] = msg

    monkeypatch.setattr("osineitor.notify.smtplib.SMTP", FakeSMTP)
    monkeypatch.setenv("SMTP_PASS", "s3cret")
    cfg = watch.load_config(
        write(
            tmp_path,
            "targets: [{target: example.com, depth: 1}]\n"
            "notifiers:\n  mail: {type: email, host: smtp.example.test, from: a@example.test,\n"
            "    to: b@example.test, username: u, password_env: SMTP_PASS}\n",
        )
    )
    with Storage(tmp_path / "s.db") as storage:
        await run(storage, cfg, T0)
        World.subdomains = ["www.example.com", "new.example.com"]
        [report] = await run(storage, cfg, T0 + timedelta(days=1))
    assert report.deliveries[0]["ok"] is True
    assert sent["port"] == 587 and sent["tls"] and sent["login"] == ("u", "s3cret")
    assert "new.example.com" in sent["msg"].get_content() and sent["msg"]["To"] == "b@example.test"
    assert "s3cret" not in json.dumps(report.as_dict())


# --- fichero de configuración --------------------------------------------------------------------


H = "targets: [{target: example.com}]\n"


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("targets: []", "targets"),
        ("nada: 1", "targets"),
        ("targets: [{target: example.com, every: 1s}]", "every"),
        ("targets: [{target: example.com, every: 1m}]", "5 minutos"),
        ("targets: [{target: example.com, depth: 9}]", "depth"),
        ("targets: [{target: example.com, bogus: 1}]", "desconocidas"),
        ("targets: [{target: example.com, notify: [nope]}]", "desconocido"),
        ("targets: [{target: example.com}, {target: EXAMPLE.com}]", "repetidos"),
        ("targets: [{target: example.com}]\nnotifiers: {a: {type: sms}}", "type"),
        ("targets: [{target: example.com}]\nnotifiers: {a: {type: webhook}}", "url"),
        (
            "targets: [{target: example.com}]\nnotifiers: {a: {type: webhook, url: x, url_env: Y}}",
            "url",
        ),
        (
            H + "notifiers: {a: {type: webhook, url: x, format: irc}}",
            "format",
        ),
        ("targets: [{target: example.com}]\nnotifiers: {a: {type: email, host: h}}", "from"),
        ("targets: [{target: example.com}]\nnotifiers: {a: {type: file}}", "path"),
        (
            H + "notifiers: {a: {type: file, path: p, min_severity: x}}",
            "min_severity",
        ),
        ("targets: [{target: 'no válido!!'}]", "no"),
    ],
)
def test_invalid_config_is_rejected(tmp_path, text, match):
    with pytest.raises(watch.WatchError, match=match):
        watch.load_config(write(tmp_path, text))


def test_unreadable_or_garbled_files_are_watch_errors(tmp_path):
    with pytest.raises(watch.WatchError, match="leer"):
        watch.load_config(tmp_path / "nope.yml")
    with pytest.raises(watch.WatchError, match="YAML"):
        watch.load_config(write(tmp_path, "targets: [unclosed"))


def test_alert_rules_file_is_valid():
    from osineitor.findings import load_rules

    assert {r.id for r in load_rules(watch.ALERT_RULES_FILE)} >= {"new-subdomain", "new-breach"}


# --- CLI -----------------------------------------------------------------------------------------


def test_watch_commands_end_to_end(tmp_path):
    log = tmp_path / "alerts.ndjson"
    path = write(tmp_path, BASE.replace("LOGPATH", log.as_posix()))
    db = str(tmp_path / "s.db")
    base = ["--file", str(path)]

    check = runner.invoke(app, ["watch", "check", *base, "--json"])
    assert json.loads(check.stdout) == {"targets": 1, "notifiers": ["log"]}

    first = runner.invoke(app, ["watch", "run", *base, "--db", db, "--json"])
    assert first.exit_code == 0, first.output
    assert json.loads(first.stdout)["targets"][0]["baseline"] is True

    World.subdomains = ["www.example.com", "vpn.example.com"]
    changed = runner.invoke(app, ["watch", "run", *base, "--db", db, "--force", "--json"])
    assert changed.exit_code == 10, changed.output  # EXIT_ALERTS
    data = json.loads(changed.stdout)
    assert data["alerts"] == 1 and data["exit_code"] == 10

    again = runner.invoke(app, ["watch", "run", *base, "--db", db, "--force"])
    assert again.exit_code == 0 and "0 alerta" in again.output

    listing = runner.invoke(app, ["watch", "list", *base, "--db", db, "--json"])
    [row] = json.loads(listing.stdout)
    assert row["target"] == "example.com" and row["last_status"] == "complete" and not row["due"]


def test_watch_run_reports_a_missing_file_and_unknown_target(tmp_path):
    missing = runner.invoke(app, ["watch", "run", "--file", str(tmp_path / "x.yml")])
    assert missing.exit_code == 2
    path = write(tmp_path, BASE.replace("LOGPATH", (tmp_path / "a").as_posix()))
    unknown = runner.invoke(
        app, ["watch", "run", "--file", str(path), "-t", "otro.org", "--db", str(tmp_path / "s.db")]
    )
    assert unknown.exit_code == 2 and "otro.org" in unknown.output


def test_notification_failure_exit_code(tmp_path):
    blocker = tmp_path / "es_un_fichero"
    blocker.write_text("x", encoding="utf-8")  # su «carpeta» no se puede crear
    path = write(
        tmp_path,
        "targets: [{target: example.com, depth: 1, notify: [hook]}]\n"
        f"notifiers: {{hook: {{type: file, path: '{(blocker / 'a.ndjson').as_posix()}'}}}}\n",
    )
    db = str(tmp_path / "s.db")
    runner.invoke(app, ["watch", "run", "--file", str(path), "--db", db])
    World.subdomains = ["www.example.com", "z.example.com"]
    result = runner.invoke(app, ["watch", "run", "--file", str(path), "--db", db, "--force"])
    assert result.exit_code == 11, result.output  # EXIT_NOTIFY_FAILED


def test_purge_removes_old_scans_only(tmp_path):
    from osineitor.models import Entity, ScanResult

    db = tmp_path / "s.db"
    old = ScanResult(
        target=Entity(type=EntityType.DOMAIN, value="a.com"),
        depth=1,
        started_at=datetime.now(UTC) - timedelta(days=100),
    )
    new = ScanResult(target=Entity(type=EntityType.DOMAIN, value="b.com"), depth=1)
    with Storage(db) as storage:
        old_id, new_id = storage.save(old), storage.save(new)
    dry = runner.invoke(
        app, ["purge", "--older-than", "90d", "--dry-run", "--db", str(db), "--json"]
    )
    assert json.loads(dry.stdout)["deleted"] == 1
    with Storage(db) as storage:
        assert storage.load(old_id) is not None  # dry-run no borra
    done = runner.invoke(app, ["purge", "--older-than", "90d", "--db", str(db), "--json"])
    assert json.loads(done.stdout) == {**json.loads(done.stdout), "deleted": 1, "dry_run": False}
    with Storage(db) as storage:
        assert storage.load(old_id) is None and storage.load(new_id) is not None
    bad = runner.invoke(app, ["purge", "--older-than", "ayer", "--db", str(db)])
    assert bad.exit_code == 2
