import re

from habanero import Crossref

from bibtui.utils.dates import now_date_added_value

from .citekeys import author_year_base
from .models import BibEntry


def _journal_for_preprint(msg: dict, doi: str, cr: Crossref) -> str:
    """Derive the journal name for a posted-content preprint with no container-title.

    Strategy:
    1. Some servers (bioRxiv, medRxiv, …) populate `institution[0].name`.
    2. Otherwise, find a published journal-article from the same DOI prefix and
       abbreviation, retrieve its container-title, then check whether a Discussions
       variant of that journal exists (Copernicus preprint model).
    """
    institution = msg.get("institution") or []
    if institution:
        name = institution[0].get("name", "")
        if name:
            return name

    parts = doi.split("/", 1)
    if len(parts) != 2:
        return ""
    prefix, local = parts
    m = re.match(r"^([a-z]+)-", local)
    if not m:
        return ""
    abbrev = m.group(1)

    # EGUsphere is a general preprint server with no matching published-article DOIs;
    # it is not registered as a journal in Crossref, so the lookup below would fail.
    if abbrev == "egusphere":
        return "EGUsphere"

    try:
        pub = cr.works(
            filter={"prefix": prefix, "type": "journal-article"},
            query=abbrev,
            limit=5,
            select=["container-title", "DOI"],
        )
        parent_journal = ""
        for item in pub["message"]["items"]:
            if (item.get("DOI", "").startswith(f"{prefix}/{abbrev}-")
                    and item.get("container-title")):
                parent_journal = item["container-title"][0]
                break
        if not parent_journal:
            return ""

        # Check if a Discussions variant exists (Copernicus preprint model)
        journals = cr.journals(query=f"{parent_journal} Discussions", limit=5)
        for journal in journals["message"]["items"]:
            title = journal.get("title", "")
            if title.startswith(parent_journal) and "Discussion" in title:
                return title

        return parent_journal
    except Exception:
        return ""


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
    date = (
        msg.get("published-print")
        or msg.get("published-online")
        or msg.get("issued")
        or msg.get("posted")
    )
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
    if not journal and msg.get("type") == "posted-content":
        journal = _journal_for_preprint(msg, doi, cr)

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

    # Build citation key: AuthorYear (normalized)
    key = author_year_base(author_str, year)

    raw: dict[str, str] = {
        "date-added": now_date_added_value(),
    }
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
