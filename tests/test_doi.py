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


def test_citation_key_normalizes_accents_and_braces() -> None:
    msg = _make_msg(author=[{"family": r"G{\"o}lles", "given": "Thomas"}])
    with patch("bibtui.bib.doi.Crossref", return_value=_mock_cr(msg)):
        e = fetch_by_doi("10.1000/test")
    assert e.key == "Goelles2023"


def test_citation_key_normalizes_punctuation() -> None:
    msg = _make_msg(author=[{"family": "O'Neil-Smith", "given": "Jane"}])
    with patch("bibtui.bib.doi.Crossref", return_value=_mock_cr(msg)):
        e = fetch_by_doi("10.1000/test")
    assert e.key == "ONeilSmith2023"


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


# ---------------------------------------------------------------------------
# Preprint / posted-content (e.g. 10.5194/essd-2025-745)
# ---------------------------------------------------------------------------


def _make_preprint_msg(**overrides) -> dict:
    """Minimal Crossref message dict mimicking a posted-content preprint.

    Matches the real structure of 10.5194/essd-2025-745: no published-print,
    no published-online; year comes from 'issued' (and also 'posted').
    """
    base = {
        "type": "posted-content",
        "subtype": "preprint",
        "title": ["Ice thickness and subglacial topography of Swedish reference glaciers"],
        "author": [
            {"family": "Wang", "given": "Zhuo"},
            {"family": "Ross", "given": "Neil"},
        ],
        "issued": {"date-parts": [[2026, 1, 21]]},
        "posted": {"date-parts": [[2026, 1, 21]]},
        "container-title": [],
        "publisher": "Copernicus GmbH",
        "DOI": "10.5194/essd-2025-745",
    }
    base.update(overrides)
    return base


def _mock_cr_copernicus(preprint_msg: dict):
    """Mock that supports the journal-lookup extra calls for Copernicus preprints."""
    cr = MagicMock()

    def works_side_effect(*args, **kwargs):
        if kwargs.get("ids"):
            # Main DOI fetch
            return {"message": preprint_msg}
        # Secondary call: find published journal articles for journal name lookup
        return {
            "message": {
                "items": [
                    {
                        "DOI": "10.5194/essd-10-2275-2018",
                        "container-title": ["Earth System Science Data"],
                    }
                ],
                "total-results": 1,
            }
        }

    cr.works.side_effect = works_side_effect
    cr.journals.return_value = {
        "message": {
            "items": [{"title": "Earth System Science Data Discussions"}],
            "total-results": 1,
        }
    }
    return cr


def test_preprint_entry_type() -> None:
    """posted-content preprints should map to misc."""
    with patch("bibtui.bib.doi.Crossref", return_value=_mock_cr(_make_preprint_msg())):
        e = fetch_by_doi("10.5194/essd-2025-745")
    assert e.entry_type == "misc"


def test_preprint_year_from_issued() -> None:
    """Year should be extracted from 'issued' when published-print/online are absent."""
    with patch("bibtui.bib.doi.Crossref", return_value=_mock_cr(_make_preprint_msg())):
        e = fetch_by_doi("10.5194/essd-2025-745")
    assert e.year == "2026"


def test_preprint_year_from_posted_when_issued_absent() -> None:
    """Year should fall back to 'posted' when issued is also absent."""
    msg = _make_preprint_msg()
    del msg["issued"]
    with patch("bibtui.bib.doi.Crossref", return_value=_mock_cr(msg)):
        e = fetch_by_doi("10.5194/essd-2025-745")
    assert e.year == "2026"


def test_preprint_journal_copernicus() -> None:
    """Journal should be resolved to the Discussions journal for Copernicus preprints."""
    cr_mock = _mock_cr_copernicus(_make_preprint_msg())
    with patch("bibtui.bib.doi.Crossref", return_value=cr_mock):
        e = fetch_by_doi("10.5194/essd-2025-745")
    assert e.journal == "Earth System Science Data Discussions"


def test_preprint_journal_biorxiv() -> None:
    """Journal should come from the institution field for bioRxiv-style preprints."""
    msg = _make_preprint_msg(institution=[{"name": "bioRxiv"}], **{"container-title": []})
    with patch("bibtui.bib.doi.Crossref", return_value=_mock_cr(msg)):
        e = fetch_by_doi("10.1101/2021.09.01.458592")
    assert e.journal == "bioRxiv"


def test_preprint_journal_egusphere() -> None:
    """EGUsphere general preprint server should resolve to 'EGUsphere'."""
    msg = _make_preprint_msg(
        **{"DOI": "10.5194/egusphere-2026-485", "container-title": []}
    )
    with patch("bibtui.bib.doi.Crossref", return_value=_mock_cr(msg)):
        e = fetch_by_doi("10.5194/egusphere-2026-485")
    assert e.journal == "EGUsphere"


def test_preprint_journal_empty_when_lookup_fails() -> None:
    """Journal stays empty when the lookup API calls return no usable data."""
    with patch("bibtui.bib.doi.Crossref", return_value=_mock_cr(_make_preprint_msg())):
        e = fetch_by_doi("10.5194/essd-2025-745")
    assert e.journal == ""


def test_preprint_citation_key() -> None:
    with patch("bibtui.bib.doi.Crossref", return_value=_mock_cr(_make_preprint_msg())):
        e = fetch_by_doi("10.5194/essd-2025-745")
    assert e.key == "Wang2026"


def test_preprint_publisher_stored() -> None:
    with patch("bibtui.bib.doi.Crossref", return_value=_mock_cr(_make_preprint_msg())):
        e = fetch_by_doi("10.5194/essd-2025-745")
    assert e.raw_fields.get("publisher") == "Copernicus GmbH"
