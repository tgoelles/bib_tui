"""Tests for bib_tui.bib.pdf_fetcher.

Unit tests run without network access.
Integration tests (marked `network`) make real HTTP calls and require a
valid Unpaywall email in ~/.config/bib_tui/config.toml.

Run only unit tests:
    uv run pytest tests/test_pdf_fetcher.py -m "not network"

Run all including network tests:
    uv run pytest tests/test_pdf_fetcher.py
"""

import pytest

from bibtui.bib.models import BibEntry
from bibtui.bib.pdf_fetcher import (
    FetchError,
    _arxiv_id,
    _try_unpaywall,
    fetch_pdf,
    pdf_filename,
)
from bibtui.utils.config import load_config

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def unpaywall_email() -> str:
    """Load the Unpaywall email from the real config file."""
    email = load_config().unpaywall_email
    if not email:
        pytest.skip("No unpaywall_email set in ~/.config/bib_tui/config.toml")
    return email


@pytest.fixture()
def tc_entry() -> BibEntry:
    """A real open-access paper from The Cryosphere (Copernicus)."""
    return BibEntry(
        key="tc-18-3807-2024",
        entry_type="article",
        title="Test paper from The Cryosphere",
        doi="10.5194/tc-18-3807-2024",
    )


@pytest.fixture()
def zeitz2021_entry() -> BibEntry:
    """Zeitz2021 — Copernicus paper where Unpaywall has no url_for_pdf,
    only a landing page URL.  PDF must be derived from the landing page.
    """
    return BibEntry(
        key="Zeitz2021",
        entry_type="article",
        title="Impact of the melt-albedo feedback on the future evolution of the Greenland Ice Sheet with PISM-dEBM-simple",
        doi="10.5194/tc-15-5739-2021",
        url="https://tc.copernicus.org/articles/15/5739/2021/",
    )


# ---------------------------------------------------------------------------
# Unit tests — no network
# ---------------------------------------------------------------------------


def test_arxiv_id_from_doi_new_format():
    e = BibEntry(key="x", entry_type="article", doi="10.48550/arXiv.2301.12345")
    assert _arxiv_id(e) == "2301.12345"


def test_arxiv_id_from_doi_legacy_format():
    e = BibEntry(key="x", entry_type="article", doi="10.48550/arXiv.hep-th/9711200")
    assert _arxiv_id(e) == "hep-th/9711200"


def test_arxiv_id_from_url_abs():
    e = BibEntry(key="x", entry_type="article", url="https://arxiv.org/abs/2301.12345")
    assert _arxiv_id(e) == "2301.12345"


def test_arxiv_id_from_url_pdf():
    e = BibEntry(
        key="x", entry_type="article", url="https://arxiv.org/pdf/2301.12345v2"
    )
    assert _arxiv_id(e) == "2301.12345"


def test_arxiv_id_none_for_regular_doi():
    e = BibEntry(key="x", entry_type="article", doi="10.1007/s10584-020-02936-7")
    assert _arxiv_id(e) is None


def test_arxiv_id_none_when_no_doi_or_url():
    e = BibEntry(key="x", entry_type="article")
    assert _arxiv_id(e) is None


def test_fetch_pdf_raises_when_no_dest_dir():
    e = BibEntry(key="x", entry_type="article", doi="10.5194/tc-18-3807-2024")
    with pytest.raises(FetchError, match="PDF base directory is not set"):
        fetch_pdf(e, dest_dir="")


def test_fetch_pdf_raises_when_file_exists(tmp_path):
    dest = tmp_path / "x.pdf"
    dest.write_bytes(b"%PDF-1.4 fake")
    e = BibEntry(key="x", entry_type="article", doi="10.5194/tc-18-3807-2024")
    with pytest.raises(FetchError, match="already exists"):
        fetch_pdf(e, dest_dir=str(tmp_path), overwrite=False)


def test_fetch_pdf_no_doi_or_url_all_strategies_fail(tmp_path):
    e = BibEntry(key="nodoi", entry_type="article")
    with pytest.raises(FetchError) as exc_info:
        fetch_pdf(e, dest_dir=str(tmp_path), unpaywall_email="x@y.com")
    msg = str(exc_info.value)
    assert "arXiv" in msg
    assert "Unpaywall" in msg
    assert "Direct URL" in msg


# ---------------------------------------------------------------------------
# pdf_filename unit tests
# ---------------------------------------------------------------------------


def test_pdf_filename_key_and_title():
    e = BibEntry(key="Smith2020", entry_type="article", title="Ice Sheet Dynamics")
    assert pdf_filename(e) == "Smith2020 - Ice Sheet Dynamics.pdf"


def test_pdf_filename_no_title_falls_back_to_key():
    e = BibEntry(key="Jones2021", entry_type="article")
    assert pdf_filename(e) == "Jones2021.pdf"


def test_pdf_filename_strips_unsafe_chars():
    e = BibEntry(key="A", entry_type="article", title='Carbon: A {Study} of "Heat"?')
    name = pdf_filename(e)
    for ch in r'\/:*?"<>|{}':
        assert ch not in name


def test_pdf_filename_truncates_long_title():
    e = BibEntry(key="K", entry_type="article", title="W" * 200)
    assert len(pdf_filename(e)) <= len("K - ") + 80 + len(".pdf")


def test_pdf_filename_normalises_whitespace():
    e = BibEntry(key="X", entry_type="article", title="  Lots   of   Spaces  ")
    assert pdf_filename(e) == "X - Lots of Spaces.pdf"


# ---------------------------------------------------------------------------
# Integration tests — require network + valid email
# ---------------------------------------------------------------------------


@pytest.mark.network
def test_try_unpaywall_downloads_pdf(tc_entry, unpaywall_email, tmp_path):
    """tc-18-3807-2024 has url_for_pdf directly from Unpaywall."""
    dest = str(tmp_path / f"{tc_entry.key}.pdf")
    reason = _try_unpaywall(tc_entry, dest, unpaywall_email)
    assert reason is None, f"Expected success but got: {reason}"
    import os

    assert os.path.exists(dest)
    assert os.path.getsize(dest) > 10_000  # real PDF should be > 10 KB
    with open(dest, "rb") as f:
        assert f.read(4) == b"%PDF", "Downloaded file is not a valid PDF"


@pytest.mark.network
def test_try_unpaywall_reports_landing_page_only(
    zeitz2021_entry, unpaywall_email, tmp_path
):
    """Zeitz2021: Unpaywall has url_for_pdf=None — only a landing page.
    The strategy should report this clearly rather than trying to download HTML.
    """
    dest = str(tmp_path / f"{zeitz2021_entry.key}.pdf")
    reason = _try_unpaywall(zeitz2021_entry, dest, unpaywall_email)
    assert reason is not None, "Expected failure but got success"
    assert "landing page" in reason


@pytest.mark.network
def test_fetch_pdf_full_pipeline(tc_entry, unpaywall_email, tmp_path):
    saved = fetch_pdf(tc_entry, str(tmp_path), unpaywall_email=unpaywall_email)
    import os

    assert os.path.exists(saved)
    expected_name = pdf_filename(tc_entry)
    assert os.path.basename(saved) == expected_name
    assert os.path.getsize(saved) > 10_000
    with open(saved, "rb") as f:
        assert f.read(4) == b"%PDF"
