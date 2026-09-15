"""Tests for bibtui.pdf.identify against real journal/arXiv PDFs.

Unlike test_pdf_identify.py's hand-built single-page synthetic PDFs (which
exercise the extraction logic in isolation), these fixtures are actual
published papers — multi-column layouts, embedded fonts, reference lists,
publisher boilerplate, and all — the kind of PDF an offline extraction
cascade could plausibly trip up on in ways a minimal fixture can't surface.
No network access here: extract_identifier() only reads the file itself.
See tests/pdfs/README.md for what each fixture is and why it's here
(license permits redistribution).
"""

from pathlib import Path

import pytest

from bibtui.pdf.identify import extract_identifier

_PDF_DIR = Path(__file__).parent / "pdfs"


def _real_pdf(name: str) -> str:
    path = _PDF_DIR / name
    if not path.is_file():
        pytest.skip(f"real-PDF fixture missing: {path}")
    return str(path)


def test_mdpi_sensors_article_doi_is_found() -> None:
    result = extract_identifier(_real_pdf("sensors-26-05829.pdf"))
    assert result.doi == "10.3390/s26185829"
    assert result.arxiv_id is None
    assert not result.ambiguous
    assert not result.no_text
    assert not result.unreadable


def test_copernicus_the_cryosphere_article_doi_is_found() -> None:
    result = extract_identifier(_real_pdf("tc-20-5061-2026.pdf"))
    assert result.doi == "10.5194/tc-20-5061-2026"
    assert result.arxiv_id is None
    assert not result.ambiguous


def test_arxiv_preprint_doi_is_found() -> None:
    """A recent arXiv submission with an already-registered DOI stamped
    directly into the PDF (arXiv now embeds 10.48550/arXiv.<id> itself), so
    this is found by the regular DOI regex — the arxiv_id fallback is for
    papers that only mention "arXiv:<id>" without a resolvable DOI."""
    result = extract_identifier(_real_pdf("2609.13974v1.pdf"))
    assert result.doi == "10.48550/arXiv.2609.13974"
    assert result.arxiv_id is None
    assert not result.ambiguous
