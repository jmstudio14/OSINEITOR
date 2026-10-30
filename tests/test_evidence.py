"""`--evidence`: huella de la respuesta original de cada fuente y `osineitor verify`."""

from __future__ import annotations

import hashlib
import json
import sqlite3

import httpx
import pytest
import respx
from typer.testing import CliRunner

from osineitor import evidence
from osineitor.cli import app
from osineitor.engine import Engine
from osineitor.http import RunStats, current_stats
from osineitor.models import Entity, EntityType, ScanResult, digest
from osineitor.modules.base import Module
from osineitor.modules.domain.dns import Dns
from tests.conftest import FakeResolver
from tests.test_cli import use_modules

runner = CliRunner()
SEED = Entity(type=EntityType.DOMAIN, value="example.com")
URL = "https://api.example.test/data"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetcher(url: str = URL, **params) -> type[Module]:
    """Módulo que consulta `url` por HTTP y emite una IP."""

    async def run(self, entity):
        await self.ctx.http.get(url, **params)
        return [self.emit(entity, EntityType.IP, "1.2.3.4")]

    return type(
        "Fetcher",
        (Module,),
        {
            "name": "fetcher",
            "description": "test",
            "consumes": frozenset({EntityType.DOMAIN}),
            "run": run,
        },
    )


# --- huella y URL ---------------------------------------------------------------------------------


def test_capture_hashes_the_body_and_flags_a_truncated_one(monkeypatch):
    item = evidence.capture("http", URL, b"hola", method="GET", status=200)
    assert (item.sha256, item.size, item.truncated) == (sha(b"hola"), 4, False)
    monkeypatch.setattr(evidence, "MAX_BODY", 3)
    cut = evidence.capture("http", URL, b"hola", method="GET", status=200)
    assert (cut.body, cut.size, cut.truncated) == (b"hol", 4, True)
    assert cut.sha256 == sha(b"hol")  # la huella es la del trozo guardado


def test_sanitize_url_hides_keys_and_credentials_but_keeps_the_rest_of_the_query():
    url = "https://user:pw@api.example.test/v1/x?q=%25.example.com&api_key=SECRETO&Token=otro#frag"
    clean = evidence.sanitize_url(url, ["SECRETO"])
    assert clean == "https://api.example.test/v1/x?q=%25.example.com&api_key=***&Token=***"
    assert "SECRETO" not in evidence.sanitize_url("https://h.test/a/SECRETO/b", ["SECRETO"])


# --- captura HTTP ---------------------------------------------------------------------------------


@respx.mock
async def test_http_records_the_response_only_when_the_scan_asks_for_it(ctx):
    respx.get(URL).mock(return_value=httpx.Response(200, content=b'{"a": 1}'))
    current_stats.set(RunStats())  # sin lista: no se guarda nada
    await ctx.http.get(URL)
    stats = RunStats(evidence=[])
    current_stats.set(stats)
    await ctx.http.get(URL)
    (item,) = stats.evidence
    assert (item.kind, item.method, item.status, item.url) == ("http", "GET", 200, URL)
    assert item.sha256 == sha(b'{"a": 1}') and item.body == b'{"a": 1}'


@respx.mock
async def test_a_retried_request_leaves_one_evidence_and_a_redirect_one_per_hop(ctx):
    respx.get(URL).mock(side_effect=[httpx.Response(503), httpx.Response(200, content=b"ok")])
    stats = RunStats(evidence=[])
    current_stats.set(stats)
    await ctx.http.get(URL)
    assert [e.status for e in stats.evidence] == [200]

    respx.get("https://a.example.test/").mock(
        return_value=httpx.Response(302, headers={"location": "https://b.example.test/x"})
    )
    respx.get("https://b.example.test/x").mock(return_value=httpx.Response(200, content=b"fin"))
    stats = RunStats(evidence=[])
    current_stats.set(stats)
    await ctx.http.get("https://a.example.test/")
    assert [(e.status, e.url) for e in stats.evidence] == [
        (302, "https://a.example.test/"),
        (200, "https://b.example.test/x"),
    ]


@respx.mock
async def test_the_stored_url_never_has_the_api_key(monkeypatch, ctx):
    monkeypatch.setenv("OSINEITOR_SHODAN_KEY", "CLAVE-SECRETA-123")
    respx.get(url__startswith="https://api.example.test/").mock(
        return_value=httpx.Response(200, content=b"x")
    )
    stats = RunStats(evidence=[])
    current_stats.set(stats)
    await ctx.http.get(URL, params={"key": "CLAVE-SECRETA-123", "q": "ok"})
    assert stats.evidence[0].url == f"{URL}?key=***&q=ok"
    await ctx.http.get(f"{URL}/CLAVE-SECRETA-123/x")
    assert "CLAVE-SECRETA-123" not in stats.evidence[1].url


# --- motor ----------------------------------------------------------------------------------------


