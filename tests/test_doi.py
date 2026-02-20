"""Unit tests for bib_tui.bib.doi — all network calls mocked."""

from unittest.mock import MagicMock, patch

import pytest

from bibtui.bib.doi import fetch_by_doi


def _make_msg(**overrides) -> dict:
    """Minimal Crossref message dict for a journal article."""
    base = {
        "type": "journal-article",
        "title": ["Glacial Dynamics in the 21st Century"],
        "author": [
            {"family": "Smith", "given": "John"},
            {"family": "Jones", "given": "Mary"},
        ],
        "published-print": {"date-parts": [[2023, 6, 1]]},
        "container-title": ["Nature"],
        "DOI": "10.1000/test",
    }
    base.update(overrides)
    return base


def _mock_cr(msg: dict):
    cr = MagicMock()
    cr.works.return_value = {"message": msg}
    return cr


# ---------------------------------------------------------------------------
# Basic field extraction
# ---------------------------------------------------------------------------


def test_fetch_title() -> None:
    with patch("bibtui.bib.doi.Crossref", return_value=_mock_cr(_make_msg())):
        e = fetch_by_doi("10.1000/test")
    assert e.title == "Glacial Dynamics in the 21st Century"


def test_fetch_author_string() -> None:
    with patch("bibtui.bib.doi.Crossref", return_value=_mock_cr(_make_msg())):
        e = fetch_by_doi("10.1000/test")
    assert e.author == "Smith, John and Jones, Mary"


def test_fetch_year() -> None:
    with patch("bibtui.bib.doi.Crossref", return_value=_mock_cr(_make_msg())):
        e = fetch_by_doi("10.1000/test")
    assert e.year == "2023"


def test_fetch_journal() -> None:
    with patch("bibtui.bib.doi.Crossref", return_value=_mock_cr(_make_msg())):
        e = fetch_by_doi("10.1000/test")
    assert e.journal == "Nature"


def test_fetch_doi_stored() -> None:
    with patch("bibtui.bib.doi.Crossref", return_value=_mock_cr(_make_msg())):
        e = fetch_by_doi("10.1000/test")
    assert e.doi == "10.1000/test"


def test_fetch_entry_type_article() -> None:
    with patch("bibtui.bib.doi.Crossref", return_value=_mock_cr(_make_msg())):
        e = fetch_by_doi("10.1000/test")
    assert e.entry_type == "article"


def test_citation_key_format() -> None:
    with patch("bibtui.bib.doi.Crossref", return_value=_mock_cr(_make_msg())):
        e = fetch_by_doi("10.1000/test")
    assert e.key == "Smith2023"


# ---------------------------------------------------------------------------
# Type mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "crossref_type,expected",
    [
        ("journal-article", "article"),
        ("proceedings-article", "inproceedings"),
        ("book", "book"),
        ("book-chapter", "incollection"),
        ("dissertation", "phdthesis"),
        ("report", "techreport"),
        ("dataset", "misc"),
        ("posted-content", "misc"),
        ("unknown-type", "misc"),  # fallback
    ],
)
def test_entry_type_mapping(crossref_type: str, expected: str) -> None:
    msg = _make_msg(type=crossref_type)
    with patch("bibtui.bib.doi.Crossref", return_value=_mock_cr(msg)):
        e = fetch_by_doi("10.1000/test")
    assert e.entry_type == expected


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_author_family_only() -> None:
    msg = _make_msg(author=[{"family": "Plato"}])
    with patch("bibtui.bib.doi.Crossref", return_value=_mock_cr(msg)):
        e = fetch_by_doi("10.1000/test")
    assert e.author == "Plato"


def test_no_authors_uses_unknown_key() -> None:
    msg = _make_msg(author=[])
    with patch("bibtui.bib.doi.Crossref", return_value=_mock_cr(msg)):
        e = fetch_by_doi("10.1000/test")
    assert e.key.startswith("Unknown")


def test_year_from_published_online() -> None:
    msg = _make_msg()
    del msg["published-print"]
    msg["published-online"] = {"date-parts": [[2022]]}
    with patch("bibtui.bib.doi.Crossref", return_value=_mock_cr(msg)):
        e = fetch_by_doi("10.1000/test")
    assert e.year == "2022"


def test_year_empty_when_no_date() -> None:
    msg = _make_msg()
    del msg["published-print"]
    with patch("bibtui.bib.doi.Crossref", return_value=_mock_cr(msg)):
        e = fetch_by_doi("10.1000/test")
    assert e.year == ""


def test_volume_and_issue_in_raw_fields() -> None:
    msg = _make_msg(volume="12", issue="3")
    with patch("bibtui.bib.doi.Crossref", return_value=_mock_cr(msg)):
        e = fetch_by_doi("10.1000/test")
    assert e.raw_fields.get("volume") == "12"
    assert e.raw_fields.get("number") == "3"


def test_pages_in_raw_fields() -> None:
    msg = _make_msg(page="100-110")
    with patch("bibtui.bib.doi.Crossref", return_value=_mock_cr(msg)):
        e = fetch_by_doi("10.1000/test")
    assert e.raw_fields.get("pages") == "100-110"


def test_publisher_in_raw_fields() -> None:
    msg = _make_msg(publisher="Elsevier")
    with patch("bibtui.bib.doi.Crossref", return_value=_mock_cr(msg)):
        e = fetch_by_doi("10.1000/test")
    assert e.raw_fields.get("publisher") == "Elsevier"
