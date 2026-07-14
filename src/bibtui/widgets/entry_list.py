from rich.text import Text
from textual import events, on
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, Input
from textual.widgets._data_table import ColumnKey

from bibtui.bib.models import BibEntry
from bibtui.widgets.columns import ColumnSpec, resolve_columns

# Extra horizontal budget beyond the sum of fixed column widths: DataTable pads
# every cell (1 char each side) and the widget itself has a small border/gutter.
# Chosen so the default 11-column layout reproduces the historical title sizing.
_TITLE_PADDING = 2

_FIELD_PREFIXES: dict[str, str] = {
    "t": "title",
    "title": "title",
    "a": "author",
    "author": "author",
    "j": "journal",
    "journal": "journal",
    "k": "keywords",
    "kw": "keywords",
    "keyword": "keywords",
    "keywords": "keywords",
    "y": "year",
    "year": "year",
    "u": "url",
    "url": "url",
    "c": "citekey",
    "citekey": "citekey",
    "key": "citekey",
}


def _parse_query(query: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Split a query into field filters and free-text terms.

    Each space-separated token is either ``prefix:value`` (field filter) or a
    plain word (searched across all fields).  Multiple tokens are ANDed.
    The keyword ``AND`` (case-insensitive) is ignored, allowing queries like
    ``j:nature AND y:2025``.
    """
    filters: list[tuple[str, str]] = []
    free_terms: list[str] = []
    for token in query.split():
        if token.upper() == "AND":
            continue
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
        elif field == "journal":
            journal = (entry.journal or entry.raw_fields.get("booktitle", "")).lower()
            if value not in journal:
                return False
        elif field == "url":
            if value not in entry.url.lower():
                return False
        elif field == "citekey":
            if value not in entry.key.lower():
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
    """Left pane: searchable DataTable of BibTeX entries.

    The visible columns and their order are driven entirely by a list of
    :class:`~bibtui.widgets.columns.ColumnSpec` (``self._specs``) resolved from
    the user's saved configuration, so column layout is data rather than logic
    duplicated across methods.
    """

    ALLOW_MAXIMIZE = True

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

    def __init__(
        self,
        entries: list[BibEntry],
        columns: list[str] | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._all_entries: list[BibEntry] = entries
        self._filtered: list[BibEntry] = list(entries)
        self._specs: list[ColumnSpec] = resolve_columns(columns)
        self._col_keys: tuple[ColumnKey, ...] = ()
        self._col_keys_by_key: dict[str, ColumnKey] = {}
        self._title_width: int = 30
        # Sort is tracked by the column's stable spec key so it survives a
        # column reconfigure (the DataTable ColumnKey objects do not).
        self._sort_key: ColumnKey | None = None
        self._sort_spec_key: str | None = None
        self._sort_reverse: bool = False
        self._pdf_base_dir: str = ""

    def set_pdf_base_dir(self, base_dir: str) -> None:
        self._pdf_base_dir = base_dir

    def compose(self) -> ComposeResult:
        yield Input(
            placeholder="Search… (a:smith j:nature y:2025 k:ice c:smith2020)",
            id="search-input",
        )
        yield DataTable(id="entry-table", cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        self._add_columns(table)
        self._populate_table(self._all_entries)
        self._update_title_width()

    def _add_columns(self, table: DataTable) -> None:
        """(Re)create the DataTable columns from ``self._specs``."""
        keys: list[ColumnKey] = []
        self._col_keys_by_key = {}
        for spec in self._specs:
            col_key = table.add_column(spec.label, width=spec.width)
            keys.append(col_key)
            self._col_keys_by_key[spec.key] = col_key
        self._col_keys = tuple(keys)

    def _row_for_entry(self, entry: BibEntry) -> list[str]:
        """Render one table row as cell values, one per active column."""
        return [spec.render(entry, self._pdf_base_dir) for spec in self._specs]

    def on_resize(self, event) -> None:
        self._update_title_width()

    def _update_title_width(self) -> None:
        """Size the flex (Title) column to fill the remaining horizontal space."""
        flex_idx = next((i for i, s in enumerate(self._specs) if s.flex), None)
        if flex_idx is None:
            return
        table = self.query_one(DataTable)
        fixed = sum(s.width for i, s in enumerate(self._specs) if i != flex_idx)
        overhead = fixed + 2 * len(self._specs) + _TITLE_PADDING
        width = max(10, self.size.width - overhead)
        if width == self._title_width:
            return
        self._title_width = width
        table.columns[self._col_keys[flex_idx]].width = width
        table.refresh()

    def _populate_table(self, entries: list[BibEntry]) -> None:
        table = self.query_one(DataTable)
        table.clear()
        self._filtered = entries
        for e in entries:
            table.add_row(*self._row_for_entry(e), key=e.key)

    # ── Sorting ───────────────────────────────────────────────────────────

    @on(DataTable.HeaderSelected)
    def on_header_selected(self, event: DataTable.HeaderSelected) -> None:
        idx = self._col_keys.index(event.column_key)
        spec_key = self._specs[idx].key
        if self._sort_spec_key == spec_key:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_spec_key = spec_key
            self._sort_reverse = False
        self._sort_key = event.column_key
        self._apply_sort()
        self._update_header_labels()

    def _sort_fn(self, col_key: ColumnKey):
        """Return the sort-key function for the column identified by *col_key*."""
        idx = self._col_keys.index(col_key)
        return self._specs[idx].sort_key

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
            table.add_row(*self._row_for_entry(e), key=e.key)

    def _update_header_labels(self) -> None:
        """Put ▲/▼ on the active sort column, restore others."""
        table = self.query_one(DataTable)
        for key, spec in zip(self._col_keys, self._specs):
            if key == self._sort_key:
                indicator = "▼" if self._sort_reverse else "▲"
                table.columns[key].label = Text(f"{spec.label} {indicator}")
            else:
                table.columns[key].label = Text(spec.label)
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

    def set_columns(self, keys: list[str]) -> None:
        """Rebuild the table with a new column layout, preserving data & sort."""
        selected_before = self.selected_entry
        selected_key = selected_before.key if selected_before is not None else None
        self._specs = resolve_columns(keys)
        table = self.query_one(DataTable)
        table.clear(columns=True)
        self._add_columns(table)
        # Restore the active sort only if that column is still present.
        self._sort_key = (
            self._col_keys_by_key.get(self._sort_spec_key)
            if self._sort_spec_key
            else None
        )
        if self._sort_key is None:
            self._sort_spec_key = None
        self._reload_rows()
        if self._sort_key is not None:
            self._update_header_labels()
        self._title_width = -1  # force a recompute on the new column set
        self._update_title_width()
        self._restore_cursor(table, selected_key)

    def _reload_rows(self) -> None:
        """Repopulate rows honoring the current search filter and sort."""
        search = self.query_one(Input).value.strip()
        if search:
            self.on_search_changed(Input.Changed(self.query_one(Input), search))
        else:
            self._populate_table(self._all_entries)
            if self._sort_key is not None:
                self._apply_sort()

    def _restore_cursor(self, table: DataTable, selected_key: str | None) -> None:
        if selected_key is None:
            return
        try:
            row_idx = next(
                i for i, e in enumerate(self._filtered) if e.key == selected_key
            )
        except StopIteration:
            return
        table.move_cursor(row=row_idx)

    def refresh_entries(self, entries: list[BibEntry]) -> None:
        """Reload all entries (e.g. after add/edit)."""
        table = self.query_one(DataTable)
        selected_before = self.selected_entry
        selected_key = selected_before.key if selected_before is not None else None
        self._all_entries = entries
        self._reload_rows()
        self._restore_cursor(table, selected_key)

    def refresh_row(self, entry: BibEntry) -> None:
        """Update the in-place (dynamic) cells for a single row."""
        table = self.query_one(DataTable)
        for spec in self._specs:
            if not spec.dynamic:
                continue
            table.update_cell(
                entry.key,
                self._col_keys_by_key[spec.key],
                spec.render(entry, self._pdf_base_dir),
                update_width=False,
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
