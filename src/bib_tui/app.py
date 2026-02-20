from __future__ import annotations
import os
import platform
import subprocess
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header, Input, Label, Static, TextArea
from textual.containers import Horizontal, Vertical
from textual import events, on, work
from textual.binding import Binding
from textual.command import DiscoveryHit, Hit, Hits, Provider

from bib_tui.bib.models import BibEntry
from bib_tui.bib import parser
from bib_tui.utils.git import commit
from bib_tui.utils.config import Config, load_config, save_config, parse_jabref_path
from bib_tui.utils.theme import detect_theme
from bib_tui.widgets.entry_list import EntryList
from bib_tui.widgets.entry_detail import EntryDetail
from bib_tui.widgets.modals import ConfirmModal, DOIModal, EditModal, KeywordsModal, RawEditModal, SettingsModal


class SettingsProvider(Provider):
    """Exposes the Settings dialog through the command palette."""

    async def discover(self) -> Hits:
        yield DiscoveryHit("Settings", self.app.action_settings, help="Open the settings dialog")

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        score = matcher.match("Settings")
        if score > 0:
            yield Hit(score, matcher.highlight("Settings"), self.app.action_settings, help="Open the settings dialog")


class BibTuiApp(App):
    """BibTeX TUI Application."""

    COMMANDS = App.COMMANDS | {SettingsProvider}

    CSS_PATH = "bib_tui.tcss"

    BINDINGS = [
        # Core
        Binding("q", "quit", "Quit"),
        Binding("w", "save", "Write"),
        Binding("s", "focus_search", "Search"),
        Binding("e", "edit_entry", "Edit"),
        Binding("d", "doi_import", "From DOI"),
        Binding("k", "edit_keywords", "Keywords"),
        Binding("v", "toggle_view", "Raw/Fmt"),
        # Entry state
        Binding("r", "cycle_read_state", "Read state"),
        Binding("p", "cycle_priority", "Priority"),
        Binding("space", "open_pdf", "Open PDF"),
        # Rating
        Binding("0", "set_rating('0')", "Unrated"),
        Binding("1", "set_rating('1')", "★"),
        Binding("2", "set_rating('2')", "★★"),
        Binding("3", "set_rating('3')", "★★★"),
        Binding("4", "set_rating('4')", "★★★★"),
        Binding("5", "set_rating('5')", "★★★★★"),
        Binding("escape", "clear_search", "Clear search", show=False),
    ]

    def __init__(self, bib_path: str, **kwargs):
        super().__init__(**kwargs)
        self._bib_path = bib_path
        self._entries: list[BibEntry] = []
        self._dirty = False
        self._config: Config = load_config()

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-content"):
            yield EntryList([], id="entry-list")
            yield EntryDetail(id="entry-detail")
        yield Footer()

    def on_mount(self) -> None:
        self.theme = detect_theme()
        self.title = f"bib-tui — {os.path.basename(self._bib_path)}"
        self._load_entries()

    def on_resize(self, event) -> None:
        self.query_one("#main-content").set_class(
            event.size.width < event.size.height * 2, "vertical"
        )

    def on_paste(self, event: events.Paste) -> None:
        """Forward paste to whichever Input or TextArea currently has focus."""
        focused = self.focused
        if isinstance(focused, Input):
            focused.insert_text_at_cursor(event.text)
        elif isinstance(focused, TextArea):
            focused.insert(event.text)

    def _load_entries(self) -> None:
        self.notify("Loading bibliography...", timeout=2)
        try:
            self._entries = parser.load(self._bib_path)
            entry_list = self.query_one(EntryList)
            entry_list.set_pdf_base_dir(self._config.pdf_base_dir)
            self.query_one(EntryDetail).set_pdf_base_dir(self._config.pdf_base_dir)
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
            ConfirmModal("You have unwritten changes. Quit without writing?"),
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
            committed = commit(self._bib_path, "bib-tui: write bibliography")
            self._dirty = False
            msg = "Written" + (" and committed to git." if committed else ".")
            self.notify(msg, timeout=3)
        except Exception as e:
            self.notify(f"Write failed: {e}", severity="error")

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
        self.notify("Entry updated. Press [w] to write.", timeout=3)

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
        path = parse_jabref_path(entry.file, self._config.pdf_base_dir)
        if not os.path.exists(path):
            self.notify(f"PDF not found: {path}", severity="error", timeout=5)
            return
        try:
            if platform.system() == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            self.notify(f"Could not open PDF: {e}", severity="error", timeout=5)

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

    def action_cycle_priority(self) -> None:
        entry = self.query_one(EntryList).selected_entry
        if entry is None:
            return
        entry.cycle_priority()
        self._dirty = True
        self.query_one(EntryList).refresh_row(entry)
        self.query_one(EntryDetail).show_entry(entry)

    def action_settings(self) -> None:
        self.push_screen(SettingsModal(self._config), self._on_settings_done)

    def _on_settings_done(self, result: Config | None) -> None:
        if result is None:
            return
        self._config = result
        save_config(result)
        self.query_one(EntryList).set_pdf_base_dir(result.pdf_base_dir)
        self.query_one(EntryDetail).set_pdf_base_dir(result.pdf_base_dir)
        self.query_one(EntryList).refresh_entries(self._entries)
        self.notify("Settings written.", timeout=2)

    def action_toggle_view(self) -> None:
        self.query_one(EntryDetail).toggle_view()

    def action_edit_keywords(self) -> None:
        entry = self.query_one(EntryList).selected_entry
        if entry is None:
            self.notify("No entry selected.", severity="warning")
            return
        all_kws, kw_counts = self._all_keywords()
        self.push_screen(KeywordsModal(entry, all_kws, kw_counts), self._on_keywords_done)

    def _all_keywords(self) -> tuple[list[str], dict[str, int]]:
        """All unique keywords across the bib file, sorted by frequency descending."""
        from collections import Counter
        counter: Counter[str] = Counter()
        for e in self._entries:
            for kw in e.keywords_list:
                counter[kw] += 1
        return [kw for kw, _ in counter.most_common()], dict(counter)

    def _on_keywords_done(self, result: tuple[str, set[str]] | None) -> None:
        if result is None:
            return
        keywords_str, delete_everywhere = result
        entry = self.query_one(EntryList).selected_entry
        if entry is None:
            return
        entry.keywords = keywords_str
        if delete_everywhere:
            for e in self._entries:
                if e is not entry:
                    kept = [k for k in e.keywords_list if k not in delete_everywhere]
                    e.keywords = ", ".join(kept)
        self._dirty = True
        self.query_one(EntryList).refresh_entries(self._entries)
        self.query_one(EntryDetail).show_entry(entry)
        self.notify("Keywords updated. Press [w] to write.", timeout=3)