@respx.mock
async def test_engine_ties_each_evidence_to_its_module_and_queried_entity(ctx):
    respx.get(URL).mock(return_value=httpx.Response(200, content=b"cuerpo"))
    result = await Engine(ctx, [fetcher()], evidence=True).run(SEED)
    (item,) = result.evidence
    assert (item.module, item.entity) == ("fetcher", "domain:example.com")
    ip = result.entities[0]
    assert (ip.observations[0].module, ip.observations[0].query) == (item.module, item.entity)
    assert result.evidence_digest == digest([sha(b"cuerpo")])


@respx.mock
async def test_without_the_flag_nothing_is_stored(ctx):
    respx.get(URL).mock(return_value=httpx.Response(200, content=b"cuerpo"))
    result = await Engine(ctx, [fetcher()]).run(SEED)
    assert result.evidence == [] and result.evidence_digest is None


async def test_dns_answers_including_negative_ones_are_evidence(ctx):
    ctx.resolver = FakeResolver(
        {("example.com", "A"): ["93.184.216.34"], ("example.com", "TXT"): ["v=spf1 -all"]}
    )
    result = await Engine(ctx, [Dns], evidence=True).run(SEED)
    by_url = {e.url: e for e in result.evidence}
    assert by_url["dns://example.com/A"].body == b"93.184.216.34"
    assert by_url["dns://example.com/TXT"].body == b"v=spf1 -all"
    assert by_url["dns://example.com/MX"].body == b"NOANSWER"  # no hay MX: también consta
    assert {e.kind for e in result.evidence} == {"dns"}
    assert all(e.method == "DNS" and e.status is None for e in result.evidence)


async def test_email_validate_records_its_mx_lookup(ctx):
    from osineitor.modules.email.validate import EmailValidate

    ctx.resolver = FakeResolver({("example.com", "MX"): ["10 mail.example.com."]})
    seed = Entity(type=EntityType.EMAIL, value="a@example.com")
    result = await Engine(ctx, [EmailValidate], evidence=True).run(seed)
    (item,) = result.evidence
    assert (item.url, item.body) == (
        "dns://example.com/MX",
        b"10 mail.example.com",
    )  # FakeRdata.exchange


# --- almacenamiento y verificación ----------------------------------------------------------------


def saved_scan(storage, bodies: list[bytes]) -> int:
    items = [
        evidence.capture("http", f"{URL}/{i}", b, method="GET", status=200).model_copy(
            update={"module": "fetcher", "entity": SEED.key}
        )
        for i, b in enumerate(bodies)
    ]
    return storage.save(ScanResult(target=SEED, depth=1, evidence=items))


def test_evidence_survives_the_database_roundtrip(storage):
    scan_id = saved_scan(storage, [b"uno", b"dos"])
    loaded = storage.load(scan_id)
    assert [(e.body, e.sha256, e.module, e.entity) for e in loaded.evidence] == [
        (b"uno", sha(b"uno"), "fetcher", SEED.key),
        (b"dos", sha(b"dos"), "fetcher", SEED.key),
    ]
    assert loaded.evidence_digest == digest([sha(b"uno"), sha(b"dos")])


def test_json_has_the_metadata_but_never_the_body(storage):
    scan_id = saved_scan(storage, [b"secreto del cuerpo"])
    dumped = storage.load(scan_id).model_dump_json()
    assert "secreto del cuerpo" not in dumped
    assert json.loads(dumped)["evidence"][0]["sha256"] == sha(b"secreto del cuerpo")


def test_verify_accepts_intact_evidence_and_detects_a_changed_body(storage):
    scan_id = saved_scan(storage, [b"uno", b"dos"])
    ok = evidence.verify(storage.load(scan_id))
    assert (ok.ok, ok.checked, ok.mismatches) == (True, 2, [])
    storage._conn.execute("UPDATE evidence SET body = ? WHERE url LIKE '%/1'", (b"alterado",))
    storage._conn.commit()
    bad = evidence.verify(storage.load(scan_id))
    assert not bad.ok
    (mismatch,) = bad.mismatches
    assert mismatch["number"] == 2 and mismatch["expected"] == sha(b"dos")
    assert mismatch["actual"] == sha(b"alterado")


def test_verify_compares_the_external_digest():
    items = [evidence.capture("http", URL, b"a", method="GET")]
    result = ScanResult(target=SEED, depth=1, evidence=items)
    good = evidence.verify(result, digest([sha(b"a")]).upper())
    assert good.digest_match is True and good.ok
    wrong = evidence.verify(result, "0" * 64)
    assert wrong.digest_match is False and not wrong.ok
    assert evidence.verify(result).digest_match is None


