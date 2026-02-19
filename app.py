from __future__ import annotations
import os
import platform
import subprocess
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header, Input, Label, Static
from textual.containers import Horizontal, Vertical
from textual import on, work
from textual.binding import Binding

from bib.models import BibEntry
from bib import parser
from utils.git import commit
from widgets.entry_list import EntryList
from widgets.entry_detail import EntryDetail
from widgets.modals import ConfirmModal, DOIModal, EditModal, RawEditModal, TagsModal


class BibTuiApp(App):
    """BibTeX TUI Application."""

    CSS_PATH = "bib_tui.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("s", "save", "Save"),
        Binding("e", "edit_entry", "Edit"),
        Binding("d", "doi_import", "From DOI"),
        Binding("o", "open_pdf", "Open PDF"),
        Binding("t", "edit_tags", "Tags"),
        Binding("r", "cycle_read_state", "Read state"),
        Binding("f,/", "focus_search", "Search"),
        Binding("1", "set_rating('1')", "★"),
        Binding("2", "set_rating('2')", "★★"),
        Binding("3", "set_rating('3')", "★★★"),
        Binding("4", "set_rating('4')", "★★★★"),
        Binding("5", "set_rating('5')", "★★★★★"),
        Binding("0", "set_rating('0')", "Clear ★"),
        Binding("v", "toggle_view", "Raw/Fmt"),
        Binding("escape", "clear_search", "Clear search", show=False),
    ]

    def __init__(self, bib_path: str, **kwargs):
        super().__init__(**kwargs)
        self._bib_path = bib_path
        self._entries: list[BibEntry] = []
        self._dirty = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-content"):
            yield EntryList([], id="entry-list")
            yield EntryDetail(id="entry-detail")
        yield Footer()

    def on_mount(self) -> None:
        self.title = f"bib-tui — {os.path.basename(self._bib_path)}"
        self._load_entries()

    def on_resize(self, event) -> None:
        self.query_one("#main-content").set_class(
            event.size.height > event.size.width, "vertical"
        )

    def _load_entries(self) -> None:
        self.notify("Loading bibliography...", timeout=2)
        try:
            self._entries = parser.load(self._bib_path)
            entry_list = self.query_one(EntryList)
            entry_list.refresh_entries(self._entries)
            self.notify(f"Loaded {len(self._entries)} entries.", timeout=3)
        except Exception as e:
            self.notify(f"Error loading file: {e}", severity="error")
        self.query_one(DataTable).focus()

    # ── Entry selection ────────────────────────────────────────────────────

    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        entry = self.query_one(EntryList).selected_entry
        self.query_one(EntryDetail).show_entry(entry)

    @on(DataTable.RowSelected)
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        entry = self.query_one(EntryList).selected_entry
        self.query_one(EntryDetail).show_entry(entry)

    # ── Actions ───────────────────────────────────────────────────────────

    def action_quit(self) -> None:
        if not self._dirty:
            self.exit()
            return
        self.push_screen(
            ConfirmModal("You have unsaved changes. Quit without saving?"),
            lambda confirmed: self.exit() if confirmed else None,
        )

    def action_focus_search(self) -> None:
        self.query_one("#search-input", Input).focus()

    def action_clear_search(self) -> None:
        search = self.query_one("#search-input", Input)
        if search.value:
            search.value = ""
            search.blur()
        else:
            search.blur()

    def action_save(self) -> None:
        try:
            parser.save(self._entries, self._bib_path)
            committed = commit(self._bib_path, "bib-tui: save bibliography")
            self._dirty = False
            msg = "Saved" + (" and committed to git." if committed else ".")
            self.notify(msg, timeout=3)
        except Exception as e:
            self.notify(f"Save failed: {e}", severity="error")

    def action_edit_entry(self) -> None:
        entry = self.query_one(EntryList).selected_entry
        if entry is None:
            self.notify("No entry selected.", severity="warning")
            return
        if self.query_one(EntryDetail).raw_mode:
            self.push_screen(RawEditModal(entry), self._on_edit_done)
        else:
            self.push_screen(EditModal(entry), self._on_edit_done)

    def _on_edit_done(self, result: BibEntry | None) -> None:
        if result is None:
            return
        # Update in master list
        for i, e in enumerate(self._entries):
            if e.key == result.key:
                self._entries[i] = result
                break
        self._dirty = True
        entry_list = self.query_one(EntryList)
        entry_list.refresh_entries(self._entries)
        self.query_one(EntryDetail).show_entry(result)
        self.notify("Entry updated. Press [s] to save.", timeout=3)

    def action_doi_import(self) -> None:
        self.push_screen(DOIModal(), self._on_doi_done)

    def _on_doi_done(self, result: BibEntry | None) -> None:
        if result is None:
            return
        # Check for duplicate key
        existing_keys = {e.key for e in self._entries}
        if result.key in existing_keys:
            result.key = result.key + "a"
        self._entries.append(result)
        self._dirty = True
        el = self.query_one(EntryList)
        el.refresh_entries(self._entries)
        # Jump cursor to the newly added entry
        try:
            idx = next(i for i, e in enumerate(el._filtered) if e.key == result.key)
            self.query_one(DataTable).move_cursor(row=idx)
            self.query_one(EntryDetail).show_entry(result)
        except StopIteration:
            pass
        self.notify(f"Added: {result.key}", timeout=3)

    def action_open_pdf(self) -> None:
        entry = self.query_one(EntryList).selected_entry
        if entry is None:
            self.notify("No entry selected.", severity="warning")
            return
        if not entry.file:
            self.notify("No PDF linked for this entry.", severity="warning")
            return
        path = entry.file
        # Handle BibDesk-style file field: {:path/to/file.pdf:PDF}
        if path.startswith("{") and ":" in path:
            parts = path.strip("{}").split(":")
            if len(parts) >= 2:
                path = parts[1]
        try:
            if platform.system() == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            self.notify(f"Could not open PDF: {e}", severity="error")

    def action_set_rating(self, value: str) -> None:
        entry = self.query_one(EntryList).selected_entry
        if entry is None:
            return
        try:
            rating = max(0, min(5, int(value)))
        except ValueError:
            return
        entry.rating = rating
        self._dirty = True
        self.query_one(EntryList).refresh_row(entry)
        self.query_one(EntryDetail).show_entry(entry)

    def action_cycle_read_state(self) -> None:
        entry = self.query_one(EntryList).selected_entry
        if entry is None:
            return
        entry.cycle_read_state()
        self._dirty = True
        self.query_one(EntryList).refresh_row(entry)
        self.query_one(EntryDetail).show_entry(entry)

    def action_toggle_view(self) -> None:
        self.query_one(EntryDetail).toggle_view()

    def action_edit_tags(self) -> None:
        entry = self.query_one(EntryList).selected_entry
        if entry is None:
            self.notify("No entry selected.", severity="warning")
            return
        self.push_screen(TagsModal(entry), self._on_tags_done)

    def _on_tags_done(self, result: list[str] | None) -> None:
        if result is None:
            return
        entry = self.query_one(EntryList).selected_entry
        if entry is None:
            return
        entry.tags = result
        self._dirty = True
        self.query_one(EntryDetail).show_entry(entry)
        self.notify("Tags updated. Press [s] to save.", timeout=3)
