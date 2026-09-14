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


def _process(path, existing_by_doi=None, seen_in_batch=None):
    return process_pdf(str(path), existing_by_doi or {}, seen_in_batch or set())


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
        row = _process(pdf)

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
        row = _process(pdf)

    mock_fetch.assert_called_once_with("10.48550/arXiv.2301.12345")
    assert row.status == ImportStatus.MATCHED


def test_no_identifier_when_extraction_finds_nothing(tmp_path) -> None:
    pdf = tmp_path / "blank.pdf"
    pdf.write_bytes(b"fake")
    with patch(
        "bibtui.pdf.import_scan.extract_identifier",
        return_value=_fake_identify(no_text=True),
    ):
        row = _process(pdf)

    assert row.status == ImportStatus.NO_IDENTIFIER
    assert "scanned" in row.message.lower()


def test_ambiguous_extraction_is_flagged_not_guessed(tmp_path) -> None:
    pdf = tmp_path / "ambiguous.pdf"
    pdf.write_bytes(b"fake")
    with patch(
        "bibtui.pdf.import_scan.extract_identifier",
        return_value=_fake_identify(ambiguous=True, candidates=["10.1/a", "10.2/b"]),
    ) as mock_extract:
        row = _process(pdf)

    mock_extract.assert_called_once()
    assert row.status == ImportStatus.AMBIGUOUS
    assert row.candidates == ["10.1/a", "10.2/b"]


def test_already_present_when_doi_seen_earlier_in_batch(tmp_path) -> None:
    pdf = tmp_path / "dup.pdf"
    pdf.write_bytes(b"fake")
    with (
        patch(
            "bibtui.pdf.import_scan.extract_identifier",
            return_value=_fake_identify(doi="10.1000/TEST"),
        ),
        patch("bibtui.pdf.import_scan.fetch_by_doi") as mock_fetch,
    ):
        row = _process(pdf, seen_in_batch={"10.1000/test"})

    mock_fetch.assert_not_called()
    assert row.status == ImportStatus.ALREADY_PRESENT
    assert "this import" in row.message.lower()


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
        row = _process(pdf)

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
        row = _process(pdf)

    assert row.status == ImportStatus.LOOKUP_FAILED
    assert "boom" in row.message


# ---------------------------------------------------------------------------
# Matching an entry already in the library
# ---------------------------------------------------------------------------


def test_link_existing_when_matched_entry_has_no_pdf(tmp_path) -> None:
    pdf = tmp_path / "backfill.pdf"
    pdf.write_bytes(b"fake")
    existing = BibEntry(
        key="Backfill2020", entry_type="article", doi="10.5000/test", file=""
    )
    with (
        patch(
            "bibtui.pdf.import_scan.extract_identifier",
            return_value=_fake_identify(doi="10.5000/TEST"),
        ),
        patch("bibtui.pdf.import_scan.fetch_by_doi") as mock_fetch,
    ):
        row = _process(pdf, existing_by_doi={"10.5000/test": existing})

    mock_fetch.assert_not_called()  # already have the metadata — no need to re-fetch
    assert row.status == ImportStatus.LINK_EXISTING
    assert row.entry is existing  # same object, so linking it mutates the library


def test_already_present_when_matched_entry_already_has_a_pdf(tmp_path) -> None:
    pdf = tmp_path / "dup.pdf"
    pdf.write_bytes(b"fake")
    existing = BibEntry(
        key="Has2020",
        entry_type="article",
        doi="10.5000/test",
        file=":Has2020.pdf:PDF",
    )
    with (
        patch(
            "bibtui.pdf.import_scan.extract_identifier",
            return_value=_fake_identify(doi="10.5000/test"),
        ),
        patch("bibtui.pdf.import_scan.fetch_by_doi") as mock_fetch,
    ):
        row = _process(pdf, existing_by_doi={"10.5000/test": existing})

    mock_fetch.assert_not_called()
    assert row.status == ImportStatus.ALREADY_PRESENT
    assert row.entry is None
