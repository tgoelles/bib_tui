from __future__ import annotations
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable, Input
from textual.reactive import reactive
from textual import on, events
from bib.models import BibEntry


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
        self._col_state = None
        self._col_rating = None

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search (title, author, tags)...", id="search-input")
        yield DataTable(id="entry-table", cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        # Store column keys so update_cell can find them reliably
        keys = table.add_columns("◉", "Type", "Year", "Author", "Title", "★")
        self._col_state, self._col_rating = keys[0], keys[5]
        table.tooltip = (
            "◉  Read state — [r] to cycle: ○ to-read → ◑ skimmed → ● read\n"
            "★  Rating — [1]–[5] to set, [0] to clear"
        )
        self._populate_table(self._all_entries)

    def _populate_table(self, entries: list[BibEntry]) -> None:
        table = self.query_one(DataTable)
        table.clear()
        self._filtered = entries
        for e in entries:
            table.add_row(
                e.read_state_icon,
                e.entry_type[:8],
                e.year[:4] if e.year else "",
                e.authors_short[:20],
                e.title[:55] + "…" if len(e.title) > 55 else e.title,
                e.rating_stars,
                key=e.key,
            )

    @on(Input.Changed, "#search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        query = event.value.lower()
        if not query:
            self._populate_table(self._all_entries)
        else:
            filtered = [
                e for e in self._all_entries
                if query in e.title.lower()
                or query in e.author.lower()
                or any(query in t.lower() for t in e.tags)
                or query in e.keywords.lower()
                or query in e.key.lower()
            ]
            self._populate_table(filtered)

    @on(Input.Submitted, "#search-input")
    def on_search_submitted(self, event: Input.Submitted) -> None:
        """Enter in search bar moves focus to the table."""
        self.query_one(DataTable).focus()

    def on_key(self, event: events.Key) -> None:
        table = self.query_one(DataTable)
        search = self.query_one(Input)
        focused = self.app.focused

        if focused is search:
            # Arrow keys while searching navigate the table without leaving search
            if event.key == "down":
                table.action_cursor_down()
                event.stop()
            elif event.key == "up":
                table.action_cursor_up()
                event.stop()
        elif focused is table:
            # Vim-style j/k navigation in the table
            if event.key == "j":
                table.action_cursor_down()
                event.stop()
            elif event.key == "k":
                table.action_cursor_up()
                event.stop()

    def refresh_entries(self, entries: list[BibEntry]) -> None:
        """Reload all entries (e.g. after add/edit)."""
        self._all_entries = entries
        search = self.query_one(Input).value
        if search:
            self.on_search_changed(Input.Changed(self.query_one(Input), search))
        else:
            self._populate_table(entries)

    def refresh_row(self, entry: BibEntry) -> None:
        """Update the read-state and rating cells for a single row."""
        table = self.query_one(DataTable)
        table.update_cell(entry.key, self._col_state, entry.read_state_icon, update_width=False)
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
