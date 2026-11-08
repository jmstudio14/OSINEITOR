"""F5.9: entidad `person`, orden `person` y generadores de candidatos (sin red)."""

from __future__ import annotations

import json

import pytest
import respx
from click import unstyle
from typer.testing import CliRunner

from osineitor import registry
from osineitor.cli import app
from osineitor.engine import Engine
from osineitor.models import Entity, EntityType
from osineitor.modules.username.person import (
    EmailCandidates,
    UsernameVariants,
    combine,
    name_parts,
)

runner = CliRunner()
PERSON = Entity(type=EntityType.PERSON, value="María José García López")
WITH_DOMAIN = Entity(
    type=EntityType.PERSON, value="María José García López", data={"domain": "example.com"}
)


def test_name_parts_strip_accents_particles_and_signs():
    assert name_parts("María José García López") == ("maria", ["jose", "lopez"])
    assert name_parts("Ana de la Cruz") == ("ana", ["cruz"])
    assert name_parts("Ñandú O'Brien") == ("nandu", ["obrien"])
    assert name_parts("Cher") == ("cher", [])
    assert name_parts("de la") == ("", [])


def test_combine_is_ordered_unique_and_capped(monkeypatch):
    found = combine("Ana García", (("a", "{f}.{l}"), ("b", "{f}.{l}"), ("c", "{f}{l}")))
    assert found == [("ana.garcia", "a"), ("anagarcia", "c")]
    assert combine("Cher", (("a", "{f}"),)) == []  # sin apellido no hay combinaciones
    monkeypatch.setattr("osineitor.modules.username.person.MAX_CANDIDATES", 2)
    assert len(combine("Ana García", (("a", "{f}.{l}"), ("b", "{f}{l}"), ("c", "{l}.{f}")))) == 2


@respx.mock  # sin rutas: cualquier petición HTTP fallaría
async def test_username_variants_make_no_requests_and_are_marked_candidates(ctx):
    out = await UsernameVariants(ctx).run(PERSON)
    values = [e.value for e in out]
    assert values[:3] == ["maria.jose", "mariajose", "mjose"]
    assert "maria.lopez" in values
    assert all(e.type == EntityType.USERNAME and e.data["candidate"] for e in out)
    assert len(values) == len(set(values)) <= 12


@respx.mock
async def test_email_candidates_need_a_domain_and_are_never_verified(ctx):
    assert not EmailCandidates(ctx).accepts(PERSON)
    assert EmailCandidates(ctx).accepts(WITH_DOMAIN)
    out = await EmailCandidates(ctx).run(WITH_DOMAIN)
    assert out[0].value == "maria.jose@example.com"
    assert out[0].data == {"candidate": True, "pattern": "{f}.{l}"}
    assert {e.value for e in out} >= {"mjose@example.com", "maria@example.com"}
    assert all(e.type == EntityType.EMAIL for e in out)


async def test_the_engine_pivots_from_a_person_to_its_candidates(ctx):
    result = await Engine(ctx, [UsernameVariants, EmailCandidates]).run(WITH_DOMAIN)
    kinds = {e.type for e in result.entities}
    assert kinds == {EntityType.USERNAME, EntityType.EMAIL}


def test_person_command_passes_the_domain_to_the_seed(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "discover", lambda: [UsernameVariants, EmailCandidates])
    result = runner.invoke(
        app, ["person", "Ana García", "--domain", "Example.COM", "--no-save", "--json"]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert (data["target"]["type"], data["target"]["value"]) == ("person", "Ana García")
    values = [e["value"] for e in data["entities"]]
    assert "ana.garcia" in values
    assert "ana.garcia@example.com" in values


def test_person_command_without_domain_gives_only_usernames(monkeypatch):
    monkeypatch.setattr(registry, "discover", lambda: [UsernameVariants, EmailCandidates])
    result = runner.invoke(app, ["person", "Ana García", "--no-save", "--json"])
    types = {e["type"] for e in json.loads(result.output)["entities"]}
    assert types == {"username"}


def test_person_command_rejects_a_bad_domain():
    result = runner.invoke(app, ["person", "Ana García", "--domain", "no es un dominio"])
    assert result.exit_code == 2


@pytest.mark.parametrize("name", ["username_variants", "email_candidates"])
def test_generators_are_registered_passive_and_offline_only(name):
    module = next(m for m in registry.discover() if m.name == name)
    assert module.passive
    assert module.consumes == frozenset({EntityType.PERSON})


def test_a_person_scan_requires_purpose_when_configured(monkeypatch):
    monkeypatch.setenv("OSINEITOR_REQUIRE_PURPOSE", "1")
    result = runner.invoke(app, ["person", "Ana García", "--no-save"])
    assert result.exit_code == 2
    assert "--purpose" in unstyle(result.output)
