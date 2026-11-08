"""Fase 6, módulos con key. Las respuestas salen de la documentación de cada API, no de la fuente
real: comprueban el código, no que la API siga contestando así (criterio D1)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from typer.testing import CliRunner

from osineitor.cli import app
from osineitor.config import Config
from osineitor.doctor import seed_entity
from osineitor.engine import Engine
from osineitor.http import HttpClient
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Context, ModuleError, ModuleQuota
from osineitor.modules.crypto.eth_explorer import EthExplorer
from osineitor.modules.domain.github_code import GithubCode, find_secrets
from osineitor.modules.domain.search_dorks import DORKS, SearchDorks
from osineitor.modules.domain.virustotal import VirusTotal
from osineitor.modules.files.hashes import FileHash
from osineitor.modules.ip.abusech import AbuseCh
from osineitor.modules.org.gleif import Gleif
from osineitor.modules.org.opensanctions import OpenSanctions
from tests.test_cli import use_modules

runner = CliRunner()
SHA256 = "a" * 64
DOMAIN = Entity(type=EntityType.DOMAIN, value="example.com")
# Por trozos: ni el escáner de secretos de GitHub ni un lector deben tomarlo por uno real.
FAKE_AWS = "AKIA" + "IOSFODNN7EXAMPLE"
FAKE_PASSWORD = "hunter2-" + "no-es-real"


@pytest.fixture
async def keyed():
    config = Config(
        keys={
            name: "CLAVE"
            for name in ("opensanctions", "etherscan", "virustotal", "abusech", "brave", "github")
        }
    )
    http = HttpClient(config, backoff=0)
    yield Context(config=config, http=http)
    await http.aclose()


def file_hash_record() -> Entity:
    return Entity(type=EntityType.RECORD, value=f"file_hash:{SHA256}")


# --- opensanctions ---------------------------------------------------------------------------


MATCH_URL = "https://api.opensanctions.org/match/default"


def match_response(*results: dict) -> httpx.Response:
    return httpx.Response(200, json={"responses": {"q": {"status": 200, "results": list(results)}}})


def test_opensanctions_ignores_github_organizations(keyed):
    module = OpenSanctions(keyed)
    assert module.accepts(Entity(type=EntityType.ORGANIZATION, value="Acme"))
    assert module.accepts(Entity(type=EntityType.PERSON, value="Ana Ruiz"))
    github = Entity(type=EntityType.ORGANIZATION, value="acme", data={"platform": "github"})
    assert not module.accepts(github)


def test_doctor_seeds_opensanctions_as_an_organization():
    entity = seed_entity(OpenSanctions)
    assert (entity.type, entity.value) == (EntityType.ORGANIZATION, "Gazprom")
    assert seed_entity(Gleif).type == EntityType.ORGANIZATION


@respx.mock
async def test_opensanctions_keeps_only_real_matches_and_sends_the_schema(keyed):
    route = respx.post(MATCH_URL).mock(
        return_value=match_response(
            {
                "id": "NK-1",
                "caption": "Acme Ltd",
                "schema": "Company",
                "score": 0.93,
                "match": True,
                "datasets": ["us_ofac_sdn"],
                "properties": {"topics": ["sanction"]},
                "first_seen": "2020-01-01T00:00:00Z",
            },
            {"id": "NK-2", "caption": "Otra", "match": False},
        )
    )
    entity = Entity(type=EntityType.ORGANIZATION, value="Acme Ltd")
    [record] = await OpenSanctions(keyed).run(entity)
    assert record.value == "opensanctions:NK-1"
    assert record.data["topics"] == ["sanction"]
    assert record.data["url"] == "https://www.opensanctions.org/entities/NK-1/"
    request = route.calls.last.request
    assert request.headers["authorization"] == "ApiKey CLAVE"
    assert json.loads(request.content)["queries"]["q"] == {
        "schema": "Organization",
        "properties": {"name": ["Acme Ltd"]},
    }


@respx.mock
@pytest.mark.parametrize(
    ("status", "error"), [(401, ModuleError), (403, ModuleError), (429, ModuleQuota)]
)
async def test_opensanctions_errors(keyed, status, error):
    respx.post(MATCH_URL).mock(return_value=httpx.Response(status))
    with pytest.raises(error):
        await OpenSanctions(keyed).run(Entity(type=EntityType.PERSON, value="Ana Ruiz"))


# --- eth_explorer ----------------------------------------------------------------------------


ETH = "0xde0b295669a9fd93d5f28d9ec85e40f4cb697bae"
ETH_URL = "https://api.etherscan.io/v2/api"


def crypto(value: str = ETH) -> Entity:
    return Entity(type=EntityType.CRYPTO_ADDRESS, value=value)


def etherscan(request: httpx.Request) -> httpx.Response:
    params = dict(request.url.params)
    assert params["chainid"] == "1"
    if params["action"] == "balance":
        result = "1500000000000000000"
    else:
        stamp = "1000" if params["sort"] == "asc" else "2000"
        result = [{"timeStamp": stamp}]
    return httpx.Response(200, json={"status": "1", "message": "OK", "result": result})


def test_eth_explorer_only_takes_ethereum_addresses(keyed):
    module = EthExplorer(keyed)
    assert module.accepts(crypto())
    assert not module.accepts(crypto("bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq"))


@respx.mock
async def test_eth_explorer_balance_and_activity(keyed):
    respx.get(ETH_URL).mock(side_effect=etherscan)
    [record] = await EthExplorer(keyed).run(crypto())
    assert record.value == f"eth:{ETH}"
    assert record.data["balance_wei"] == "1500000000000000000"
    assert record.data["balance_eth"] == "1.5"
    assert record.data["first_activity"] == "1970-01-01T00:16:40Z"
    assert record.data["last_activity"] == "1970-01-01T00:33:20Z"


@respx.mock
async def test_eth_explorer_without_transactions_is_not_an_error(keyed):
    def empty(request: httpx.Request) -> httpx.Response:
        if request.url.params["action"] == "balance":
            return httpx.Response(200, json={"status": "1", "message": "OK", "result": "0"})
        body = {"status": "0", "message": "No transactions found", "result": []}
        return httpx.Response(200, json=body)

    respx.get(ETH_URL).mock(side_effect=empty)
    [record] = await EthExplorer(keyed).run(crypto())
    assert record.data["balance_eth"] == "0"
    assert record.data["first_activity"] is None


@respx.mock
@pytest.mark.parametrize(
    ("result", "error"),
    [("Invalid API Key", ModuleError), ("Max rate limit reached", ModuleQuota)],
)
async def test_eth_explorer_reports_errors_sent_with_status_200(keyed, result, error):
    body = {"status": "0", "message": "NOTOK", "result": result}
    respx.get(ETH_URL).mock(return_value=httpx.Response(200, json=body))
    with pytest.raises(error):
        await EthExplorer(keyed).run(crypto())


# --- reputación de un hash (F6.10) -----------------------------------------------------------


def test_reputation_modules_only_take_the_record_of_file_hash(keyed):
    other = Entity(type=EntityType.RECORD, value="wayback:example.com")
    for module in (VirusTotal(keyed), AbuseCh(keyed)):
        assert module.accepts(file_hash_record())
        assert not module.accepts(other)
        assert module.accepts(DOMAIN)


@respx.mock
async def test_virustotal_reports_a_known_hash(keyed):
    respx.get(f"https://www.virustotal.com/api/v3/files/{SHA256}").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "attributes": {
                        "last_analysis_stats": {"malicious": 7, "harmless": 1},
                        "meaningful_name": "dropper.exe",
                        "type_description": "Win32 EXE",
                    }
                }
            },
        )
    )
    [record] = await VirusTotal(keyed).run(file_hash_record())
    assert record.value == f"virustotal:{SHA256}"
    assert record.data["malicious"] == 7
    assert record.data["meaningful_name"] == "dropper.exe"


@respx.mock
async def test_virustotal_does_not_know_the_hash(keyed):
    respx.get(f"https://www.virustotal.com/api/v3/files/{SHA256}").mock(
        return_value=httpx.Response(404)
    )
    assert await VirusTotal(keyed).run(file_hash_record()) == []


@respx.mock
async def test_malwarebazaar_reports_a_known_hash_and_receives_only_the_hash(keyed):
    route = respx.post("https://mb-api.abuse.ch/api/v1/").mock(
        return_value=httpx.Response(
            200,
            json={
                "query_status": "ok",
                "data": [{"signature": "Adwind", "file_type": "jar", "tags": ["jar"]}],
            },
        )
    )
    [record] = await AbuseCh(keyed).run(file_hash_record())
    assert record.value == f"abusech:{SHA256}"
    assert record.data["malware"] == "Adwind"
    request = route.calls.last.request
    assert request.headers["auth-key"] == "CLAVE"
    assert parse_qs(request.content.decode()) == {"query": ["get_info"], "hash": [SHA256]}


@respx.mock
async def test_malwarebazaar_does_not_know_the_hash(keyed):
    respx.post("https://mb-api.abuse.ch/api/v1/").mock(
        return_value=httpx.Response(200, json={"query_status": "hash_not_found"})
    )
    assert await AbuseCh(keyed).run(file_hash_record()) == []


@respx.mock
async def test_the_file_content_never_leaves_only_its_hash(keyed, tmp_path):
    secret = b"contenido privado del fichero"
    path = tmp_path / "privado.bin"
    path.write_bytes(secret)
    digest = hashlib.sha256(secret).hexdigest()
    vt = respx.get(f"https://www.virustotal.com/api/v3/files/{digest}").mock(
        return_value=httpx.Response(404)
    )
    bazaar = respx.post("https://mb-api.abuse.ch/api/v1/").mock(
        return_value=httpx.Response(200, json={"query_status": "hash_not_found"})
    )
    seed = Entity(type=EntityType.FILE, value=str(path))
    await Engine(keyed, [FileHash, VirusTotal, AbuseCh], depth=2).run(seed)
    assert vt.called
    assert bazaar.called
    for call in [*vt.calls, *bazaar.calls]:
        assert secret not in call.request.content
        assert str(path) not in str(call.request.url)


@respx.mock
async def test_at_depth_one_the_hash_does_not_leave(keyed, tmp_path):
    path = tmp_path / "privado.bin"
    path.write_bytes(b"x")
    catch_all = respx.route().mock(return_value=httpx.Response(200))
    seed = Entity(type=EntityType.FILE, value=str(path))
    await Engine(keyed, [FileHash, VirusTotal, AbuseCh], depth=1).run(seed)
    assert not catch_all.called


# --- search_dorks ----------------------------------------------------------------------------


BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"


@respx.mock
async def test_search_dorks_keeps_urls_of_the_domain_and_marks_documents(keyed):
    route = respx.get(BRAVE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {"url": "https://www.example.com/informe.PDF", "title": "Informe"},
                        {"url": "https://example.com/listado/", "title": "Index of /listado"},
                        {"url": "https://example.com.evil.test/a.pdf", "title": "Ajeno"},
                        {"url": "no es una url", "title": "Roto"},
                    ]
                }
            },
        )
    )
    found = await SearchDorks(keyed).run(DOMAIN)
    assert route.call_count == len(DORKS)
    assert route.calls[0].request.headers["x-subscription-token"] == "CLAVE"
    assert route.calls[0].request.url.params["q"] == "site:example.com filetype:pdf"
    urls = {e.value: e.data for e in found}
    assert set(urls) == {"https://www.example.com/informe.PDF", "https://example.com/listado/"}
    assert urls["https://www.example.com/informe.PDF"]["document"] is True
    assert urls["https://example.com/listado/"]["document"] is None


@respx.mock
async def test_search_dorks_with_a_bad_key_fails(keyed):
    respx.get(BRAVE_URL).mock(return_value=httpx.Response(401))
    with pytest.raises(ModuleError):
        await SearchDorks(keyed).run(DOMAIN)


# --- github_code -----------------------------------------------------------------------------


GITHUB_URL = "https://api.github.com/search/code"


def github_items() -> dict:
    return {
        "total_count": 2,
        "items": [
            {
                "path": "config/prod.py",
                "html_url": "https://github.com/acme/app/blob/abc/config/prod.py",
                "repository": {"full_name": "acme/app"},
                "text_matches": [
                    {
                        "fragment": (
                            f'API = "api.example.com"\nAWS = "{FAKE_AWS}"\n'
                            f'password = "{FAKE_PASSWORD}"\n'
                        )
                    }
                ],
            },
            {
                "path": "README.md",
                "html_url": "https://github.com/acme/web/blob/abc/README.md",
                "repository": {"full_name": "acme/web"},
                "text_matches": [{"fragment": "Visita example.com"}],
            },
            {"path": "sin-repositorio.txt"},
        ],
    }


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        (FAKE_AWS, "aws_access_key"),
        ("ghp_" + "a1" * 18, "github_token"),
        ("github_pat_" + "a" * 22, "github_token"),
        ("xoxb-" + "1234567890-abcdef", "slack_token"),
        ("AIza" + "b" * 35, "google_api_key"),
        ("-----BEGIN RSA " + "PRIVATE KEY-----", "private_key"),
        ("https://user:" + "s3cretvalue@db.example.com/", "url_credentials"),
        ('api_key = "' + 'abcdef123456"', "assignment"),
    ],
)
def test_each_rule_finds_its_secret(text, rule):
    assert rule in find_secrets(text).values()


def test_rules_do_not_fire_on_ordinary_code():
    assert find_secrets('URL = "https://api.example.com/v1/users"\nprint(token)\n') == {}


def test_fingerprint_is_partial_and_stable():
    [fingerprint] = find_secrets(FAKE_AWS)
    assert fingerprint == hashlib.sha256(FAKE_AWS.encode()).hexdigest()[:16]


@respx.mock
async def test_github_code_records_rules_and_fingerprints_but_never_the_value(keyed):
    route = respx.get(GITHUB_URL).mock(return_value=httpx.Response(200, json=github_items()))
    records = await GithubCode(keyed).run(DOMAIN)
    assert [r.value for r in records] == [
        "github_code:acme/app/config/prod.py",
        "github_code:acme/web/README.md",
    ]
    assert records[0].data["rules"] == ["assignment", "aws_access_key"]
    assert len(records[0].data["fingerprints"]) == 2
    assert records[1].data["rules"] == []
    dumped = json.dumps([r.model_dump(mode="json") for r in records])
    assert FAKE_AWS not in dumped
    assert FAKE_PASSWORD not in dumped
    request = route.calls.last.request
    assert request.url.params["q"] == '"example.com"'
    assert "text-match" in request.headers["accept"]


@respx.mock
@pytest.mark.parametrize(
    ("status", "headers", "error"),
    [
        (401, {}, ModuleError),
        (403, {}, ModuleError),
        (403, {"retry-after": "60"}, ModuleQuota),
        (403, {"x-ratelimit-remaining": "0"}, ModuleQuota),
    ],
)
async def test_github_code_errors(keyed, status, headers, error):
    respx.get(GITHUB_URL).mock(return_value=httpx.Response(status, headers=headers))
    with pytest.raises(error):
        await GithubCode(keyed).run(DOMAIN)


def test_the_secret_reaches_neither_the_database_nor_the_reports(monkeypatch, tmp_path):
    """Criterio de la fase 6, con `--evidence`, que guardaría la respuesta original."""
    monkeypatch.setenv("OSINEITOR_GITHUB_KEY", "CLAVE")
    use_modules(monkeypatch, [GithubCode])
    db = tmp_path / "scans.sqlite"
    with respx.mock:
        respx.get(GITHUB_URL).mock(return_value=httpx.Response(200, json=github_items()))
        result = runner.invoke(
            app, ["scan", "example.com", "--evidence", "--db", str(db), "--json"]
        )
    assert result.exit_code == 0, result.output
    assert FAKE_AWS not in result.output
    assert "acme/app/config/prod.py" in result.output

    with sqlite3.connect(db) as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        [(body,)] = connection.execute("SELECT body FROM evidence").fetchall()
    connection.close()
    assert b"omitido" in bytes(body)
    for path in tmp_path.glob("scans.sqlite*"):
        raw = path.read_bytes()
        assert FAKE_AWS.encode() not in raw
        assert FAKE_PASSWORD.encode() not in raw

    verified = runner.invoke(app, ["verify", "1", "--db", str(db)])
    assert verified.exit_code == 0, verified.output  # la evidencia sin cuerpo sigue cuadrando

    for fmt in ("html", "md", "json", "csv"):
        out = tmp_path / f"informe.{fmt}"
        exported = runner.invoke(app, ["export", "1", "-f", fmt, "--db", str(db), "-o", str(out)])
        assert exported.exit_code == 0, exported.output
        text = out.read_text(encoding="utf-8")
        assert FAKE_AWS not in text
        assert FAKE_PASSWORD not in text
