import shlex

from rich.text import Text
from textual import events, on
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, Input, Static
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
    "r": "read_state",
    "state": "read_state",
    "read": "read_state",
    "pr": "priority",
    "priority": "priority",
    "urgency": "priority",
}


def _tokenize(query: str) -> list[str]:
    """Split a query string into whitespace-separated tokens, honoring quotes.

    ``shlex.split`` (with its default whitespace-splitting mode) lets
    ``k:"sea ice"`` keep its embedded space as one token's value while still
    leaving ``:`` untouched, so field prefixes are unaffected. An unbalanced
    quote — the normal state of things while the user is still typing —
    raises ``ValueError`` in shlex; fall back to a plain split rather than
    losing the query.
    """
    try:
        return shlex.split(query)
    except ValueError:
        return query.split()


def _parse_query(query: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Split a query into field filters and free-text terms.

    Each token is either ``prefix:value`` (field filter) or a plain word
    (searched across all fields). Multiple tokens are ANDed. The keyword
    ``AND`` (case-insensitive) is ignored, allowing queries like
    ``j:nature AND y:2025``.
    """
    filters: list[tuple[str, str]] = []
    free_terms: list[str] = []
    for token in _tokenize(query):
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


def _year_matches(entry_year: str, value: str) -> bool:
    """Match a ``y:`` filter value against an entry's year.

    Supports an exact/substring match (``2010``), a closed range
    (``2010-2020``), an open range (``2010-`` = 2010 or later, ``-2010`` = up
    to 2010), and comparisons (``>2010``, ``>=2010``, ``<2010``, ``<=2010``).
    A non-numeric entry year never satisfies a range or comparison — only
    the plain substring form can match it.
    """
    for op, op_len in ((">=", 2), ("<=", 2), (">", 1), ("<", 1)):
        if value.startswith(op):
            bound_str = value[op_len:]
            if not bound_str.isdigit() or not entry_year.isdigit():
                return False
            bound, year = int(bound_str), int(entry_year)
            if op == ">=":
                return year >= bound
            if op == "<=":
                return year <= bound
            if op == ">":
                return year > bound
            return year < bound

    if "-" in value:
        y_min_str, _, y_max_str = value.partition("-")
        if entry_year.isdigit():
            year = int(entry_year)
            try:
                if y_min_str and y_max_str:
                    return int(y_min_str) <= year <= int(y_max_str)
                if y_min_str:  # "2010-" → 2010 or later
                    return year >= int(y_min_str)
                if y_max_str:  # "-2010" → up to 2010
                    return year <= int(y_max_str)
            except ValueError:
                pass
        return value in entry_year

    return value in entry_year


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
            if not _year_matches(entry.year, value):
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
        elif field == "read_state":
            # Exact match, not substring: "read" and "to-read" are distinct
            # states and a substring match would conflate them.
            if value != entry.read_state.lower():
                return False
        elif field == "priority":
            if value != entry.priority_label.lower():
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


def matches_query(entry, query: str) -> bool:
    """Return whether *entry* matches a full query string.

    Thin wrapper around :func:`_parse_query` + :func:`_entry_matches` so
    saved filter presets (:mod:`bibtui.utils.filters`) and the live search
    box share exactly one implementation of the query syntax.
    """
    filters, free_terms = _parse_query(query)
    return _entry_matches(entry, filters, free_terms)


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
    """

    BORDER_TITLE = "Entries"

    search_text: reactive[str] = reactive("")

    _DEFAULT_SEARCH_PLACEHOLDER = "Search… (a:smith j:nature y:2025 k:ice c:smith2020)"

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
        # Saved filter preset layered underneath the live search box — see
        # `_apply_filters`. Empty name means no preset is active.
        self._preset_name: str = ""
        self._preset_query: str = ""

    def set_pdf_base_dir(self, base_dir: str) -> None:
        self._pdf_base_dir = base_dir

    def compose(self) -> ComposeResult:
        yield Static("", id="preset-bar")
        yield Input(
            placeholder=self._DEFAULT_SEARCH_PLACEHOLDER,
            id="search-input",
        )
        yield DataTable(id="entry-table", cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        self._add_columns(table)
        self._populate_table(self._all_entries)
        self._update_title_width()
        self._update_preset_bar()

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

    # ── Search & filter presets ──────────────────────────────────────────

    def _apply_filters(self) -> None:
        """Recompute visible rows: the active preset query, then the search box.

        The two layer as a plain AND — the preset narrows the library down
        to a working set (e.g. "Project X"), and the search box then
        refines further within it, exactly like typing two ANDed terms.
        """
        base = self._all_entries
        if self._preset_query:
            base = [e for e in base if matches_query(e, self._preset_query)]
        search = self.query_one(Input).value.strip()
        if search:
            base = [e for e in base if matches_query(e, search)]
        self._populate_table(base)
        if self._sort_key is not None:
            self._apply_sort()
        self._update_preset_bar()

    def _update_preset_bar(self) -> None:
        """Show/hide and refresh the one-line active-preset indicator."""
        bar = self.query_one("#preset-bar", Static)
        if not self._preset_name:
            bar.display = False
            return
        bar.display = True
        bar.update(
            f"Filter: [bold]{self._preset_name}[/bold]  "
            f"[dim]{self._preset_query}[/dim]  "
            f"{len(self._filtered)} / {len(self._all_entries)}"
        )

    def _update_search_placeholder(self) -> None:
        search = self.query_one(Input)
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
        return self.query_one(Input).value.strip()

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
