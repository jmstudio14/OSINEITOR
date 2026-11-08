"""F7.10: resolución de entidades. Todo es una hipótesis, nunca una identidad confirmada."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from osineitor import report, resolve
from osineitor.cli import app
from osineitor.models import Entity, EntityType, ScanResult
from osineitor.storage import Storage

runner = CliRunner()
SEED = Entity(type=EntityType.USERNAME, value="maria_perez_dev")


def profile(url, parent, **data) -> Entity:
    return Entity(type=EntityType.PROFILE, value=url, parent=parent.key, data=data)


def scan(*entities: Entity, seed: Entity = SEED) -> ScanResult:
    return ScanResult(target=seed, depth=2, entities=list(entities))


def test_accounts_found_for_the_same_username_form_a_hypothesis():
    a = profile("https://github.com/maria_perez_dev", SEED, site="GitHub")
    b = profile("https://gitlab.com/maria_perez_dev", SEED, site="GitLab")
    [h] = resolve.hypotheses(scan(a, b))
    assert h["label"] == "hipótesis"
    assert h["accounts"] == sorted([a.key, b.key])
    assert h["signals"] == [{"kind": "username", "value": "maria_perez_dev", "weight": 0.4}]
    assert h["score"] == 0.4


def test_short_usernames_are_too_common_to_group_on_their_own():
    seed = Entity(type=EntityType.USERNAME, value="juan")
    a = profile("https://github.com/juan", seed)
    b = profile("https://gitlab.com/juan", seed)
    assert resolve.hypotheses(scan(a, b, seed=seed)) == []


def test_independent_signals_reinforce_but_never_reach_certainty():
    email = Entity(type=EntityType.EMAIL, value="maria@example.com", parent=SEED.key)
    other = Entity(type=EntityType.USERNAME, value="mperez", parent=email.key)
    a = profile("https://github.com/maria_perez_dev", SEED, site="GitHub", name="María Pérez")
    b = profile("https://gravatar.com/mperez", other, site="Gravatar", display_name="MARÍA PÉREZ")
    c = profile("https://example.org/mperez", email, site="Otro")
    [h] = resolve.hypotheses(scan(email, other, a, b, c))
    kinds = {s["kind"] for s in h["signals"]}
    assert {"email", "display_name", "username"} <= kinds
    assert 0.6 < h["score"] <= resolve.MAX_SCORE < 1


def test_unrelated_accounts_are_not_grouped():
    other = Entity(type=EntityType.USERNAME, value="otra_persona_x")
    a = profile("https://github.com/maria_perez_dev", SEED)
    b = profile("https://github.com/otra_persona_x", other, name="Otra")
    assert resolve.hypotheses(scan(a, b, other)) == []


def test_a_single_word_name_is_not_a_signal():
    a = profile("https://a.example/1", SEED, name="María")
    b = profile(
        "https://b.example/2", Entity(type=EntityType.USERNAME, value="zzzzzz"), name="maría"
    )
    assert resolve.hypotheses(scan(a, b)) == []


def test_markdown_report_labels_hypotheses():
    a = profile("https://github.com/maria_perez_dev", SEED, site="GitHub")
    b = profile("https://gitlab.com/maria_perez_dev", SEED, site="GitLab")
    text = report.render(scan(a, b), "md")
    assert "## Hipótesis de identidad" in text and "no una identidad confirmada" in text
    assert "## Hipótesis de identidad" not in report.render(scan(), "md")


def test_cli_resolve_json_and_table(tmp_path):
    a = profile("https://github.com/maria_perez_dev", SEED)
    b = profile("https://gitlab.com/maria_perez_dev", SEED)
    db = tmp_path / "r.db"
    with Storage(db) as store:
        store.save(scan(a, b))
        store.save(scan())
    data = json.loads(runner.invoke(app, ["resolve", "1", "--db", str(db), "--json"]).stdout)
    assert data["scan_id"] == 1 and data["hypotheses"][0]["label"] == "hipótesis"
    assert "Hipótesis" in runner.invoke(app, ["resolve", "1", "--db", str(db)]).stdout
    assert "Sin hipótesis" in runner.invoke(app, ["resolve", "2", "--db", str(db)]).stdout
    assert runner.invoke(app, ["resolve", "9", "--db", str(db)]).exit_code != 0
