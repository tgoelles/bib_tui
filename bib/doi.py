from __future__ import annotations
from habanero import Crossref
from .models import BibEntry


def fetch_by_doi(doi: str) -> BibEntry:
    cr = Crossref()
    result = cr.works(ids=doi)
    msg = result["message"]

    def get_str(key: str) -> str:
        val = msg.get(key, "")
        if isinstance(val, list):
            return val[0] if val else ""
        return str(val) if val else ""

    # Authors
    authors = msg.get("author", [])
    author_parts = []
    for a in authors:
        family = a.get("family", "")
        given = a.get("given", "")
        if family and given:
            author_parts.append(f"{family}, {given}")
        elif family:
            author_parts.append(family)
    author_str = " and ".join(author_parts)

    # Year
    year = ""
    date = msg.get("published-print") or msg.get("published-online") or msg.get("issued")
    if date:
        parts = date.get("date-parts", [[]])
        if parts and parts[0]:
            year = str(parts[0][0])

    # Title
    titles = msg.get("title", [])
    title = titles[0] if titles else ""

    # Journal
    container = msg.get("container-title", [])
    journal = container[0] if container else ""

    # Entry type
    crossref_type = msg.get("type", "journal-article")
    type_map = {
        "journal-article": "article",
        "proceedings-article": "inproceedings",
        "book": "book",
        "book-chapter": "incollection",
        "dissertation": "phdthesis",
        "report": "techreport",
        "dataset": "misc",
        "posted-content": "misc",
    }
    entry_type = type_map.get(crossref_type, "misc")

    # Build citation key: AuthorYEAR
    key_author = authors[0].get("family", "Unknown").replace(" ", "") if authors else "Unknown"
    key = f"{key_author}{year}"

    raw: dict[str, str] = {}
    if msg.get("volume"):
        raw["volume"] = str(msg["volume"])
    if msg.get("issue"):
        raw["number"] = str(msg["issue"])
    page = msg.get("page", "")
    if page:
        raw["pages"] = str(page)
    publisher = msg.get("publisher", "")
    if publisher:
        raw["publisher"] = publisher

    return BibEntry(
        key=key,
        entry_type=entry_type,
        title=title,
        author=author_str,
        year=year,
        journal=journal,
        doi=doi,
        raw_fields=raw,
    )
