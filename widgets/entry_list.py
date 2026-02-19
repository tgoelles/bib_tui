from __future__ import annotations
from rich.text import Text
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable, Input
from textual.widgets._data_table import ColumnKey
from textual.reactive import reactive
from textual import on, events
from bib.models import BibEntry, READ_STATES

# Original header labels in column order
_COL_LABELS = ("◉", "◫", "Type", "Year", "Author", "Journal", "Title", "★")


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
        self._col_rating: ColumnKey | None = None
        self._sort_key: ColumnKey | None = None
        self._sort_reverse: bool = False

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search (title, author, tags)...", id="search-input")
        yield DataTable(id="entry-table", cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        non_rating_keys = list(table.add_columns(*_COL_LABELS[:-1]))
        rating_key = table.add_column("★", width=5)
        self._col_keys = tuple(non_rating_keys) + (rating_key,)
        self._col_state = self._col_keys[0]
        self._col_file = self._col_keys[1]
        self._col_rating = self._col_keys[7]
        self._populate_table(self._all_entries)

    def _populate_table(self, entries: list[BibEntry]) -> None:
        table = self.query_one(DataTable)
        table.clear()
        self._filtered = entries
        for e in entries:
            journal = e.journal or e.raw_fields.get("booktitle", "")
            table.add_row(
                e.read_state_icon,
                e.file_icon,
                e.entry_type[:8],
                e.year[:4] if e.year else "",
                e.authors_short[:20],
                journal[:22] + "…" if len(journal) > 22 else journal,
                e.title[:35] + "…" if len(e.title) > 35 else e.title,
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
        if idx == 0:   # ◉ read state
            return lambda e: READ_STATES.index(e.read_state) if e.read_state in READ_STATES else 0
        if idx == 1:   # ▪ file
            return lambda e: (0 if e.file else 1)
        if idx == 2:   # Type
            return lambda e: e.entry_type
        if idx == 3:   # Year
            return lambda e: int(e.year) if e.year.isdigit() else 0
        if idx == 4:   # Author
            return lambda e: e.authors_short.lower()
        if idx == 5:   # Journal
            return lambda e: (e.journal or e.raw_fields.get("booktitle", "")).lower()
        if idx == 6:   # Title
            return lambda e: e.title.lower()
        if idx == 7:   # ★ rating
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
                e.file_icon,
                e.entry_type[:8],
                e.year[:4] if e.year else "",
                e.authors_short[:20],
                journal[:22] + "…" if len(journal) > 22 else journal,
                e.title[:35] + "…" if len(e.title) > 35 else e.title,
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
        query = event.value.lower()
        if not query:
            base = self._all_entries
        else:
            base = [
                e for e in self._all_entries
                if query in e.title.lower()
                or query in e.author.lower()
                or any(query in t.lower() for t in e.tags)
                or query in e.keywords.lower()
                or query in e.key.lower()
            ]
        self._populate_table(base)
        if self._sort_key is not None:
            self._apply_sort()

    @on(Input.Submitted, "#search-input")
    def on_search_submitted(self, event: Input.Submitted) -> None:
        """Enter in search bar moves focus to the table."""
        self.query_one(DataTable).focus()

    def on_key(self, event: events.Key) -> None:
        table = self.query_one(DataTable)
        search = self.query_one(Input)
        focused = self.app.focused

        if focused is search:
            if event.key == "down":
                table.action_cursor_down()
                event.stop()
            elif event.key == "up":
                table.action_cursor_up()
                event.stop()
        elif focused is table:
            if event.key == "j":
                table.action_cursor_down()
                event.stop()
            elif event.key == "k":
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
        """Update the read-state, file, and rating cells for a single row."""
        table = self.query_one(DataTable)
        table.update_cell(entry.key, self._col_state, entry.read_state_icon, update_width=False)
        table.update_cell(entry.key, self._col_file, entry.file_icon, update_width=False)
        table.update_cell(entry.key, self._col_rating, entry.rating_stars, update_width=False)

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
