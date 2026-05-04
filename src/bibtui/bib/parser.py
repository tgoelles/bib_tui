from pathlib import Path

import bibtexparser
from bibtexparser import model as bpmodel

from .models import READ_STATES, BibEntry


class _SourceBlock:
    def __init__(
        self,
        kind: str,
        text: str,
        key: str | None = None,
        parsed_entry: BibEntry | None = None,
    ) -> None:
        self.kind = kind
        self.text = text
        self.key = key
        self.parsed_entry = parsed_entry


def _find_block_end(text: str, open_idx: int, open_char: str, close_char: str) -> int:
    """Find the closing delimiter of a BibTeX block, tracking brace/paren depth.

    In BibTeX syntax every ``{`` and ``}`` is structural regardless of a
    preceding backslash, so no escape-skipping is performed here.
    """
    depth = 0
    for i in range(open_idx, len(text)):
        ch = text[i]
        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def _build_line_offsets(text: str) -> list[int]:
    """Return a list where index *i* is the byte offset of line *i* (0-indexed)."""
    offsets: list[int] = []
    pos = 0
    for line in text.split("\n"):
        offsets.append(pos)
        pos += len(line) + 1  # +1 for the '\n'
    return offsets


def _parse_source_blocks(
    text: str, src_lib: bpmodel.Library | None = None
) -> list[_SourceBlock]:
    """Decompose *text* into _SourceBlock objects.

    Entry positions are anchored via bibtexparser's ``start_line`` attribute
    so that every ``@TYPE{...}`` block is located accurately even when field
    values contain ``@`` characters, unbalanced LaTeX constructs, or unusual
    whitespace.  Non-entry content (comments, whitespace, preambles, strings)
    between entries is preserved verbatim as ``kind='text'`` blocks.
    """
    if src_lib is None:
        try:
            src_lib = bibtexparser.parse_string(text)
        except Exception:
            return []

    if not src_lib.entries:
        return []

    line_offsets = _build_line_offsets(text)
    n = len(text)

    # Only Entry blocks have byte-accurate start_line; sort by position.
    sorted_entries = sorted(src_lib.entries, key=lambda e: e.start_line)

    blocks: list[_SourceBlock] = []
    cursor = 0

    for bp_entry in sorted_entries:
        start = line_offsets[bp_entry.start_line]

        # Emit text (comments, whitespace, etc.) before this entry.
        if start > cursor:
            blocks.append(_SourceBlock(kind="text", text=text[cursor:start]))

        # Locate the opening delimiter of the entry body (skip @TYPE_NAME).
        j = start + 1  # skip '@'
        while j < n and text[j].isalpha():
            j += 1
        while j < n and text[j].isspace():
            j += 1

        if j >= n or text[j] not in "{(":
            # Unexpected format — emit remainder as text and stop.
            blocks.append(_SourceBlock(kind="text", text=text[start:]))
            cursor = n
            break

        open_char = text[j]
        close_char = "}" if open_char == "{" else ")"
        end = _find_block_end(text, j, open_char, close_char)

        if end < 0:
            blocks.append(_SourceBlock(kind="text", text=text[start:]))
            cursor = n
            break

        block_text = text[start:end]
        cursor = end

        parsed_entry: BibEntry | None = None
        try:
            parsed_entry = _to_bib_entry(bp_entry)
        except Exception:
            parsed_entry = None

        blocks.append(
            _SourceBlock(
                kind="entry",
                text=block_text,
                key=bp_entry.key,
                parsed_entry=parsed_entry,
            )
        )

    # Trailing text after the last entry.
    if cursor < n:
        blocks.append(_SourceBlock(kind="text", text=text[cursor:]))

    return blocks


def _entry_signature(entry: BibEntry) -> tuple:
    raw_items = tuple(
        sorted((k, v) for k, v in entry.raw_fields.items() if isinstance(v, str) and v)
    )
    return (
        entry.key,
        entry.entry_type,
        entry.title,
        entry.author,
        entry.year,
        entry.journal,
        entry.doi,
        entry.url,
        entry.abstract,
        entry.keywords,
        entry.comment,
        entry.rating,
        entry.read_state,
        entry.priority,
        entry.file,
        raw_items,
    )


def _serialize_entry(entry: BibEntry) -> str:
    text = entry_to_bibtex_str(entry)
    return text if text.endswith("\n") else text + "\n"


