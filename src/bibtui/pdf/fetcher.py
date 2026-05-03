"""PDF fetching utilities.

Tries strategies in order:
1. arXiv — free PDF via the arXiv API (DOI 10.48550/arXiv.* or arxiv.org URL)
2. Copernicus — direct PDF URL constructed from DOI (prefix 10.5194)
3. OpenAlex — open-access PDF lookup by DOI (optional, requires API key)
4. Unpaywall — open-access PDF lookup by DOI (requires email)
5. Direct URL — download if the entry's URL points directly to a PDF

Raises FetchError if none of the strategies succeed.
"""

import json
import os
import re
import shutil
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import pyalex  # type: ignore[import-untyped]

from bibtui.bib.models import BibEntry


class FetchError(Exception):
    """Raised when all PDF fetch strategies fail."""


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------

_UNSAFE_RE = re.compile(r'[\\/:*?"<>|{}]')
_WHITESPACE_RE = re.compile(r"\s+")
_MAX_TITLE_LEN = 80


def pdf_filename(entry: BibEntry) -> str:
    """Return a sanitized filename: ``{key} - {title}.pdf``.

    Characters that are unsafe in filenames are stripped.  The title portion
    is truncated to keep paths reasonable.  Falls back to ``{key}.pdf`` when
    the entry has no title.
    """
    key = entry.key or "unknown"
    title = entry.title.strip() if entry.title else ""
    # Remove LaTeX commands and unsafe chars, then normalise whitespace
    title = _UNSAFE_RE.sub("", title)
    title = _WHITESPACE_RE.sub(" ", title).strip()
    if title:
        if len(title) > _MAX_TITLE_LEN:
            title = title[:_MAX_TITLE_LEN].rstrip()
        return f"{key} - {title}.pdf"
    return f"{key}.pdf"


def add_pdf(src: Path, entry: BibEntry, base_dir: str) -> Path:
    """Move an existing PDF to the canonical location for *entry*.

    Parameters
    ----------
    src:
        Path to the existing PDF file.  ``~`` is expanded and the path is
        resolved to an absolute location.
    entry:
        The BibTeX entry to associate the file with.
    base_dir:
        Destination directory (from ``Config.pdf_base_dir``).  Must not be empty.

    Returns
    -------
    Path
        The destination path the file was moved to.

    Raises
    ------
    FetchError
        If ``base_dir`` is empty, the source file does not exist, the source
        is not a ``.pdf``, or the destination already exists.
    """
    if not base_dir:
        raise FetchError(
            "PDF base directory is not set. "
            "Open Settings (Ctrl+P → Settings) and set a base directory first."
        )
    src = Path(src).expanduser().resolve()
    if not src.exists():
        raise FetchError(f"File not found: {src}")
    if src.suffix.lower() != ".pdf":
        raise FetchError(f"Not a PDF file: {src.name}")
    dest = Path(base_dir) / pdf_filename(entry)
    if dest.exists() and dest.resolve() != src:
        raise FetchError(f"Destination already exists: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), dest)
    return dest


# ---------------------------------------------------------------------------
# arXiv helpers
# ---------------------------------------------------------------------------


def _arxiv_id(entry: BibEntry) -> str | None:
    """Extract an arXiv ID from the entry's DOI or URL, or None."""
    # DOI: 10.48550/arXiv.2301.12345  or  10.48550/arxiv.hep-th/9711200
    if entry.doi:
        m = re.search(r"10\.48550/[aA]r[xX]iv\.(.+)$", entry.doi)
        if m:
            return m.group(1)

    # URL: https://arxiv.org/abs/2301.12345  or  /pdf/2301.12345
    if entry.url:
        m = re.search(
            r"arxiv\.org/(?:abs|pdf)/(.+?)(?:v\d+)?(?:\.pdf)?$",
            entry.url,
            re.IGNORECASE,
        )
        if m:
            return m.group(1)

    return None


# ---------------------------------------------------------------------------
# Download helper
# ---------------------------------------------------------------------------


def _download(url: str, dest_path: str, timeout: int = 30) -> None:
    """Stream *url* to *dest_path*.

    Raises FetchError if the response Content-Type is not PDF or the request
    fails.
    """
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0"
            ),
            "Accept": "application/pdf,*/*",
        },
    )
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: str | None = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            first_chunk = resp.read(65536)
            if not first_chunk:
                raise FetchError(f"URL returned empty response: {url}")

            is_pdf_type = "pdf" in content_type.lower()
            is_pdf_magic = first_chunk.startswith(b"%PDF")
            if not is_pdf_type and not is_pdf_magic:
                raise FetchError(
                    f"URL did not return a PDF (Content-Type: {content_type}): {url}"
                )

            fd, tmp_path = tempfile.mkstemp(
                prefix=f".{dest.name}.", suffix=".tmp", dir=str(dest.parent)
            )
            with os.fdopen(fd, "wb") as f:
                f.write(first_chunk)
                while chunk := resp.read(65536):
                    f.write(chunk)
                f.flush()
                os.fsync(f.fileno())

            os.replace(tmp_path, dest_path)
            tmp_path = None
    except FetchError:
        raise
    except Exception as exc:
        raise FetchError(f"Download failed from {url}: {exc}") from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _write_pdf_bytes(pdf_bytes: bytes, dest_path: str) -> None:
    """Write raw PDF bytes to *dest_path* atomically after basic validation."""
    if not pdf_bytes:
        raise FetchError("OpenAlex returned empty PDF content")
    if not pdf_bytes.startswith(b"%PDF"):
        raise FetchError("OpenAlex did not return PDF content")

    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: str | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            prefix=f".{dest.name}.", suffix=".tmp", dir=str(dest.parent)
        )
        with os.fdopen(fd, "wb") as f:
            f.write(pdf_bytes)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, dest_path)
        tmp_path = None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Strategy 1 — arXiv
