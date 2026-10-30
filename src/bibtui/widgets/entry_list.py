from rich.text import Text
from textual import events, on
from textual.app import ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, Input, Static
from textual.widgets._data_table import ColumnKey

from bibtui.bib.models import BibEntry
from bibtui.bib.search import Matcher, QueryError, compile_query
from bibtui.widgets.columns import ColumnSpec, resolve_columns, spec_for

# Extra horizontal budget beyond the sum of fixed column widths: DataTable pads
# every cell (1 char each side) and the widget itself has a small border/gutter.
# Chosen so the default 11-column layout reproduces the historical title sizing.
_TITLE_PADDING = 2


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
    EntryList #preset-bar {
        height: 1;
        color: $accent;
        padding: 0 1;
    }
    EntryList #search-hint {
        height: 1;
        color: $error;
        padding: 0 1;
    }
    """

    BORDER_TITLE = "Entries"

    search_text: reactive[str] = reactive("")

    _DEFAULT_SEARCH_PLACEHOLDER = "Search… (a:smith j:nature y:2025 k:ice c:smith2020)"

    class SortChanged(Message):
        """The user picked a new sort by clicking a column header."""

        def __init__(self, column: str, reverse: bool) -> None:
            super().__init__()
            self.column = column
            self.reverse = reverse

    def __init__(
        self,
        entries: list[BibEntry],
        columns: list[str] | None = None,
        sort_column: str | None = None,
        sort_reverse: bool = False,
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
        # column reconfigure (the DataTable ColumnKey objects do not). It also
        # applies while its column is hidden — only the ▲/▼ marker needs the
        # column to be visible.
        self._sort_spec_key: str | None = sort_column or None
        self._sort_reverse: bool = sort_reverse
        self._pdf_base_dir: str = ""
        # Saved filter preset layered underneath the live search box — see
        # `_apply_filters`. Empty name means no preset is active.
        self._preset_name: str = ""
        self._preset_query: str = ""
        # The last search that parsed, kept on screen while the query in the
        # box is invalid (e.g. "a OR OR") so the list doesn't go empty.
        self._last_valid_search: Matcher | None = None
        self._preset_invalid = False

    def set_pdf_base_dir(self, base_dir: str) -> None:
        self._pdf_base_dir = base_dir

    def compose(self) -> ComposeResult:
        yield Static("", id="preset-bar")
        yield Input(
            placeholder=self._DEFAULT_SEARCH_PLACEHOLDER,
            id="search-input",
        )
        yield Static("", id="search-hint")
        yield DataTable(id="entry-table", cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        self._add_columns(table)
        self._apply_filters()
        self._update_header_labels()
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
        self._apply_sort()
        self._update_header_labels()
        self.post_message(self.SortChanged(spec_key, self._sort_reverse))

    def _sorted(self, entries: list[BibEntry]) -> list[BibEntry]:
        """*entries* in the active sort order, or unchanged if nothing is sorted."""
        if self._sort_spec_key is None:
            return entries
        spec = next(
            (s for s in self._specs if s.key == self._sort_spec_key),
            None,
        ) or spec_for(self._sort_spec_key)
        return sorted(entries, key=spec.sort_key, reverse=self._sort_reverse)

    def _apply_sort(self) -> None:
        """Reorder the rows already on screen, without re-filtering."""
        self._populate_table(self._sorted(self._filtered))

    def _update_header_labels(self) -> None:
        """Put ▲/▼ on the active sort column, restore others."""
        table = self.query_one(DataTable)
        for key, spec in zip(self._col_keys, self._specs):
            if spec.key == self._sort_spec_key:
                indicator = "▼" if self._sort_reverse else "▲"
                table.columns[key].label = Text(f"{spec.label} {indicator}")
            else:
                table.columns[key].label = Text(spec.label)
        table.refresh()

    # ── Search & filter presets ──────────────────────────────────────────

    def _apply_filters(self) -> None:
        """Recompute visible rows: the active preset query, then the search box.

        The two layer as a plain AND — the preset narrows the library down
        to a working set (e.g. "Project X"), and the search box then
        refines further within it, exactly like typing two ANDed terms.
        """
        base = self._all_entries
        self._preset_invalid = False
        if self._preset_query:
            try:
                preset = compile_query(self._preset_query)
            except QueryError:
                # A filter saved before the query syntax changed; the filter
                # bar says so, and nothing matches until it's edited.
                self._preset_invalid = True
                base = []
            else:
                base = [e for e in base if preset(e)]

        hint = self.query_one("#search-hint", Static)
        hint.display = False
        search = self.query_one("#search-input", Input).value.strip()
        matcher: Matcher | None = None
        if search:
            try:
                matcher = compile_query(search)
            except QueryError as error:
                matcher = self._last_valid_search
                hint.update(f"Invalid query: {error}. Showing the last valid result.")
                hint.display = True
            else:
                self._last_valid_search = matcher
        else:
            self._last_valid_search = None
        if matcher is not None:
            base = [e for e in base if matcher(e)]
        self._populate_table(self._sorted(base))
        self._update_preset_bar()

    def _update_preset_bar(self) -> None:
        """Show/hide and refresh the one-line active-preset indicator."""
        bar = self.query_one("#preset-bar", Static)
        if not self._preset_name:
            bar.display = False
            return
        bar.display = True
        status = (
            "[$error]invalid query, edit it with f → e[/]"
            if self._preset_invalid
            else f"{len(self._filtered)} / {len(self._all_entries)}"
        )
        bar.update(
            f"Filter: [bold]{self._preset_name}[/bold]  "
            f"[dim]{self._preset_query}[/dim]  {status}"
        )

    def _update_search_placeholder(self) -> None:
        search = self.query_one("#search-input", Input)
        search.placeholder = (
            f"Search within {self._preset_name}…"
            if self._preset_name
            else self._DEFAULT_SEARCH_PLACEHOLDER
        )

    @on(Input.Changed, "#search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        self._apply_filters()

    @on(Input.Submitted, "#search-input")
    def on_search_submitted(self, event: Input.Submitted) -> None:
        """Enter in search bar moves focus to the table."""
        self.query_one(DataTable).focus()

    def on_key(self, event: events.Key) -> None:
        """Allow arrow keys to move the table cursor while search is focused."""
        table = self.query_one(DataTable)
        search = self.query_one("#search-input", Input)
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
        self._reload_rows()
        self._update_header_labels()
        self._title_width = -1  # force a recompute on the new column set
        self._update_title_width()
        self._restore_cursor(table, selected_key)

    def _reload_rows(self) -> None:
        """Repopulate rows honoring the active preset, search filter and sort."""
        self._apply_filters()

    def set_preset(self, name: str, query: str) -> None:
        """Activate a saved filter preset, or clear it when *name* is empty."""
        selected_before = self.selected_entry
        selected_key = selected_before.key if selected_before is not None else None
        self._preset_name = name
        self._preset_query = query if name else ""
        self._update_search_placeholder()
        self._apply_filters()
        self._restore_cursor(self.query_one(DataTable), selected_key)

    @property
    def active_preset(self) -> tuple[str, str]:
        """The active preset as ``(name, query)``; ``("", "")`` when none is active."""
        return self._preset_name, self._preset_query

    @property
    def search_query(self) -> str:
        return self.query_one("#search-input", Input).value.strip()

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
