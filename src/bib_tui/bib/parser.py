from __future__ import annotations
import bibtexparser
from bibtexparser import model as bpmodel
from .models import BibEntry, READ_STATES


def _field_str(entry: bpmodel.Entry, key: str) -> str:
    """Extract string value from a bibtexparser Entry field, stripping outer braces."""
    f = entry.fields_dict.get(key)
    if f is None:
        return ""
    val = f.value
    if isinstance(val, str):
        val = val.strip()
        # Strip outer curly braces that BibTeX uses for case protection
        if val.startswith("{") and val.endswith("}"):
            val = val[1:-1]
        return val
    return str(val).strip()


def _to_bib_entry(entry: bpmodel.Entry) -> BibEntry:
    known = {"title", "author", "year", "journal", "doi", "abstract", "keywords", "ranking", "readstate", "tags", "file"}
    raw = {}
    for k, f in entry.fields_dict.items():
        if k not in known:
            val = f.value
            raw[k] = val if isinstance(val, str) else str(val)

    ranking_str = _field_str(entry, "ranking")  # JabRef format: rank1..rank5
    try:
        rating = max(0, min(5, int(ranking_str.removeprefix("rank")))) if ranking_str else 0
    except ValueError:
        rating = 0

    tags_str = _field_str(entry, "tags")
    tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []

    read_state = _field_str(entry, "readstate")
    if read_state not in READ_STATES:
        read_state = ""

    return BibEntry(
        key=entry.key,
        entry_type=entry.entry_type,
        title=_field_str(entry, "title"),
        author=_field_str(entry, "author"),
        year=_field_str(entry, "year"),
        journal=_field_str(entry, "journal"),
        doi=_field_str(entry, "doi"),
        abstract=_field_str(entry, "abstract"),
        keywords=_field_str(entry, "keywords"),
        rating=rating,
        read_state=read_state,
        tags=tags,
        file=_field_str(entry, "file"),
        raw_fields=raw,
    )


def _to_bp_entry(entry: BibEntry) -> bpmodel.Entry:
    fields: list[bpmodel.Field] = []

    def add(key: str, value: str) -> None:
        if value:
            fields.append(bpmodel.Field(key=key, value=value))

    add("title", entry.title)
    add("author", entry.author)
    add("year", entry.year)
    add("journal", entry.journal)
    add("doi", entry.doi)
    add("abstract", entry.abstract)
    add("keywords", entry.keywords)

    if entry.rating:
        add("ranking", f"rank{entry.rating}")
    if entry.read_state:
        add("readstate", entry.read_state)
    if entry.tags:
        add("tags", ", ".join(entry.tags))
    if entry.file:
        add("file", entry.file)

    for k, v in entry.raw_fields.items():
        if v:
            fields.append(bpmodel.Field(key=k, value=v))

    return bpmodel.Entry(key=entry.key, entry_type=entry.entry_type, fields=fields)


def entry_to_bibtex_str(entry: BibEntry) -> str:
    """Serialize a single BibEntry to a BibTeX string."""
    lib = bibtexparser.Library()
    lib.add(_to_bp_entry(entry))
    return bibtexparser.write_string(lib)


def bibtex_str_to_entry(text: str) -> BibEntry:
    """Parse a BibTeX string containing a single entry back to a BibEntry.

    Raises ValueError if parsing fails or no entry is found.
    """
    lib = bibtexparser.parse_string(text)
    if not lib.entries:
        raise ValueError("No valid BibTeX entry found in the text.")
    return _to_bib_entry(lib.entries[0])


def load(path: str) -> list[BibEntry]:
    lib = bibtexparser.parse_file(path)
    return [_to_bib_entry(e) for e in lib.entries]


def save(entries: list[BibEntry], path: str) -> None:
    lib = bibtexparser.Library()
    for entry in entries:
        lib.add(_to_bp_entry(entry))
    bibtexparser.write_file(path, lib)