# ---------------------------------------------------------------------------


def _try_arxiv(entry: BibEntry, dest_path: str) -> str | None:
    """Try to fetch the PDF from arXiv.
    Returns None on success, or an error reason string on failure.
    """
    arxiv_id = _arxiv_id(entry)
    if not arxiv_id:
        return "no arXiv ID found"
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
    try:
        _download(pdf_url, dest_path)
        return None
    except FetchError as exc:
        return str(exc)


# ---------------------------------------------------------------------------
# Strategy 2 — Copernicus
# ---------------------------------------------------------------------------

_COPERNICUS_PREFIX = "10.5194/"


def _copernicus_pdf_url(doi: str) -> str | None:
    """Construct a direct PDF URL for a Copernicus publication (prefix 10.5194).

    Copernicus DOI patterns:
    - Preprint:          {abbrev}-{year}-{id}        → preprints/{doi_local}/{doi_local}.pdf
    - EGUsphere preprint: egusphere-{year}-{id}      → preprints/{year}/{doi_local}/{doi_local}.pdf
    - Published article: {abbrev}-{vol}-{page}-{year} → articles/{vol}/{page}/{year}/{doi_local}.pdf
    """
    if not doi.lower().startswith(_COPERNICUS_PREFIX):
        return None
    doi_local = doi[len(_COPERNICUS_PREFIX) :]
    parts = doi_local.split("-")

    # Published article: 4 segments, year is last (e.g. tc-17-1585-2023)
    if len(parts) == 4 and re.fullmatch(r"20\d\d", parts[3]):
        abbrev, vol, page, year = parts
        return f"https://{abbrev}.copernicus.org/articles/{vol}/{page}/{year}/{doi_local}.pdf"

    # Preprint: 3 segments, year is second (e.g. essd-2025-745, egusphere-2026-485)
    if len(parts) == 3 and re.fullmatch(r"20\d\d", parts[1]):
        abbrev, year = parts[0], parts[1]
        if abbrev == "egusphere":
            return f"https://egusphere.copernicus.org/preprints/{year}/{doi_local}/{doi_local}.pdf"
        return f"https://{abbrev}.copernicus.org/preprints/{doi_local}/{doi_local}.pdf"

    return None


