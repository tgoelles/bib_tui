"""Fetch BibTeX metadata for an arXiv preprint from the arXiv API.

arXiv's own DOIs (``10.48550/arXiv.<id>``) are registered with DataCite, not
CrossRef, so :func:`bibtui.bib.doi.fetch_by_doi` can't resolve them — the
arXiv API is queried directly instead. It also covers pre-2022 and pre-2007
(``hep-th/9711200``-style) preprints that never got a DOI at all.
"""

import re
import threading
import time
import xml.etree.ElementTree as ET

import httpx

from bibtui.utils.dates import now_date_added_value

from .authors import to_bibtex_name
from .citekeys import author_year_base
from .models import BibEntry

ARXIV_DOI_PREFIX = "10.48550/arXiv."

_API_URL = "https://export.arxiv.org/api/query"
_NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

# arXiv asks API clients to keep to one request every three seconds; a batch
# import of a folder of preprints would otherwise trip its rate limiting.
_MIN_INTERVAL_SECONDS = 3.0
_throttle_lock = threading.Lock()
_last_request_at = 0.0


def _throttle() -> None:
    global _last_request_at
    with _throttle_lock:
        wait = _last_request_at + _MIN_INTERVAL_SECONDS - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()


def _text(el: ET.Element, path: str) -> str:
    found = el.find(path, _NS)
    if found is None or not found.text:
        return ""
    return " ".join(found.text.split())


def fetch_by_arxiv_id(arxiv_id: str) -> BibEntry:
    """Look up *arxiv_id* (``2301.12345`` or ``hep-th/9711200``) on arXiv.

    Raises ``LookupError`` if arXiv doesn't know the id, ``httpx.HTTPError``
    on network failure.
    """
    _throttle()
    resp = httpx.get(
        _API_URL,
        params={"id_list": arxiv_id, "max_results": 1},
        headers={"User-Agent": "bibtui (https://github.com/tgoelles/bib_tui)"},
        timeout=20,
        follow_redirects=True,
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    entry = root.find("a:entry", _NS)
    # An unknown id comes back as an empty feed (older API versions sent a
    # single entry titled "Error" instead).
    title = _text(entry, "a:title") if entry is not None else ""
    if entry is None or not title or title == "Error":
        raise LookupError(f"arXiv has no record for {arxiv_id}")

    authors = [
        to_bibtex_name(_text(a, "a:name")) for a in entry.findall("a:author", _NS)
    ]
    author_str = " and ".join(a for a in authors if a)
    published = _text(entry, "a:published")
    year = published[:4] if re.match(r"\d{4}", published) else ""

    raw: dict[str, str] = {
        "date-added": now_date_added_value(),
        "eprint": arxiv_id,
        "archiveprefix": "arXiv",
    }
    primary = entry.find("arxiv:primary_category", _NS)
    if primary is not None and primary.get("term"):
        raw["primaryclass"] = primary.get("term", "")
    journal_ref = _text(entry, "arxiv:journal_ref")
    if journal_ref:
        raw["note"] = journal_ref

    return BibEntry(
        key=author_year_base(author_str, year),
        entry_type="misc",
        title=title,
        author=author_str,
        year=year,
        journal="arXiv",
        doi=f"{ARXIV_DOI_PREFIX}{arxiv_id}",
        url=f"https://arxiv.org/abs/{arxiv_id}",
        abstract=_text(entry, "a:summary"),
        raw_fields=raw,
    )
