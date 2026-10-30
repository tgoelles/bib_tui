"""Round-trip integrity of the incremental save (``parser.save``).

Every test edits entries the way the app does (mutate the ``BibEntry``, then
save) and checks two things after reloading:

* the data is exactly what was intended — the edit landed, nothing else moved;
* the file text outside the edited field is untouched.

See #70 and #78 for the bugs these guard against.
"""

import copy
import dataclasses
from collections.abc import Callable
from pathlib import Path

import bibtexparser as bibtexparser_lib
import pytest

from bibtui.bib import parser
from bibtui.bib.models import BibEntry

EXAMPLES = Path(__file__).parent / "bib_examples"
EDGE_CASES = EXAMPLES / "edge_cases.bib"

# name -> (bib field name written to the file, edit applied to the entry)
EDITS: dict[str, tuple[str, Callable[[BibEntry], None]]] = {
    "rating": ("ranking", lambda e: setattr(e, "rating", 4 if e.rating == 3 else 3)),
    "read_state": (
        "readstatus",
        lambda e: setattr(
            e, "read_state", "skimmed" if e.read_state == "read" else "read"
        ),
    ),
    "author": ("author", lambda e: setattr(e, "author", "Probe, X and Doe, J")),
    "title": ("title", lambda e: setattr(e, "title", "{Probe} Title")),
    "clear_author": ("author", lambda e: setattr(e, "author", "")),
}


def _entry_blocks(path: Path) -> list[tuple[str, str]]:
    """Return ``(key, block_text)`` for each entry in *path*."""
    text = path.read_text(encoding="utf-8")
    return [
        (b.key, b.text)
        for b in parser._parse_source_blocks(text)
        if b.kind == "entry" and b.key
    ]


def _normalised(line: str) -> str:
    # Adding a field after a last field without trailing comma adds one there.
    return line.rstrip().rstrip(",")


def _field_line_spans(block_text: str) -> dict[str, range] | None:
    """Map each field to the block lines it occupies, or None if fields share
    a line (such layouts are re-serialized, so text isn't preserved)."""
    entry = bibtexparser_lib.parse_string(block_text).entries[0]
    starts = sorted(
        (f.start_line - entry.start_line, f.key.lower()) for f in entry.fields
    )
    if any(line == 0 for line, _ in starts) or len({line for line, _ in starts}) != len(
        starts
    ):
        return None
    lines = block_text.splitlines()
    close = max(i for i, text in enumerate(lines) if text.strip() in ("}", ")"))
    bounds = [line for line, _ in starts] + [close]
    return {key: range(first, bounds[n + 1]) for n, (first, key) in enumerate(starts)}


def _check_edit(tmp_path: Path, block_text: str, edit_name: str) -> None:
    field, edit = EDITS[edit_name]
    path = tmp_path / "entry.bib"
    path.write_text(block_text, encoding="utf-8")

    entries = parser.load(str(path))
    assert len(entries) == 1
    edit(entries[0])
    expected = copy.deepcopy(entries[0])

    parser.save(entries, str(path))
    new_text = path.read_text(encoding="utf-8")

    reloaded = parser.load(str(path))
    assert len(reloaded) == 1, new_text
    assert dataclasses.asdict(reloaded[0]) == dataclasses.asdict(expected), new_text

    spans = _field_line_spans(block_text)
    if spans is None:
        return
    edited = spans.get(field, range(0))
    new_lines = {_normalised(line) for line in new_text.splitlines()}
    lost = [
        line
        for i, line in enumerate(block_text.splitlines())
        if i not in edited and _normalised(line) not in new_lines
    ]
    assert lost == [], new_text


# ---------------------------------------------------------------------------
# edge-case layouts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("edit_name", list(EDITS))
@pytest.mark.parametrize(
    ("key", "block_text"),
    _entry_blocks(EDGE_CASES),
    ids=lambda v: v if "\n" not in v else "",
)
def test_edge_case_entry_survives_edit(tmp_path, key, block_text, edit_name) -> None:
    _check_edit(tmp_path, block_text, edit_name)


def test_multiline_last_field_gets_comma_when_field_added(tmp_path) -> None:
    """A rating added after a multi-line last value used to be swallowed (#78)."""
    block = dict(_entry_blocks(EDGE_CASES))["MultilineLast2020"]
    path = tmp_path / "e.bib"
    path.write_text(block, encoding="utf-8")

    entries = parser.load(str(path))
    entries[0].rating = 3
    parser.save(entries, str(path))

    assert path.read_text(encoding="utf-8") == block.replace(
        "    several lines\n  }\n}", "    several lines\n  },\n  ranking = {rank3}\n}"
    )


def test_two_fields_on_one_line_edit_keeps_other_field(tmp_path) -> None:
    """Editing author used to overwrite the title on the same line (#78)."""
    block = dict(_entry_blocks(EDGE_CASES))["TwoPerLine2020"]
    path = tmp_path / "e.bib"
    path.write_text(block, encoding="utf-8")

    entries = parser.load(str(path))
    entries[0].author = "Roe, R"
    parser.save(entries, str(path))

    reloaded = parser.load(str(path))[0]
    assert (reloaded.title, reloaded.author, reloaded.year) == ("T", "Roe, R", "2020")