def test_migrating_a_v3_database_adds_the_evidence_table(tmp_path):
    from osineitor.storage import MIGRATIONS, Storage

    path = tmp_path / "v3.db"
    conn = sqlite3.connect(path)
    for statement in "".join(MIGRATIONS[:3]).split(";"):
        if statement.strip():
            conn.execute(statement)
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
    conn.close()
    with Storage(path) as store:
        assert store.load(store.save(ScanResult(target=SEED, depth=1))).evidence == []
        store._conn.execute("SELECT body FROM evidence")  # la tabla existe


# --- CLI ------------------------------------------------------------------------------------------


@pytest.fixture
def http_module(monkeypatch):
    use_modules(monkeypatch, [fetcher()])


@respx.mock
def test_evidence_flag_saves_the_response_and_verify_checks_it(http_module, tmp_path):
    respx.get(URL).mock(return_value=httpx.Response(200, content=b"cuerpo"))
    db = str(tmp_path / "s.db")
    run = runner.invoke(app, ["domain", "example.com", "--evidence", "--db", db, "--json"])
    assert run.exit_code == 0, run.output
    scan = json.loads(run.stdout)
    assert scan["evidence"][0]["sha256"] == sha(b"cuerpo")
    assert scan["evidence_digest"] == digest([sha(b"cuerpo")])

    verified = runner.invoke(app, ["verify", "1", "--db", db, "--json"])
    assert verified.exit_code == 0
    assert json.loads(verified.stdout)["ok"] is True

    conn = sqlite3.connect(db)
    conn.execute("UPDATE evidence SET body = x'00'")
    conn.commit()
    conn.close()
    tampered = runner.invoke(app, ["verify", "1", "--db", db, "--json"])
    assert tampered.exit_code == 5
    assert json.loads(tampered.stdout)["mismatches"][0]["module"] == "fetcher"
    assert runner.invoke(app, ["verify", "1", "--db", db]).exit_code == 5


@respx.mock
def test_verify_with_the_digest_noted_at_scan_time(http_module, tmp_path):
    respx.get(URL).mock(return_value=httpx.Response(200, content=b"cuerpo"))
    db = str(tmp_path / "s.db")
    runner.invoke(app, ["domain", "example.com", "--evidence", "--db", db, "--quiet"])
    noted = digest([sha(b"cuerpo")])
    assert runner.invoke(app, ["verify", "1", "--digest", noted, "--db", db]).exit_code == 0
    assert runner.invoke(app, ["verify", "1", "--digest", "0" * 64, "--db", db]).exit_code == 5


@respx.mock
def test_evidence_does_not_use_the_cache(http_module, tmp_path):
    route = respx.get(URL).mock(return_value=httpx.Response(200, content=b"x"))
    db = str(tmp_path / "s.db")
    for _ in range(2):
        runner.invoke(app, ["domain", "example.com", "--evidence", "--db", db, "--quiet"])
    assert route.call_count == 2  # cada scan consulta de verdad, no sirve una copia vieja


@respx.mock
def test_ndjson_scan_end_carries_the_digest_only_with_evidence(http_module, tmp_path):
    respx.get(URL).mock(return_value=httpx.Response(200, content=b"cuerpo"))
    db = str(tmp_path / "s.db")

    def last_event(*extra: str) -> dict:
        out = runner.invoke(app, ["domain", "example.com", "--ndjson", "--db", db, *extra]).stdout
        return json.loads(out.splitlines()[-1])

    assert last_event("--evidence")["evidence_digest"] == digest([sha(b"cuerpo")])
    assert "evidence_digest" not in last_event()


def test_verify_without_evidence_and_with_an_unknown_scan(tmp_path):
    from osineitor.storage import Storage

    db = tmp_path / "s.db"
    with Storage(db) as store:
        store.save(ScanResult(target=SEED, depth=1))
    plain = runner.invoke(app, ["verify", "1", "--db", str(db), "--json"])
    assert plain.exit_code == 0 and json.loads(plain.stdout)["checked"] == 0
    assert runner.invoke(app, ["verify", "99", "--db", str(db)]).exit_code == 2


def test_no_save_warns_that_evidence_is_not_kept(http_module):
    res = runner.invoke(app, ["domain", "example.com", "--evidence", "--no-save", "--quiet"])
    assert "las evidencias no se guardan" in res.output


@respx.mock
def test_evidence_outputs_match_the_contract_schema(http_module, tmp_path):
    from tests.test_contract import parse_events, validate

    respx.get(URL).mock(return_value=httpx.Response(200, content=b"cuerpo"))
    db = str(tmp_path / "s.db")
    streamed = runner.invoke(app, ["domain", "example.com", "--evidence", "--ndjson", "--db", db])
    assert "evidence_digest" in parse_events(streamed.stdout)[-1]
    shown = runner.invoke(app, ["show", "1", "--db", db, "--json"])
    validate("scan_result", json.loads(shown.stdout))
    for extra in ([], ["--digest", "0" * 64]):
        checked = runner.invoke(app, ["verify", "1", "--db", db, "--json", *extra])
        validate("verify_output", json.loads(checked.stdout))
