"""Fetch BibTeX metadata for a book by ISBN from Open Library.

CrossRef only knows books that publishers registered a DOI for, and its ISBN
filter misses most of them; Open Library covers far more books and needs no
API key.
"""

import re

import httpx

from bibtui.utils.dates import now_date_added_value
from bibtui.utils.isbn import normalize_isbn

from .authors import to_bibtex_name
from .citekeys import author_year_base
from .models import BibEntry

_API_URL = "https://openlibrary.org/api/books"


def fetch_by_isbn(isbn: str) -> BibEntry:
    """Look up *isbn* (ISBN-10 or -13, hyphens allowed) on Open Library.

    Raises ``ValueError`` for an invalid ISBN, ``LookupError`` if Open
    Library has no record of it, ``httpx.HTTPError`` on network failure.
    """
    isbn13 = normalize_isbn(isbn)
    if not isbn13:
        raise ValueError(f"Not a valid ISBN: {isbn}")
    bibkey = f"ISBN:{isbn13}"
    resp = httpx.get(
        _API_URL,
        params={"bibkeys": bibkey, "format": "json", "jscmd": "data"},
        headers={"User-Agent": "bibtui (https://github.com/tgoelles/bib_tui)"},
        timeout=20,
        follow_redirects=True,
    )
    resp.raise_for_status()
    book = resp.json().get(bibkey)
    if not book or not book.get("title"):
        raise LookupError(f"Open Library has no record for ISBN {isbn13}")

    title = book["title"]
    if book.get("subtitle"):
        title = f"{title}: {book['subtitle']}"
    authors = [to_bibtex_name(a.get("name", "")) for a in book.get("authors", [])]
    author_str = " and ".join(a for a in authors if a)
    year_match = re.search(r"\d{4}", book.get("publish_date", ""))
    year = year_match.group(0) if year_match else ""

    raw: dict[str, str] = {"date-added": now_date_added_value(), "isbn": isbn13}
    publishers = book.get("publishers") or []
    if publishers and publishers[0].get("name"):
        raw["publisher"] = publishers[0]["name"]
    places = book.get("publish_places") or []
    if places and places[0].get("name"):
        raw["address"] = places[0]["name"]

    return BibEntry(
        key=author_year_base(author_str, year),
        entry_type="book",
        title=title,
        author=author_str,
        year=year,
        raw_fields=raw,
    )
