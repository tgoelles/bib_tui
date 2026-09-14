"""Unit tests for bibtui.pdf.import_scan — all network calls mocked."""

from unittest.mock import patch

import pytest

from bibtui.bib.models import BibEntry
from bibtui.pdf.import_scan import ImportStatus, process_pdf


@pytest.fixture(autouse=True)
def _no_retry_delay(monkeypatch):
    """Don't actually sleep between retry attempts in tests."""
    monkeypatch.setattr("bibtui.pdf.import_scan.time.sleep", lambda _seconds: None)


def _fake_identify(doi=None, arxiv_id=None, ambiguous=False, candidates=None, no_text=False):
    from bibtui.pdf.identify import IdentifyResult

    return IdentifyResult(
        doi=doi,
        arxiv_id=arxiv_id,
        ambiguous=ambiguous,
        candidates=candidates or [],
        no_text=no_text,
    )


def _entry(doi: str) -> BibEntry:
    return BibEntry(key="Smith2023", entry_type="article", title="A Paper", doi=doi)


def test_matched_when_doi_resolves(tmp_path) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"fake")
    with (
        patch(
            "bibtui.pdf.import_scan.extract_identifier",
            return_value=_fake_identify(doi="10.1000/test"),
        ),
        patch(
            "bibtui.pdf.import_scan.fetch_by_doi",
            return_value=_entry("10.1000/test"),
        ),
    ):
        row = process_pdf(str(pdf), seen_dois=set())

    assert row.status == ImportStatus.MATCHED
    assert row.entry is not None
    assert row.entry.doi == "10.1000/test"
    assert row.filename == "paper.pdf"


def test_arxiv_id_is_looked_up_as_a_crossref_doi(tmp_path) -> None:
    pdf = tmp_path / "preprint.pdf"
    pdf.write_bytes(b"fake")
    with (
        patch(
            "bibtui.pdf.import_scan.extract_identifier",
            return_value=_fake_identify(arxiv_id="2301.12345"),
        ),
        patch(
            "bibtui.pdf.import_scan.fetch_by_doi",
            return_value=_entry("10.48550/arXiv.2301.12345"),
        ) as mock_fetch,
    ):
        row = process_pdf(str(pdf), seen_dois=set())

    mock_fetch.assert_called_once_with("10.48550/arXiv.2301.12345")
    assert row.status == ImportStatus.MATCHED


def test_no_identifier_when_extraction_finds_nothing(tmp_path) -> None:
    pdf = tmp_path / "blank.pdf"
    pdf.write_bytes(b"fake")
    with patch(
        "bibtui.pdf.import_scan.extract_identifier",
        return_value=_fake_identify(no_text=True),
    ):
        row = process_pdf(str(pdf), seen_dois=set())

    assert row.status == ImportStatus.NO_IDENTIFIER
    assert "scanned" in row.message.lower()


def test_ambiguous_extraction_is_flagged_not_guessed(tmp_path) -> None:
    pdf = tmp_path / "ambiguous.pdf"
    pdf.write_bytes(b"fake")
    with patch(
        "bibtui.pdf.import_scan.extract_identifier",
        return_value=_fake_identify(
            ambiguous=True, candidates=["10.1/a", "10.2/b"]
        ),
    ) as mock_extract:
        row = process_pdf(str(pdf), seen_dois=set())

    mock_extract.assert_called_once()
    assert row.status == ImportStatus.AMBIGUOUS
    assert row.candidates == ["10.1/a", "10.2/b"]


def test_already_present_when_doi_matches_seen_set(tmp_path) -> None:
    pdf = tmp_path / "dup.pdf"
    pdf.write_bytes(b"fake")
    with (
        patch(
            "bibtui.pdf.import_scan.extract_identifier",
            return_value=_fake_identify(doi="10.1000/TEST"),
        ),
        patch("bibtui.pdf.import_scan.fetch_by_doi") as mock_fetch,
    ):
        row = process_pdf(str(pdf), seen_dois={"10.1000/test"})

    mock_fetch.assert_not_called()
    assert row.status == ImportStatus.ALREADY_PRESENT


def test_lookup_failed_after_one_retry(tmp_path) -> None:
    pdf = tmp_path / "fails.pdf"
    pdf.write_bytes(b"fake")
    with (
        patch(
            "bibtui.pdf.import_scan.extract_identifier",
            return_value=_fake_identify(doi="10.1000/test"),
        ),
        patch(
            "bibtui.pdf.import_scan.fetch_by_doi",
            side_effect=RuntimeError("crossref down"),
        ) as mock_fetch,
    ):
        row = process_pdf(str(pdf), seen_dois=set())

    assert mock_fetch.call_count == 2
    assert row.status == ImportStatus.LOOKUP_FAILED
    assert "crossref down" in row.message


def test_unexpected_exception_never_propagates(tmp_path) -> None:
    pdf = tmp_path / "boom.pdf"
    pdf.write_bytes(b"fake")
    with patch(
        "bibtui.pdf.import_scan.extract_identifier",
        side_effect=RuntimeError("boom"),
    ):
        row = process_pdf(str(pdf), seen_dois=set())

    assert row.status == ImportStatus.LOOKUP_FAILED
    assert "boom" in row.message
