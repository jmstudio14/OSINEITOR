from __future__ import annotations

import pytest
from pydantic import ValidationError

from osineitor.errors import InvalidEntityValue
from osineitor.models import Entity, EntityType, detect_type
from osineitor.normalize import (
    canonical,
    canonical_email,
    canonical_hostname,
    canonical_ip,
    canonical_url,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("EXAMPLE.com.", "example.com"),
        ("  Sub.Example.COM  ", "sub.example.com"),
        ("münchen.de", "xn--mnchen-3ya.de"),
        ("xn--mnchen-3ya.de", "xn--mnchen-3ya.de"),
        ("MÜNCHEN.DE.", "xn--mnchen-3ya.de"),
        ("_dmarc.example.com", "_dmarc.example.com"),
        ("localhost", "localhost"),
    ],
)
def test_hostname_canonical_form(raw, expected):
    assert canonical_hostname(raw) == expected


@pytest.mark.parametrize(
    "raw", ["", ".", "a b.com", "-a.com", "a-.com", "a..com", "a" * 64 + ".com", "ex$ample.com"]
)
def test_hostname_rejects(raw):
    with pytest.raises(InvalidEntityValue):
        canonical_hostname(raw)


def test_hostname_rejects_too_long_name():
    with pytest.raises(InvalidEntityValue):
        canonical_hostname(".".join(["a" * 60] * 5) + ".com")


def test_ip_canonical_form():
    assert canonical_ip(" 8.8.8.8 ") == "8.8.8.8"
    assert canonical_ip("2001:0DB8:0000:0000:0000:0000:0000:0001") == "2001:db8::1"
    with pytest.raises(InvalidEntityValue):
        canonical_ip("999.1.1.1")


def test_email_canonical_form():
    assert canonical_email(" Jane@MÜNCHEN.de ") == "jane@xn--mnchen-3ya.de"
    assert canonical_email("a+tag@Example.com") == "a+tag@example.com"


@pytest.mark.parametrize("raw", ["not-an-email", "@x.com", "a b@x.com", "a@", "a@@"])
def test_email_rejects(raw):
    with pytest.raises(InvalidEntityValue):
        canonical_email(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("HTTP://Example.COM:80/a?b=1#frag", "http://example.com/a?b=1"),
        ("https://example.com:443/", "https://example.com/"),
        ("https://Example.com:8443/x", "https://example.com:8443/x"),
        ("http://[::1]:8080/x", "http://[::1]:8080/x"),
        ("https://münchen.de/ü", "https://xn--mnchen-3ya.de/ü"),
        ("not a url", "not a url"),
        ("http://exa mple.com/", "http://exa mple.com/"),
    ],
)
def test_url_is_normalized_on_a_best_effort_basis(raw, expected):
    assert canonical_url(raw) == expected


def test_canonical_leaves_other_types_untouched():
    assert canonical("record", "dns:Example.COM") == "dns:Example.COM"
    assert canonical("service", "1.2.3.4:80") == "1.2.3.4:80"


def test_entity_values_are_canonical_on_creation():
    domain = Entity(type=EntityType.DOMAIN, value="EXAMPLE.com.")
    assert domain.value == "example.com"
    assert domain.key == "domain:example.com"
    assert Entity(type=EntityType.USERNAME, value="@JDoe").value == "JDoe"
    assert Entity(type=EntityType.USERNAME, value="JDoe").key == "username:jdoe"


def test_same_domain_written_two_ways_is_one_entity():
    a = Entity(type=EntityType.DOMAIN, value="münchen.de")
    b = Entity(type=EntityType.DOMAIN, value="XN--MNCHEN-3YA.DE.")
    assert a.key == b.key


@pytest.mark.parametrize(
    ("etype", "value"),
    [
        (EntityType.DOMAIN, "bad domain"),
        (EntityType.IP, "300.1.1.1"),
        (EntityType.EMAIL, "nope"),
        (EntityType.USERNAME, "a/b"),
    ],
)
def test_invalid_entities_are_rejected(etype, value):
    with pytest.raises(ValidationError):
        Entity(type=etype, value=value)


def test_detect_type_handles_idn_and_underscores():
    assert detect_type("münchen.de") == EntityType.DOMAIN
    assert detect_type("example.xn--p1ai") == EntityType.DOMAIN
    assert detect_type("john_doe") == EntityType.USERNAME
    assert detect_type("a/b") == EntityType.USERNAME
