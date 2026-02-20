"""PDF fetching utilities.

Tries three strategies in order:
1. arXiv — free PDF via the arXiv API (DOI 10.48550/arXiv.* or arxiv.org URL)
2. Unpaywall — open-access PDF lookup by DOI (requires email)
3. Direct URL — download if the entry's URL points directly to a PDF

Raises FetchError if none of the strategies succeed.
"""

import json
import os
import re
import urllib.request
from urllib.parse import urlparse

from bib_tui.bib.models import BibEntry


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
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if "pdf" not in content_type.lower():
                raise FetchError(
                    f"URL did not return a PDF (Content-Type: {content_type}): {url}"
                )
            with open(dest_path, "wb") as f:
                while chunk := resp.read(65536):
                    f.write(chunk)
    except FetchError:
        raise
    except Exception as exc:
        raise FetchError(f"Download failed from {url}: {exc}") from exc


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
# Strategy 2 — Unpaywall
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
    except Exception as exc:
        return f"Unpaywall API error: {exc}"

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
        return (
            "Unpaywall found no direct PDF URL (publisher only provides a landing page)"
        )

    last_error = ""
    for url in pdf_candidates:
        try:
            _download(url, dest_path)
            return None
        except FetchError as exc:
            last_error = str(exc)
    return last_error


# ---------------------------------------------------------------------------
# Strategy 3 — Direct URL
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
    try:
        with urllib.request.urlopen(head_req, timeout=10) as resp:
            content_type = resp.headers.get("Content-Type", "")
    except Exception as exc:
        return f"HEAD request failed: {exc}"

    if "pdf" not in content_type.lower():
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
    overwrite: bool = False,
) -> str:
    """Fetch a PDF for *entry* and save it under *dest_dir*.

    Tries arXiv → Unpaywall → direct URL in order.

    Returns the saved file path on success.
    Raises FetchError (with a human-readable message) if all strategies fail.
    """
    if not dest_dir:
        raise FetchError(
            "PDF base directory is not set. "
            "Open Settings (Ctrl+P → Settings) and set a base directory first."
        )

    dest_path = os.path.join(dest_dir, pdf_filename(entry))

    if os.path.exists(dest_path) and not overwrite:
        raise FetchError(f"File already exists: {dest_path}")

    reasons: list[str] = []

    reason = _try_arxiv(entry, dest_path)
    if reason is None:
        return dest_path
    reasons.append(f"arXiv: {reason}")

    reason = _try_unpaywall(entry, dest_path, unpaywall_email)
    if reason is None:
        return dest_path
    reasons.append(f"Unpaywall: {reason}")

    reason = _try_direct_url(entry, dest_path)
    if reason is None:
        return dest_path
    reasons.append(f"Direct URL: {reason}")

    raise FetchError("Could not fetch PDF:\n" + "\n".join(f"  • {r}" for r in reasons))