def _full_rewrite(entries: list[BibEntry], path: str) -> None:
    lib = bibtexparser.Library()
    for entry in entries:
        lib.add(_to_bp_entry(entry))
    bibtexparser.write_file(path, lib)


def _field_str(entry: bpmodel.Entry, key: str) -> str:
    """Extract string value from a bibtexparser Entry field, stripping outer braces.

    Field name lookup is case-insensitive: ``AUTHOR`` and ``author`` both work.
    """
    # bibtexparser v2 preserves original casing — search case-insensitively
    f = entry.fields_dict.get(key) or entry.fields_dict.get(key.upper())
    if f is None:
        # Full case-insensitive scan as final fallback
        key_lower = key.lower()
        for k, v in entry.fields_dict.items():
            if k.lower() == key_lower:
                f = v
                break
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
    known = {
        "title",
        "author",
        "year",
        "journal",
        "doi",
        "url",
        "abstract",
        "keywords",
        "comment",
        "ranking",
        "readstatus",
        "priority",
        "file",
    }
    raw = {}
    for k, f in entry.fields_dict.items():
        # Normalise to lowercase so raw_fields are always consistent
        k_norm = k.lower()
        if k_norm not in known:
            val = f.value
            raw[k_norm] = val if isinstance(val, str) else str(val)

    ranking_str = _field_str(entry, "ranking")  # JabRef format: rank1..rank5
    try:
        rating = (
            max(0, min(5, int(ranking_str.removeprefix("rank")))) if ranking_str else 0
        )
    except ValueError:
        rating = 0

    priority_str = _field_str(entry, "priority")  # JabRef format: prio1..prio3
    try:
        priority = (
            max(0, min(3, int(priority_str.removeprefix("prio"))))
            if priority_str
            else 0
        )
    except ValueError:
        priority = 0

    read_state = _field_str(entry, "readstatus")  # JabRef field name
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
        url=_field_str(entry, "url"),
        abstract=_field_str(entry, "abstract"),
        keywords=_field_str(entry, "keywords"),
        comment=_field_str(entry, "comment"),
        rating=rating,
        read_state=read_state,
        priority=priority,
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
    add("url", entry.url)
    add("abstract", entry.abstract)
    add("keywords", entry.keywords)
    add("comment", entry.comment)

    if entry.rating:
        add("ranking", f"rank{entry.rating}")
    if entry.read_state:
        add("readstatus", entry.read_state)
    if entry.priority:
        add("priority", f"prio{entry.priority}")
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
    path_obj = Path(path)
    try:
        original_text = path_obj.read_text(encoding="utf-8")
    except OSError:
        _full_rewrite(entries, path)
        return

    try:
        source_lib = bibtexparser.parse_string(original_text)
    except Exception:
        _full_rewrite(entries, path)
        return

    source_keys = [e.key for e in source_lib.entries]
    if len(source_keys) != len(set(source_keys)):
        # Duplicate keys: cannot safely patch incrementally.
        _full_rewrite(entries, path)
        return

    blocks = _parse_source_blocks(original_text, src_lib=source_lib)
    if not any(block.kind == "entry" for block in blocks):
        _full_rewrite(entries, path)
        return

    current_by_key: dict[str, BibEntry] = {}
    for entry in entries:
        if entry.key in current_by_key:
            _full_rewrite(entries, path)
            return
        current_by_key[entry.key] = entry

    output: list[str] = []
    used_keys: set[str] = set()

    for block in blocks:
        if block.kind != "entry" or block.key is None:
            output.append(block.text)
            continue

        current = current_by_key.get(block.key)
        if current is None:
            # Entry was deleted: drop just this block, keep surrounding text untouched.
            continue

        used_keys.add(block.key)
        if block.parsed_entry is not None and _entry_signature(
            current
        ) == _entry_signature(block.parsed_entry):
            output.append(block.text)
        else:
            output.append(_serialize_entry(current))

    new_entries = [entry for entry in entries if entry.key not in used_keys]
    if new_entries:
        existing = "".join(output)
        if existing and not existing.endswith("\n"):
            output.append("\n")
        if existing and not existing.endswith("\n\n"):
            output.append("\n")
        output.append(
            "\n\n".join(_serialize_entry(e).rstrip("\n") for e in new_entries)
        )
        output.append("\n")

    rewritten = "".join(output)
    if rewritten != original_text:
        path_obj.write_text(rewritten, encoding="utf-8")
