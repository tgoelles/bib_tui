"""Tests for bibtui.pdf.import_scan.process_pdf against real PDFs.

Complements test_pdf_identify_real.py: those check extraction alone, these
run the real extraction cascade through process_pdf's full decision logic
(new/link-existing/already-present/etc) too — only fetch_by_doi (the actual
network call) is mocked, so there's no network access here either. See
tests/pdfs/README.md for what each fixture is and why it's here.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from bibtui.bib.models import BibEntry
from bibtui.pdf.import_scan import ImportStatus, process_pdf

_PDF_DIR = Path(__file__).parent / "pdfs"


def _real_pdf(name: str) -> str:
    path = _PDF_DIR / name
    if not path.is_file():
        pytest.skip(f"real-PDF fixture missing: {path}")
    return str(path)


def _entry(doi: str) -> BibEntry:
    return BibEntry(key="Fetched2026", entry_type="article", title="A Paper", doi=doi)


def test_real_pdf_matches_when_doi_resolves() -> None:
    path = _real_pdf("sensors-26-05829.pdf")
    with patch(
        "bibtui.pdf.import_scan.fetch_by_doi",
        return_value=_entry("10.3390/s26185829"),
    ) as mock_fetch:
        row = process_pdf(path, {}, set())

    mock_fetch.assert_called_once_with("10.3390/s26185829")
    assert row.status == ImportStatus.MATCHED
    assert row.entry is not None
    assert row.entry.doi == "10.3390/s26185829"


def test_real_pdf_links_existing_entry_by_doi_without_fetching() -> None:
    path = _real_pdf("tc-20-5061-2026.pdf")
    existing = BibEntry(
        key="Gallarate2026", entry_type="article", doi="10.5194/tc-20-5061-2026", file=""
    )
    with patch("bibtui.pdf.import_scan.fetch_by_doi") as mock_fetch:
        row = process_pdf(path, {"10.5194/tc-20-5061-2026": existing}, set())

    mock_fetch.assert_not_called()
    assert row.status == ImportStatus.LINK_EXISTING
    assert row.entry is existing


def test_real_arxiv_pdf_doi_is_resolved_through_the_regular_doi_path() -> None:
    """arXiv now stamps a resolvable 10.48550/arXiv.<id> DOI directly into
    the PDF, so this goes through process_pdf like any other DOI — no
    arxiv-id-specific branch involved."""
    path = _real_pdf("2609.13974v1.pdf")
    with patch(
        "bibtui.pdf.import_scan.fetch_by_doi",
        return_value=_entry("10.48550/arXiv.2609.13974"),
    ) as mock_fetch:
        row = process_pdf(path, {}, set())

    mock_fetch.assert_called_once_with("10.48550/arXiv.2609.13974")
    assert row.status == ImportStatus.MATCHED