@pytest.mark.parametrize("new_abstract", ["short", ""], ids=["edit", "delete"])
def test_multiline_field_replaced_as_a_whole(tmp_path, new_abstract) -> None:
    block = dict(_entry_blocks(EDGE_CASES))["MultilineMiddle2020"]
    path = tmp_path / "e.bib"
    path.write_text(block, encoding="utf-8")

    entries = parser.load(str(path))
    entries[0].abstract = new_abstract
    parser.save(entries, str(path))

    replacement = f"  abstract = {{{new_abstract}}},\n" if new_abstract else ""
    expected = block.replace(
        "  abstract = {line one\n    line two\n    line three},\n", replacement
    )
    assert path.read_text(encoding="utf-8") == expected


def test_entry_type_change_is_saved(tmp_path) -> None:
    """Changing the entry type in the edit form used to be lost on save."""
    path = tmp_path / "e.bib"
    path.write_text("@article{a,\n  title = {T},\n}\n", encoding="utf-8")

    entries = parser.load(str(path))
    entries[0].entry_type = "book"
    parser.save(entries, str(path))

    assert path.read_text(encoding="utf-8") == "@book{a,\n  title = {T},\n}\n"


# ---------------------------------------------------------------------------
# line endings (#79)
# ---------------------------------------------------------------------------

CRLF_SOURCE = (
    b"@article{a,\r\n  title = {T},\r\n}\r\n\r\n@article{b,\r\n  title = {U},\r\n}\r\n"
)


def test_crlf_file_keeps_crlf_after_edit(tmp_path) -> None:
    path = tmp_path / "crlf.bib"
    path.write_bytes(CRLF_SOURCE)

    entries = parser.load(str(path))
    entries[0].title = "T2"
    parser.save(entries, str(path))

    assert path.read_bytes() == CRLF_SOURCE.replace(b"{T}", b"{T2}")


def test_crlf_file_keeps_crlf_when_entry_added(tmp_path) -> None:
    path = tmp_path / "crlf.bib"
    path.write_bytes(CRLF_SOURCE)

    entries = parser.load(str(path))
    entries.append(BibEntry(key="c", entry_type="misc", title="New"))
    parser.save(entries, str(path))

    data = path.read_bytes()
    assert data.startswith(CRLF_SOURCE)
    assert b"\n" not in data.replace(b"\r\n", b"")


def test_crlf_noop_save_does_not_touch_file(tmp_path) -> None:
    path = tmp_path / "crlf.bib"
    path.write_bytes(CRLF_SOURCE)
    parser.save(parser.load(str(path)), str(path))
    assert path.read_bytes() == CRLF_SOURCE


# ---------------------------------------------------------------------------
# duplicate keys
# ---------------------------------------------------------------------------


def test_duplicate_key_block_is_preserved_when_other_entry_edited(tmp_path) -> None:
    """bibtexparser drops a repeated key from the entries (it is not loaded into
    the app), but saving must still keep that block verbatim on disk."""
    source = (
        "@article{a,\n  title = {First},\n}\n\n"
        "@article{a,\n  title = {Second},\n}\n\n"
        "@article{b,\n  title = {B},\n}\n"
    )
    path = tmp_path / "dup.bib"
    path.write_text(source, encoding="utf-8")

    entries = parser.load(str(path))
    assert [e.key for e in entries] == ["a", "b"]
    entries[0].rating = 2
    parser.save(entries, str(path))

    assert path.read_text(encoding="utf-8") == source.replace(
        "{First},\n}", "{First},\n  ranking = {rank2},\n}"
    )


def test_string_macros_survive_edit_of_entry_using_them(tmp_path) -> None:
    """The patch check must resolve the file's @string macros like load() does;
    otherwise every edit re-serialized the entry, inlining ``jgr`` and turning
    the month macro ``jan`` into the literal ``{jan}``."""
    source = (
        '@string{jgr = "J. Geophys. Res."}\n\n'
        "@article{m,\n"
        "  title = {T},\n"
        "  journal = jgr,\n"
        "  month = jan,\n"
        "  year = {2020},\n"
        "}\n"
    )
    path = tmp_path / "macro.bib"
    path.write_text(source, encoding="utf-8")

    entries = parser.load(str(path))
    assert entries[0].journal == "J. Geophys. Res."
    entries[0].rating = 3
    parser.save(entries, str(path))

    assert path.read_text(encoding="utf-8") == source.replace(
        "{2020},\n}", "{2020},\n  ranking = {rank3},\n}"
    )


# ---------------------------------------------------------------------------
# real libraries
# ---------------------------------------------------------------------------

LIBRARY_BLOCKS = [
    pytest.param(key, text, id=f"{lib.stem}:{key}")
    for lib in (EXAMPLES / "ex1.bib", EXAMPLES / "MyCollection.bib")
    for key, text in _entry_blocks(lib)
]
# A fixed sample keeps the default run fast; the full sweep is marked slow.
SAMPLE_EVERY = 25


@pytest.mark.parametrize("edit_name", ["rating", "title"])
@pytest.mark.parametrize(("key", "block_text"), LIBRARY_BLOCKS[::SAMPLE_EVERY])
def test_library_entry_survives_edit_sample(
    tmp_path, key, block_text, edit_name
) -> None:
    _check_edit(tmp_path, block_text, edit_name)


@pytest.mark.slow
@pytest.mark.parametrize("edit_name", list(EDITS))
@pytest.mark.parametrize(("key", "block_text"), LIBRARY_BLOCKS)
def test_library_entry_survives_edit_full(tmp_path, key, block_text, edit_name) -> None:
    _check_edit(tmp_path, block_text, edit_name)
