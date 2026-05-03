"""Tests for bibtui.pdf.fetcher.

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
from bibtui.pdf import fetcher as pdf_fetcher
from bibtui.pdf.fetcher import (
    FetchError,
    FetchResult,
    _arxiv_id,
    _copernicus_pdf_url,
    _try_copernicus,
    _try_direct_url,
    _try_openalex,
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


@pytest.fixture(scope="session")
def openalex_api_key() -> str:
    """Load the OpenAlex API key from the real config file."""
    api_key = load_config().openalex_api_key
    if not api_key:
        pytest.skip("No openalex_api_key set in ~/.config/bib_tui/config.toml")
    return api_key


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


def test_fetch_pdf_overwrite_skips_existing_file_check(tmp_path):
    """overwrite=True must not raise 'already exists' — regression for the bug where
    confirming overwrite in the UI still showed the 'file already exists' error because
    FetchPDFModal called fetch_pdf without overwrite=True.
    """
    dest = tmp_path / "x.pdf"
    dest.write_bytes(b"%PDF-1.4 fake")
    e = BibEntry(key="x", entry_type="article")  # no DOI/URL → all strategies fail
    with pytest.raises(FetchError) as exc_info:
        fetch_pdf(e, dest_dir=str(tmp_path), overwrite=True)
    # The error must be about fetch strategies failing, not about file existence
    assert "already exists" not in str(exc_info.value)
    assert "arXiv" in str(exc_info.value) or "Could not fetch" in str(exc_info.value)


def test_fetch_pdf_no_doi_or_url_all_strategies_fail(tmp_path):
    e = BibEntry(key="nodoi", entry_type="article")
    with pytest.raises(FetchError) as exc_info:
        fetch_pdf(e, dest_dir=str(tmp_path), unpaywall_email="x@y.com")
    msg = str(exc_info.value)
    assert "arXiv" in msg
    assert "Copernicus" in msg
    assert "Unpaywall" in msg
    assert "Direct URL" in msg


# ---------------------------------------------------------------------------
# Copernicus URL construction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "doi,expected",
    [
        # Published articles
        (
            "10.5194/tc-17-1585-2023",
            "https://tc.copernicus.org/articles/17/1585/2023/tc-17-1585-2023.pdf",
        ),
        (
            "10.5194/essd-10-2275-2018",
            "https://essd.copernicus.org/articles/10/2275/2018/essd-10-2275-2018.pdf",
        ),
        # Journal-specific preprints
        (
            "10.5194/essd-2025-745",
            "https://essd.copernicus.org/preprints/essd-2025-745/essd-2025-745.pdf",
        ),
        (
            "10.5194/tc-2024-50",
            "https://tc.copernicus.org/preprints/tc-2024-50/tc-2024-50.pdf",
        ),
        # EGUsphere general preprint server (year in path)
        (
            "10.5194/egusphere-2026-485",
            "https://egusphere.copernicus.org/preprints/2026/egusphere-2026-485/egusphere-2026-485.pdf",
        ),
    ],
)
def test_copernicus_pdf_url(doi: str, expected: str) -> None:
    assert _copernicus_pdf_url(doi) == expected


def test_copernicus_pdf_url_non_copernicus_doi() -> None:
    assert _copernicus_pdf_url("10.1038/s41586-020-1") is None


def test_copernicus_pdf_url_no_doi() -> None:
    assert _copernicus_pdf_url("") is None


def test_try_copernicus_no_doi(tmp_path) -> None:
    e = BibEntry(key="x", entry_type="article")
    reason = _try_copernicus(e, str(tmp_path / "x.pdf"))
    assert reason == "no DOI"


def test_try_copernicus_non_copernicus_doi(tmp_path) -> None:
    e = BibEntry(key="x", entry_type="article", doi="10.1038/s41586-020-1")
    reason = _try_copernicus(e, str(tmp_path / "x.pdf"))
    assert reason is not None
    assert "not a recognised Copernicus DOI" in reason


def test_try_direct_url_falls_back_to_get_when_head_fails(monkeypatch, tmp_path):
    entry = BibEntry(key="x", entry_type="article", url="https://example.org/paper.pdf")
    dest = str(tmp_path / "x.pdf")
    called: list[tuple[str, str]] = []

    def fake_urlopen(req, timeout=0):
        if req.get_method() == "HEAD":
            raise OSError("HEAD blocked")
        raise AssertionError("GET should be handled by _download, not urlopen here")

    def fake_download(url: str, dest_path: str, timeout: int = 30) -> None:
        called.append((url, dest_path))

    monkeypatch.setattr(pdf_fetcher.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(pdf_fetcher, "_download", fake_download)

    reason = _try_direct_url(entry, dest)
    assert reason is None
    assert called == [(entry.url, dest)]


def test_try_direct_url_rejects_non_pdf_content_type(monkeypatch, tmp_path):
    entry = BibEntry(key="x", entry_type="article", url="https://example.org/page")
    dest = str(tmp_path / "x.pdf")

    class FakeHeadResponse:
        headers = {"Content-Type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(req, timeout=0):
        assert req.get_method() == "HEAD"
        return FakeHeadResponse()

    monkeypatch.setattr(pdf_fetcher.urllib.request, "urlopen", fake_urlopen)

    reason = _try_direct_url(entry, dest)
    assert reason is not None
    assert "does not serve a PDF" in reason


def test_try_openalex_requires_doi(tmp_path) -> None:
    e = BibEntry(key="x", entry_type="article")
    reason = _try_openalex(e, str(tmp_path / "x.pdf"), api_key="abc")
    assert reason == "entry has no DOI or title"


def test_try_openalex_requires_api_key(tmp_path) -> None:
    e = BibEntry(key="x", entry_type="article", doi="10.5194/tc-18-3807-2024")
    reason = _try_openalex(e, str(tmp_path / "x.pdf"), api_key="")
    assert reason == "no API key configured in Settings"


def test_try_openalex_uses_best_pdf_url(monkeypatch, tmp_path) -> None:
    e = BibEntry(key="x", entry_type="article", doi="10.5194/tc-18-3807-2024")
    dest = str(tmp_path / "x.pdf")
    called: list[tuple[bytes, str]] = []

    class FakePDF:
        def get(self):
            return b"%PDF-1.4 fake"

    class FakeWorks:
        def __init__(self) -> None:
            self.filtered = None

        def filter(self, **kwargs):
            self.filtered = kwargs
            return self

        def get(self, per_page=None):
            return [
                {
                    "id": "https://openalex.org/W123",
                    "best_oa_location": {"pdf_url": "https://example.org/best.pdf"},
                    "open_access": {"oa_url": "https://example.org/oa.pdf"},
                    "locations": [{"pdf_url": "https://example.org/loc.pdf"}],
                }
            ]

        def __getitem__(self, work_id):
            assert work_id == "W123"
            return type("FakeWork", (), {"pdf": FakePDF()})()

    fake_works = FakeWorks()

    def fake_write_pdf_bytes(pdf_bytes: bytes, dest_path: str) -> None:
        called.append((pdf_bytes, dest_path))

    monkeypatch.setattr(pdf_fetcher.pyalex, "Works", lambda: fake_works)
    monkeypatch.setattr(pdf_fetcher, "_write_pdf_bytes", fake_write_pdf_bytes)

    reason = _try_openalex(e, dest, api_key="test-key")
    assert reason is None
    assert fake_works.filtered == {"doi": "https://doi.org/10.5194/tc-18-3807-2024"}
    assert called == [(b"%PDF-1.4 fake", dest)]


def test_try_openalex_uses_title_search_when_no_doi(monkeypatch, tmp_path) -> None:
    e = BibEntry(
        key="Ritz2001",
        entry_type="article",
        title=(
            "Modeling the evolution of Antarctic ice sheet over the last "
            "420,000 years: Implications for altitude changes in the Vostok region"
        ),
    )
    dest = str(tmp_path / "Ritz2001.pdf")
    calls: list[tuple[str, str]] = []

    class FakePDF:
        def get(self):
            return b"%PDF-1.4 title-search"

    class FakeWorks:
        def filter(self, **kwargs):
            calls.append(("filter", str(kwargs)))
            return self

        def search(self, query):
            calls.append(("search", query))
            return self

        def get(self, per_page=None):
            return [{"id": "https://openalex.org/W2046172844"}]

        def __getitem__(self, work_id):
            assert work_id == "W2046172844"
            return type("FakeWork", (), {"pdf": FakePDF()})()

    monkeypatch.setattr(pdf_fetcher.pyalex, "Works", lambda: FakeWorks())

    reason = _try_openalex(e, dest, api_key="test-key")
    assert reason is None
    # No DOI present, so it should use title fallback query.
    assert any(c[0] == "search" for c in calls)


def test_try_openalex_prefers_doi_before_title(monkeypatch, tmp_path) -> None:
    e = BibEntry(
        key="x",
        entry_type="article",
        doi="10.5194/tc-18-3807-2024",
        title="Some title",
    )
    dest = str(tmp_path / "x.pdf")
    calls: list[tuple[str, str]] = []

    class FakePDF:
        def get(self):
            return b"%PDF-1.4 doi-first"

    class FakeWorks:
        def filter(self, **kwargs):
            calls.append(("filter", str(kwargs)))
            return self

        def search(self, query):
            calls.append(("search", query))
            return self

        def get(self, per_page=None):
            return [{"id": "https://openalex.org/W123"}]

        def __getitem__(self, work_id):
            assert work_id == "W123"
            return type("FakeWork", (), {"pdf": FakePDF()})()

    monkeypatch.setattr(pdf_fetcher.pyalex, "Works", lambda: FakeWorks())

    reason = _try_openalex(e, dest, api_key="test-key")
    assert reason is None
    assert calls[0][0] == "filter"
    assert all(c[0] != "search" for c in calls)


def test_try_openalex_uses_content_pdf_for_joughin2008(monkeypatch, tmp_path) -> None:
    e = BibEntry(
        key="Joughin2008",
        entry_type="article",
        title=(
            "Ice-front variation and tidewater behavior on Helheim and "
            "Kangerdlugssuaq Glaciers, Greenland"
        ),
        doi="10.1029/2007JF000837",
    )
    dest = str(tmp_path / "Joughin2008.pdf")
    called: list[tuple[bytes, str]] = []

    class FakePDF:
        def get(self):
            return b"%PDF-1.7 openalex"

    class FakeWorks:
        def filter(self, **_kwargs):
            return self

        def get(self, per_page=None):
            return [
                {
                    "id": "https://openalex.org/W2012092742",
                    "content_urls": {
                        "pdf": "https://content.openalex.org/works/W2012092742.pdf"
                    },
                    "best_oa_location": {
                        "pdf_url": "https://onlinelibrary.wiley.com/doi/pdfdirect/10.1029/2007JF000837"
                    },
                    "open_access": {
                        "oa_url": "https://onlinelibrary.wiley.com/doi/pdfdirect/10.1029/2007JF000837"
                    },
                    "locations": [
                        {
                            "pdf_url": "https://onlinelibrary.wiley.com/doi/pdfdirect/10.1029/2007JF000837"
                        }
                    ],
                }
            ]

        def __getitem__(self, work_id):
            assert work_id == "W2012092742"
            return type("FakeWork", (), {"pdf": FakePDF()})()

    def fake_write_pdf_bytes(pdf_bytes: bytes, dest_path: str) -> None:
        called.append((pdf_bytes, dest_path))

    monkeypatch.setattr(pdf_fetcher.pyalex, "Works", lambda: FakeWorks())
    monkeypatch.setattr(pdf_fetcher, "_write_pdf_bytes", fake_write_pdf_bytes)

    reason = _try_openalex(e, dest, api_key="test-key")
    assert reason is None
    assert called == [(b"%PDF-1.7 openalex", dest)]


def test_try_openalex_falls_back_from_blocked_publisher_pdf_to_content_pdf(
    monkeypatch, tmp_path
) -> None:
    e = BibEntry(key="Joughin2008", entry_type="article", doi="10.1029/2007JF000837")
    dest = str(tmp_path / "Joughin2008.pdf")
    called: list[str] = []

    class FakeWorks:
        def filter(self, **_kwargs):
            return self

        def get(self, per_page=None):
            return [
                {
                    "id": "https://openalex.org/W2012092742",
                    "best_oa_location": {
                        "pdf_url": "https://onlinelibrary.wiley.com/doi/pdfdirect/10.1029/2007JF000837"
                    },
                    "content_urls": {
                        "pdf": "https://content.openalex.org/works/W2012092742.pdf"
                    },
                }
            ]

        def __getitem__(self, work_id):
            assert work_id == "W2012092742"
            raise RuntimeError("pdf api unavailable")

    def fake_download(url: str, dest_path: str, timeout: int = 30) -> None:
        called.append(url)
        if "wiley.com" in url:
            raise FetchError("URL did not return a PDF")

    monkeypatch.setattr(pdf_fetcher.pyalex, "Works", lambda: FakeWorks())
    monkeypatch.setattr(pdf_fetcher, "_download", fake_download)

    reason = _try_openalex(e, dest, api_key="test-key")
    assert reason is None
    assert called == ["https://content.openalex.org/works/W2012092742.pdf"]


def test_fetch_pdf_uses_openalex_before_unpaywall(monkeypatch, tmp_path) -> None:
    e = BibEntry(key="x", entry_type="article", doi="10.5194/tc-18-3807-2024")
    order: list[str] = []

    monkeypatch.setattr(pdf_fetcher, "_try_arxiv", lambda *_args, **_kwargs: "miss")
    monkeypatch.setattr(
        pdf_fetcher, "_try_copernicus", lambda *_args, **_kwargs: "miss"
    )

    def fake_openalex(*_args, **_kwargs):
        order.append("openalex")
        return None

    def fake_unpaywall(*_args, **_kwargs):
        order.append("unpaywall")
        return "miss"

    monkeypatch.setattr(pdf_fetcher, "_try_openalex", fake_openalex)
    monkeypatch.setattr(pdf_fetcher, "_try_unpaywall", fake_unpaywall)

    result = fetch_pdf(
        e,
        dest_dir=str(tmp_path),
        unpaywall_email="me@example.com",
        openalex_api_key="openalex-key",
        overwrite=True,
    )
    assert isinstance(result, FetchResult)
    assert result.path.endswith("x.pdf")
    assert result.provider == "OpenAlex"
    assert order == ["openalex"]


def test_fetch_pdf_skips_openalex_without_api_key(monkeypatch, tmp_path) -> None:
    e = BibEntry(key="x", entry_type="article")
    monkeypatch.setattr(pdf_fetcher, "_try_arxiv", lambda *_args, **_kwargs: "miss")
    monkeypatch.setattr(
        pdf_fetcher, "_try_copernicus", lambda *_args, **_kwargs: "miss"
    )
    monkeypatch.setattr(
        pdf_fetcher,
        "_try_openalex",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("OpenAlex should be skipped when key is empty")
        ),
    )
    monkeypatch.setattr(pdf_fetcher, "_try_unpaywall", lambda *_args, **_kwargs: "miss")
    monkeypatch.setattr(
        pdf_fetcher, "_try_direct_url", lambda *_args, **_kwargs: "miss"
    )

    with pytest.raises(FetchError) as exc_info:
        fetch_pdf(
            e,
            dest_dir=str(tmp_path),
            unpaywall_email="me@example.com",
            openalex_api_key="",
            overwrite=True,
        )

    assert "OpenAlex" not in str(exc_info.value)


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
def test_try_openalex_downloads_pdf_for_joughin2008(openalex_api_key, tmp_path):
    entry = BibEntry(
        key="Joughin2008",
        entry_type="article",
        title=(
            "Ice-front variation and tidewater behavior on Helheim and "
            "Kangerdlugssuaq Glaciers, Greenland"
        ),
        doi="10.1029/2007JF000837",
    )
    dest = str(tmp_path / "Joughin2008.pdf")
    reason = _try_openalex(entry, dest, openalex_api_key)
    assert reason is None, f"Expected OpenAlex PDF success but got: {reason}"

    import os

    assert os.path.exists(dest)
    assert os.path.getsize(dest) > 10_000
    with open(dest, "rb") as f:
        assert f.read(4) == b"%PDF"


@pytest.mark.network
def test_try_openalex_downloads_pdf_by_title_without_doi(openalex_api_key, tmp_path):
    entry = BibEntry(
        key="Ritz2001",
        entry_type="article",
        title=(
            "Modeling the evolution of Antarctic ice sheet over the last "
            "420,000 years: Implications for altitude changes in the Vostok region"
        ),
    )
    dest = str(tmp_path / "Ritz2001.pdf")
    reason = _try_openalex(entry, dest, openalex_api_key)
    assert reason is None, f"Expected OpenAlex title PDF success but got: {reason}"

    import os

    assert os.path.exists(dest)
    assert os.path.getsize(dest) > 10_000
    with open(dest, "rb") as f:
        assert f.read(4) == b"%PDF"


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
    assert "no direct PDF" in reason


@pytest.mark.network
def test_try_copernicus_downloads_preprint(tmp_path) -> None:
    """ESSD preprint — PDF must be fetched directly from copernicus.org."""
    e = BibEntry(key="Wang2026", entry_type="misc", doi="10.5194/essd-2025-745")
    dest = str(tmp_path / "Wang2026.pdf")
    reason = _try_copernicus(e, dest)
    assert reason is None, f"Expected success but got: {reason}"
    import os

    assert os.path.getsize(dest) > 10_000
    with open(dest, "rb") as f:
        assert f.read(4) == b"%PDF"


@pytest.mark.network
def test_try_copernicus_downloads_egusphere(tmp_path) -> None:
    """EGUsphere preprint — PDF URL contains year subdirectory."""
    e = BibEntry(key="Ruttner2026", entry_type="misc", doi="10.5194/egusphere-2026-485")
    dest = str(tmp_path / "Ruttner2026.pdf")
    reason = _try_copernicus(e, dest)
    assert reason is None, f"Expected success but got: {reason}"
    import os

    assert os.path.getsize(dest) > 10_000
    with open(dest, "rb") as f:
        assert f.read(4) == b"%PDF"


@pytest.mark.network
def test_fetch_pdf_full_pipeline(tc_entry, unpaywall_email, tmp_path):
    result = fetch_pdf(tc_entry, str(tmp_path), unpaywall_email=unpaywall_email)
    import os

    assert os.path.exists(result.path)
    expected_name = pdf_filename(tc_entry)
    assert os.path.basename(result.path) == expected_name
    assert result.provider in {
        "arXiv",
        "Copernicus",
        "OpenAlex",
        "Unpaywall",
        "Direct URL",
    }
    assert os.path.getsize(result.path) > 10_000
    with open(result.path, "rb") as f:
        assert f.read(4) == b"%PDF"
