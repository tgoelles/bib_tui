"""Single source of truth for the entry-browsing table's columns.

Each display column is defined **once** as a :class:`ColumnSpec` carrying its
header label, width, cell renderer and sort key.  ``EntryList`` builds the
table by iterating a list of specs, so the column set (which columns, in what
order) is data — configurable and persisted — instead of logic duplicated
across several methods.

The 11 :data:`DEFAULT_TABLE_COLUMNS` reproduce the historical hard-coded table
exactly; any other BibTeX field discovered in the library can be surfaced as a
generic field column via :func:`field_column_spec`.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from bibtui.bib.models import READ_STATES, BibEntry
from bibtui.pdf.paths import find_pdf_for_entry
from bibtui.utils.dates import DATE_ADDED_KEYS, extract_date_added, format_bib_date


@dataclass(frozen=True)
class ColumnSpec:
    """Everything the table needs to render and sort one column."""

    key: str  # stable id stored in config, e.g. "state", "title", "volume"
    label: str  # terse table header (e.g. "◉", "Author")
    name: str  # human-readable name shown in the config panel ("Read state")
    width: int  # fixed column width; the starting width when flex
    render: Callable[[BibEntry, str], str]  # (entry, pdf_base_dir) -> cell text
    sort_key: Callable[[BibEntry], Any]
    flex: bool = False  # Title-style: expand to fill remaining width
    dynamic: bool = False  # cell can change in place (refresh_row updates it)


def _truncate(text: str, width: int) -> str:
    """Trim *text* to *width* characters with an ellipsis when it overflows."""
    if len(text) <= width:
        return text
    return text[: max(0, width - 1)] + "…"


def _journal_value(entry: BibEntry) -> str:
    return entry.journal or entry.raw_fields.get("booktitle", "")


def _file_icon(entry: BibEntry, pdf_base_dir: str) -> str:
    if not entry.file:
        return " "
    return "■" if find_pdf_for_entry(entry.file, entry.key, pdf_base_dir) else "□"


def _date_added(entry: BibEntry) -> str:
    return format_bib_date(extract_date_added(entry.raw_fields))


# The built-in columns, defined once. ``label`` is the terse table header;
# ``name`` is the readable name shown in the config panel (so a column whose
# header is a symbol/emoji is still identifiable there).
_BUILTINS: tuple[ColumnSpec, ...] = (
    ColumnSpec(
        key="state",
        label="◉",
        name="Read state",
        width=1,
        render=lambda e, _b: e.read_state_icon,
        sort_key=lambda e: (
            READ_STATES.index(e.read_state) if e.read_state in READ_STATES else 0
        ),
        dynamic=True,
    ),
    ColumnSpec(
        key="priority",
        label="!",
        name="Priority",
        width=1,
        render=lambda e, _b: e.priority_icon,
        sort_key=lambda e: e.priority if e.priority > 0 else 99,
        dynamic=True,
    ),
    ColumnSpec(
        key="file",
        label="◫",
        name="PDF",
        width=1,
        render=_file_icon,
        sort_key=lambda e: 0 if e.file else 1,
        dynamic=True,
    ),
    ColumnSpec(
        key="url",
        label="🔗",
        name="URL",
        width=2,
        render=lambda e, _b: e.url_icon,
        sort_key=lambda e: 0 if e.url else 1,
        dynamic=True,
    ),
    ColumnSpec(
        key="citekey",
        label="Key",
        name="Cite key",
        width=16,
        render=lambda e, _b: e.key,
        sort_key=lambda e: e.key.lower(),
    ),
    ColumnSpec(
        key="type",
        label="Type",
        name="Type",
        width=7,
        render=lambda e, _b: e.entry_type[:7],
        sort_key=lambda e: e.entry_type,
    ),
    ColumnSpec(
        key="year",
        label="Year",
        name="Year",
        width=4,
        render=lambda e, _b: e.year[:4] if e.year else "",
        sort_key=lambda e: int(e.year) if e.year.isdigit() else 0,
    ),
    ColumnSpec(
        key="author",
        label="Author",
        name="Author",
        width=13,
        render=lambda e, _b: _truncate(e.authors_short, 13),
        sort_key=lambda e: e.authors_short.lower(),
    ),
    ColumnSpec(
        key="journal",
        label="Journal",
        name="Journal",
        width=17,
        render=lambda e, _b: _truncate(_journal_value(e), 17),
        sort_key=lambda e: _journal_value(e).lower(),
    ),
    ColumnSpec(
        key="title",
        label="Title",
        name="Title",
        width=30,
        render=lambda e, _b: e.title,
        sort_key=lambda e: e.title.lower(),
        flex=True,
    ),
    ColumnSpec(
        key="added",
        label="Added",
        name="Added",
        width=10,
        render=lambda e, _b: _date_added(e),
        sort_key=_date_added,
    ),
    ColumnSpec(
        key="rating",
        label="★",
        name="Rating",
        width=5,
        render=lambda e, _b: e.rating_stars,
        sort_key=lambda e: e.rating,
        dynamic=True,
    ),
)

BUILTIN_COLUMNS: dict[str, ColumnSpec] = {spec.key: spec for spec in _BUILTINS}

# The default column layout (and the "Reset to defaults" target). This is the
# historical set — the cite-key column is available to add but off by default.
DEFAULT_TABLE_COLUMNS: list[str] = [
    "state",
    "priority",
    "file",
    "url",
    "type",
    "year",
    "author",
    "journal",
    "title",
    "added",
    "rating",
]

# Field names already represented by a built-in column, or app-only metadata
# surfaced through the icon columns — never offered as generic field columns.
_FIELD_WIDTH = 15
_COVERED_BY_BUILTIN = {"title", "author", "year", "journal", "url", "file"}
_METADATA_FIELDS = {"readstatus", "ranking", "priority", *DATE_ADDED_KEYS}

# Content attributes on BibEntry that carry a real value worth scanning for.
_CONTENT_FIELDS = (
    "title",
    "author",
    "year",
    "journal",
    "doi",
    "url",
    "abstract",
    "keywords",
    "comment",
    "file",
)


def field_column_spec(name: str) -> ColumnSpec:
    """Build a generic column for an arbitrary BibTeX field name."""
    return ColumnSpec(
        key=name,
        label=name.capitalize(),
        name=name.capitalize(),
        width=_FIELD_WIDTH,
        render=lambda e, _b, _n=name: _truncate(e.get_field(_n), _FIELD_WIDTH),
        sort_key=lambda e, _n=name: e.get_field(_n).lower(),
    )


def spec_for(key: str) -> ColumnSpec:
    """Return the built-in spec for *key*, or a generic field spec."""
    return BUILTIN_COLUMNS.get(key) or field_column_spec(key)


def resolve_columns(keys: list[str] | None) -> list[ColumnSpec]:
    """Map stored column keys to specs; empty/None falls back to the default."""
    if not keys:
        keys = DEFAULT_TABLE_COLUMNS
    return [spec_for(key) for key in keys]


def discover_field_names(entries: list[BibEntry]) -> list[str]:
    """Return extra field names present in *entries*, excluding built-ins/metadata."""
    found: set[str] = set()
    for entry in entries:
        for name in _CONTENT_FIELDS:
            if entry.get_field(name):
                found.add(name)
        found.update(entry.raw_fields)
    # Drop anything a built-in column already shows (by internal name or key)
    # and app-only metadata, so no field is offered as a duplicate column.
    excluded = _COVERED_BY_BUILTIN | _METADATA_FIELDS | set(BUILTIN_COLUMNS)
    return sorted(found - excluded)


def available_columns(entries: list[BibEntry]) -> list[ColumnSpec]:
    """All columns offered in the control panel: built-ins then discovered fields."""
    specs = list(_BUILTINS)
    specs.extend(field_column_spec(name) for name in discover_field_names(entries))
    return specs
