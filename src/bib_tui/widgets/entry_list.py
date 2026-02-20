from __future__ import annotations

import os

from rich.text import Text
from textual import events, on
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, Input
from textual.widgets._data_table import ColumnKey

from bib_tui.bib.models import PRIORITIES, READ_STATES, BibEntry
from bib_tui.utils.config import parse_jabref_path

# Original header labels in column order
_COL_LABELS = ("◉", "!", "◫", "◍", "Type", "Year", "Author", "Journal", "Title", "★")

# Sum of all fixed column widths + per-column padding (2 each) + EntryList border (2) + scrollbar (1).
# Fixed widths: ◉(1)+!(1)+◫(1)+⊕(1)+Type(7)+Year(4)+Author(13)+Journal(17)+★(5) = 50
# Padding: 10 cols × 2 = 20  |  border+scrollbar = 3
_COL_OVERHEAD = 73

_FIELD_PREFIXES: dict[str, str] = {
    "t": "title",
    "title": "title",
    "a": "author",
    "author": "author",
    "k": "keywords",
    "kw": "keywords",
    "keyword": "keywords",
    "keywords": "keywords",
    "y": "year",
    "year": "year",
    "u": "url",
    "url": "url",
}


def _parse_query(query: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Split a query into field filters and free-text terms.

    Each space-separated token is either ``prefix:value`` (field filter) or a
    plain word (searched across all fields).  Multiple tokens are ANDed.
    """
    filters: list[tuple[str, str]] = []
    free_terms: list[str] = []
    for token in query.split():
        if ":" in token:
            prefix, _, value = token.partition(":")
            field = _FIELD_PREFIXES.get(prefix.lower())
            if field and value:
                filters.append((field, value.lower()))
                continue
        free_terms.append(token.lower())
    return filters, free_terms


def _entry_matches(
    entry, filters: list[tuple[str, str]], free_terms: list[str]
) -> bool:
    for field, value in filters:
        if field == "title":
            if value not in entry.title.lower():
                return False
        elif field == "author":
            if value not in entry.author.lower():
                return False
        elif field == "keywords":
            if value not in entry.keywords.lower():
                return False
        elif field == "year":
            if "-" in value:
                # Range: y:2010-2020
                parts = value.split("-", 1)
                try:
                    y_min, y_max = int(parts[0]), int(parts[1])
                    y = int(entry.year) if entry.year.isdigit() else 0
                    if not (y_min <= y <= y_max):
                        return False
                except ValueError:
                    if value not in entry.year:
                        return False
            else:
                if value not in entry.year:
                    return False
        elif field == "url":
            if value not in entry.url.lower():
                return False
    for term in free_terms:
        if not (
            term in entry.title.lower()
            or term in entry.author.lower()
            or term in entry.keywords.lower()
            or term in entry.key.lower()
        ):
            return False
    return True


class EntryList(Widget):
    """Left pane: searchable DataTable of BibTeX entries."""

    DEFAULT_CSS = """
    EntryList {
        layout: vertical;
        height: 100%;
    }
    EntryList Input {
        height: 3;
    }
    EntryList DataTable {
        height: 1fr;
    }
    """

    BORDER_TITLE = "Entries"

    search_text: reactive[str] = reactive("")

    def __init__(self, entries: list[BibEntry], **kwargs):
        super().__init__(**kwargs)
        self._all_entries: list[BibEntry] = entries
        self._filtered: list[BibEntry] = list(entries)
        self._col_keys: tuple[ColumnKey, ...] = ()
        self._col_state: ColumnKey | None = None
        self._col_priority: ColumnKey | None = None
        self._col_file: ColumnKey | None = None
        self._col_url: ColumnKey | None = None
        self._col_title: ColumnKey | None = None
        self._col_rating: ColumnKey | None = None
        self._title_width: int = 30
        self._sort_key: ColumnKey | None = None
        self._sort_reverse: bool = False
        self._pdf_base_dir: str = ""

    def set_pdf_base_dir(self, base_dir: str) -> None:
        self._pdf_base_dir = base_dir

    def _file_icon(self, entry: BibEntry) -> str:
        if not entry.file:
            return " "
        path = parse_jabref_path(entry.file, self._pdf_base_dir)
        return "■" if os.path.exists(path) else "□"

    def compose(self) -> ComposeResult:
        yield Input(
            placeholder="Search… (a:smith t:glacier k:ice y:2020-2023)",
            id="search-input",
        )
        yield DataTable(id="entry-table", cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        col_state = table.add_column("◉", width=1)
        col_priority = table.add_column("!", width=1)
        col_file = table.add_column("◫", width=1)
        col_url = table.add_column("◍", width=1)
        col_type = table.add_column("Type", width=7)
        col_year = table.add_column("Year", width=4)
        col_author = table.add_column("Author", width=13)
        col_journal = table.add_column("Journal", width=17)
        col_title = table.add_column("Title", width=self._title_width)
        col_rating = table.add_column("★", width=5)
        self._col_keys = (
            col_state,
            col_priority,
            col_file,
            col_url,
            col_type,
            col_year,
            col_author,
            col_journal,
            col_title,
            col_rating,
        )
        self._col_state = col_state
        self._col_priority = col_priority
        self._col_file = col_file
        self._col_url = col_url
        self._col_title = col_title
        self._col_rating = col_rating
        self._populate_table(self._all_entries)

    def on_resize(self, event) -> None:
        self._update_title_width()

    def _update_title_width(self) -> None:
        """Recompute title column width to fill available horizontal space."""
        if self._col_title is None:
            return
        width = max(10, self.size.width - _COL_OVERHEAD)
        if width == self._title_width:
            return
        self._title_width = width
        table = self.query_one(DataTable)
        table.columns[self._col_title].width = width
        table.refresh()

    def _populate_table(self, entries: list[BibEntry]) -> None:
        table = self.query_one(DataTable)
        table.clear()
        self._filtered = entries
        for e in entries:
            journal = e.journal or e.raw_fields.get("booktitle", "")
            table.add_row(
                e.read_state_icon,
                e.priority_icon,
                self._file_icon(e),
                e.url_icon,
                e.entry_type[:7],
                e.year[:4] if e.year else "",
                e.authors_short[:12] + "…"
                if len(e.authors_short) > 12
                else e.authors_short,
                journal[:16] + "…" if len(journal) > 16 else journal,
                e.title,
                e.rating_stars,
                key=e.key,
            )

    # ── Sorting ───────────────────────────────────────────────────────────

    @on(DataTable.HeaderSelected)
    def on_header_selected(self, event: DataTable.HeaderSelected) -> None:
        col_key = event.column_key
        if self._sort_key == col_key:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_key = col_key
            self._sort_reverse = False
        self._apply_sort()
        self._update_header_labels()

    def _sort_fn(self, col_key: ColumnKey):
        """Return a key function for sorting BibEntry by the given column."""
        idx = list(self._col_keys).index(col_key)
        if idx == 0:  # ◉ read state
            return lambda e: (
                READ_STATES.index(e.read_state) if e.read_state in READ_STATES else 0
            )
        if idx == 1:  # ! priority
            return lambda e: e.priority if e.priority > 0 else 99
        if idx == 2:  # ◫ file
            return lambda e: 0 if e.file else 1
        if idx == 3:  # ⊕ url
            return lambda e: 0 if e.url else 1
        if idx == 4:  # Type
            return lambda e: e.entry_type
        if idx == 5:  # Year
            return lambda e: int(e.year) if e.year.isdigit() else 0
        if idx == 6:  # Author
            return lambda e: e.authors_short.lower()
        if idx == 7:  # Journal
            return lambda e: (e.journal or e.raw_fields.get("booktitle", "")).lower()
        if idx == 8:  # Title
            return lambda e: e.title.lower()
        if idx == 9:  # ★ rating
            return lambda e: e.rating
        return lambda e: ""

    def _apply_sort(self) -> None:
        if self._sort_key is None:
            return
        self._filtered = sorted(
            self._filtered,
            key=self._sort_fn(self._sort_key),
            reverse=self._sort_reverse,
        )
        # Rebuild the table rows in new order without re-fetching data
        table = self.query_one(DataTable)
        table.clear()
        for e in self._filtered:
            journal = e.journal or e.raw_fields.get("booktitle", "")
            table.add_row(
                e.read_state_icon,
                e.priority_icon,
                self._file_icon(e),
                e.url_icon,
                e.entry_type[:7],
                e.year[:4] if e.year else "",
                e.authors_short[:12] + "…"
                if len(e.authors_short) > 12
                else e.authors_short,
                journal[:16] + "…" if len(journal) > 16 else journal,
                e.title,
                e.rating_stars,
                key=e.key,
            )

    def _update_header_labels(self) -> None:
        """Put ▲/▼ on the active sort column, restore others."""
        table = self.query_one(DataTable)
        for key, label in zip(self._col_keys, _COL_LABELS):
            if key == self._sort_key:
                indicator = "▼" if self._sort_reverse else "▲"
                table.columns[key].label = Text(f"{label} {indicator}")
            else:
                table.columns[key].label = Text(label)
        table.refresh()

    # ── Search ────────────────────────────────────────────────────────────

    @on(Input.Changed, "#search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        query = event.value.strip()
        if not query:
            base = self._all_entries
        else:
            filters, free_terms = _parse_query(query)
            base = [
                e for e in self._all_entries if _entry_matches(e, filters, free_terms)
            ]
        self._populate_table(base)
        if self._sort_key is not None:
            self._apply_sort()

    @on(Input.Submitted, "#search-input")
    def on_search_submitted(self, event: Input.Submitted) -> None:
        """Enter in search bar moves focus to the table."""
        self.query_one(DataTable).focus()

    def on_key(self, event: events.Key) -> None:
        """Allow arrow keys to move the table cursor while search is focused."""
        table = self.query_one(DataTable)
        search = self.query_one(Input)
        if self.app.focused is search:
            if event.key == "down":
                table.action_cursor_down()
                event.stop()
            elif event.key == "up":
                table.action_cursor_up()
                event.stop()

    # ── Public helpers ────────────────────────────────────────────────────

    def refresh_entries(self, entries: list[BibEntry]) -> None:
        """Reload all entries (e.g. after add/edit)."""
        self._all_entries = entries
        search = self.query_one(Input).value
        if search:
            self.on_search_changed(Input.Changed(self.query_one(Input), search))
        else:
            self._populate_table(entries)
            if self._sort_key is not None:
                self._apply_sort()

    def refresh_row(self, entry: BibEntry) -> None:
        """Update the read-state, priority, file, and rating cells for a single row."""
        table = self.query_one(DataTable)
        table.update_cell(
            entry.key, self._col_state, entry.read_state_icon, update_width=False
        )
        table.update_cell(
            entry.key, self._col_priority, entry.priority_icon, update_width=False
        )
        table.update_cell(
            entry.key, self._col_file, self._file_icon(entry), update_width=False
        )
        table.update_cell(entry.key, self._col_url, entry.url_icon, update_width=False)
        table.update_cell(
            entry.key, self._col_rating, entry.rating_stars, update_width=False
        )

    @property
    def selected_entry(self) -> BibEntry | None:
        table = self.query_one(DataTable)
        if table.cursor_row < 0 or not self._filtered:
            return None
        if table.cursor_row >= len(self._filtered):
            return None
        return self._filtered[table.cursor_row]

    @property
    def filtered_entries(self) -> list[BibEntry]:
        return self._filtered