def _try_copernicus(entry: BibEntry, dest_path: str) -> str | None:
    """Try to fetch the PDF directly from copernicus.org using the DOI pattern.
    Returns None on success, or an error reason string on failure.
    """
    if not entry.doi:
        return "no DOI"
    pdf_url = _copernicus_pdf_url(entry.doi)
    if not pdf_url:
        return "not a recognised Copernicus DOI"
    try:
        _download(pdf_url, dest_path)
        return None
    except FetchError as exc:
        return str(exc)


# ---------------------------------------------------------------------------
# Strategy 3 — OpenAlex
# ---------------------------------------------------------------------------


def _normalized_doi(doi: str) -> str:
    """Normalize DOI for provider lookups."""
    norm = doi.strip()
    norm = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", norm, flags=re.IGNORECASE)
    return norm


def _try_openalex(entry: BibEntry, dest_path: str, api_key: str) -> str | None:
    """Try OpenAlex lookup and download a direct PDF URL.

    Returns None on success, or an error reason string on failure.
    """
    if not entry.doi:
        return "entry has no DOI"
    if not api_key:
        return "no API key configured in Settings"

    lookup_doi = _normalized_doi(entry.doi)
    previous_api_key = pyalex.config.get("api_key")
    pyalex.config["api_key"] = api_key

    try:
        works = cast(
            list[dict[str, Any]],
            pyalex.Works().filter(doi=f"https://doi.org/{lookup_doi}").get(per_page=1)
        )
        if not works:
            return "no OpenAlex work found"

        work = works[0]
        work_id = str(work.get("id") or "").rstrip("/").split("/")[-1]
        if work_id:
            try:
                openalex_work = cast(Any, pyalex.Works()[work_id])
                pdf_bytes = cast(bytes, openalex_work.pdf.get())
                _write_pdf_bytes(pdf_bytes, dest_path)
                return None
            except Exception:
                pass

        pdf_candidates: list[str] = []

        content_urls = work.get("content_urls") or {}
        if content_urls.get("pdf"):
            pdf_candidates.append(content_urls["pdf"])

        best = work.get("best_oa_location") or {}
        if best.get("pdf_url"):
            pdf_candidates.append(best["pdf_url"])

        primary = work.get("primary_location") or {}
        if primary.get("pdf_url") and primary["pdf_url"] not in pdf_candidates:
            pdf_candidates.append(primary["pdf_url"])

        open_access = work.get("open_access") or {}
        if open_access.get("oa_url") and open_access["oa_url"] not in pdf_candidates:
            pdf_candidates.append(open_access["oa_url"])

        for location in work.get("locations", []):
            url = location.get("pdf_url")
            if url and url not in pdf_candidates:
                pdf_candidates.append(url)

        if not pdf_candidates:
            return "no direct PDF available"

        last_error = ""
        for url in pdf_candidates:
            try:
                _download(url, dest_path)
                return None
            except FetchError as exc:
                last_error = str(exc)
        return last_error
    except Exception:
        return "OpenAlex lookup failed"
    finally:
        pyalex.config["api_key"] = previous_api_key


# ---------------------------------------------------------------------------
# Strategy 4 — Unpaywall
# ---------------------------------------------------------------------------


