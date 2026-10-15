"""Tests for ISBN normalization and the Open Library lookup (network mocked)."""

from unittest.mock import MagicMock, patch

import pytest

from bibtui.bib.isbn import fetch_by_isbn
from bibtui.utils.isbn import normalize_isbn


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("978-0-262-03561-3", "9780262035613"),
        ("978 0 262 03561 3", "9780262035613"),
        ("0-262-03561-8", "9780262035613"),  # ISBN-10 → ISBN-13
        ("0-8044-2957-X", "9780804429573"),  # X check digit
        ("978-0-262-03561-4", None),  # bad checksum
        ("0-262-03561-9", None),
        ("123", None),
        ("", None),
    ],
)
def test_normalize_isbn(raw, expected) -> None:
    assert normalize_isbn(raw) == expected


def _response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


def test_fetch_by_isbn_builds_book_entry() -> None:
    payload = {
        "ISBN:9780262035613": {
            "title": "Deep Learning",
            "subtitle": "Adaptive Computation",
            "authors": [{"name": "Ian Goodfellow"}, {"name": "Yoshua Bengio"}],
            "publishers": [{"name": "MIT Press"}],
            "publish_places": [{"name": "Cambridge, MA"}],
            "publish_date": "3 January 2017",
        }
    }
    with patch("bibtui.bib.isbn.httpx.get", return_value=_response(payload)):
        entry = fetch_by_isbn("0-262-03561-8")

    assert entry.entry_type == "book"
    assert entry.key == "Goodfellow2017"
    assert entry.title == "Deep Learning: Adaptive Computation"
    assert entry.author == "Goodfellow, Ian and Bengio, Yoshua"
    assert entry.year == "2017"
    assert entry.raw_fields["isbn"] == "9780262035613"
    assert entry.raw_fields["publisher"] == "MIT Press"
    assert entry.raw_fields["address"] == "Cambridge, MA"


def test_fetch_by_isbn_unknown_raises_lookup_error() -> None:
    with patch("bibtui.bib.isbn.httpx.get", return_value=_response({})):
        with pytest.raises(LookupError):
            fetch_by_isbn("9780262035613")


def test_fetch_by_isbn_rejects_invalid_isbn() -> None:
    with pytest.raises(ValueError):
        fetch_by_isbn("978-0-262-03561-4")
