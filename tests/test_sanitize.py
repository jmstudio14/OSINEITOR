from __future__ import annotations

import pytest

from osineitor.errors import InvalidEntityValue
from osineitor.sanitize import clean_username, is_valid_username, quote_segment


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("john.doe", "john.doe"), ("@john", "john"), ("José_9", "José_9"), (" a-b ", "a-b")],
)
def test_clean_username_accepts(raw, expected):
    assert clean_username(raw) == expected


@pytest.mark.parametrize(
    "raw", ["", "a/b", "a/../b", "x?y", "x#z", "a b", "50%", "a:b", "u@host", "x" * 65, "a\nb"]
)
def test_clean_username_rejects(raw):
    with pytest.raises(InvalidEntityValue):
        clean_username(raw)
    assert not is_valid_username(raw)


def test_quote_segment_leaves_no_url_delimiters():
    assert quote_segment("a/../b") == "a%2F..%2Fb"
    assert quote_segment("x?y#z") == "x%3Fy%23z"
    assert quote_segment("a b") == "a%20b"
    assert quote_segment("ñandú") == "%C3%B1and%C3%BA"