def _try_unpaywall(entry: BibEntry, dest_path: str, email: str) -> str | None:
    """Try Unpaywall open-access lookup using only direct ``url_for_pdf`` links.

    Returns None on success, or an error reason string on failure.
    If Unpaywall only knows a landing page (url_for_pdf=None), the paper is
    reported as not fetchable via this strategy.
    """
    if not entry.doi:
        return "entry has no DOI"
    if not email:
        return "no email configured in Settings"
    api_url = f"https://api.unpaywall.org/v2/{entry.doi}?email={email}"
    req = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0"
            )
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return "Unpaywall lookup failed"

    # Collect all direct PDF URLs Unpaywall knows about
    pdf_candidates: list[str] = []
    best = data.get("best_oa_location") or {}
    if best.get("url_for_pdf"):
        pdf_candidates.append(best["url_for_pdf"])
    for loc in data.get("oa_locations", []):
        u = loc.get("url_for_pdf")
        if u and u not in pdf_candidates:
            pdf_candidates.append(u)

    if not pdf_candidates:
        return "no direct PDF available"

    last_error = ""
    for url in pdf_candidates:
        try:
            _download(url, dest_path)
            return None
        except FetchError as exc:
            last_error = str(exc)
    return last_error


# ---------------------------------------------------------------------------
# Strategy 5 — Direct URL
# ---------------------------------------------------------------------------


def _try_direct_url(entry: BibEntry, dest_path: str) -> str | None:
    """Try to download the entry's URL directly if it looks like a PDF.
    Returns None on success, or an error reason string on failure.
    """
    if not entry.url:
        return "entry has no URL"
    parsed = urlparse(entry.url)
    if parsed.scheme not in ("http", "https"):
        return "URL scheme is not http/https"
    # Quick HEAD request to check Content-Type before consuming bandwidth
    head_req = urllib.request.Request(
        entry.url,
        method="HEAD",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0"
            )
        },
    )
    content_type = ""
    try:
        with urllib.request.urlopen(head_req, timeout=10) as resp:
            content_type = resp.headers.get("Content-Type", "")
    except Exception:
        # Some servers reject HEAD; try GET download as fallback.
        content_type = ""

    if content_type and "pdf" not in content_type.lower():
        return f"URL does not serve a PDF (Content-Type: {content_type})"

    try:
        _download(entry.url, dest_path)
        return None
    except FetchError as exc:
        return str(exc)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def fetch_pdf(
    entry: BibEntry,
    dest_dir: str,
    unpaywall_email: str = "",
    openalex_api_key: str = "",
    overwrite: bool = False,
) -> str:
    """Fetch a PDF for *entry* and save it under *dest_dir*.

    Tries arXiv → Copernicus → OpenAlex (optional) → Unpaywall → direct URL.

    Returns the saved file path on success.
    Raises FetchError (with a human-readable message) if all strategies fail.
    """
    if not dest_dir:
        raise FetchError(
            "PDF base directory is not set. "
            "Open Settings (Ctrl+P → Settings) and set a base directory first."
        )

    try:
        os.makedirs(dest_dir, exist_ok=True)
    except OSError as exc:
        raise FetchError(f"Could not create destination directory: {dest_dir}: {exc}")

    dest_path = os.path.join(dest_dir, pdf_filename(entry))

    if os.path.exists(dest_path) and not overwrite:
        raise FetchError(f"File already exists: {dest_path}")

    reasons: list[str] = []

    reason = _try_arxiv(entry, dest_path)
    if reason is None:
        return dest_path
    reasons.append(f"arXiv: {reason}")

    reason = _try_copernicus(entry, dest_path)
    if reason is None:
        return dest_path
    reasons.append(f"Copernicus: {reason}")

    if openalex_api_key:
        reason = _try_openalex(entry, dest_path, openalex_api_key)
        if reason is None:
            return dest_path
        reasons.append(f"OpenAlex: {reason}")

    reason = _try_unpaywall(entry, dest_path, unpaywall_email)
    if reason is None:
        return dest_path
    reasons.append(f"Unpaywall: {reason}")

    reason = _try_direct_url(entry, dest_path)
    if reason is None:
        return dest_path
    reasons.append(f"Direct URL: {reason}")

    raise FetchError("Could not fetch PDF:\n" + "\n".join(f"  • {r}" for r in reasons))
