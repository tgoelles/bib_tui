import os
import platform
import subprocess
import webbrowser
from urllib.parse import urlparse

from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import DiscoveryHit, Hit, Hits, Provider
from textual.containers import Horizontal
from textual.widgets import DataTable, Footer, Header, Input, TextArea

from bibtui.bib import parser
from bibtui.bib.models import BibEntry
from bibtui.utils.config import (
    CONFIG_PATH,
    Config,
    is_first_run,
    load_config,
    parse_jabref_path,
    save_config,
)
from bibtui.utils.theme import detect_theme
from bibtui.widgets.entry_detail import EntryDetail
from bibtui.widgets.entry_list import EntryList
from bibtui.widgets.modals import (
    AddPDFModal,
    ConfirmModal,
    DOIModal,
    EditModal,
    FetchPDFModal,
    FirstRunModal,
    HelpModal,
    KeywordsModal,
    PasteModal,
    RawEditModal,
    SettingsModal,
)


class SettingsProvider(Provider):
    """Exposes the Settings dialog through the command palette."""

    async def discover(self) -> Hits:
        yield DiscoveryHit(
            "Settings", self.app.action_settings, help="Open the settings dialog"
        )

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        score = matcher.match("Settings")
        if score > 0:
            yield Hit(
                score,
                matcher.highlight("Settings"),
                self.app.action_settings,
                help="Open the settings dialog",
            )


class BibTuiApp(App):
    """BibTeX TUI Application."""

    COMMANDS = App.COMMANDS | {SettingsProvider}

    CSS_PATH = "bibtui.tcss"

    BINDINGS = [
        # Core
        Binding("q", "quit", "Quit"),
        Binding("w", "save", "Write"),
        Binding("s", "focus_search", "Search"),
        Binding("e", "edit_entry", "Edit"),
        Binding("d", "doi_import", "From DOI"),
        Binding("k", "edit_keywords", "Keywords"),
        Binding("v", "toggle_view", "View"),
        # Entry state
        Binding("r", "cycle_read_state", "State"),
        Binding("p", "cycle_priority", "Prio"),
        Binding("space", "open_pdf", "␣ Show PDF"),
        Binding("b", "open_url", "Browser"),
        Binding("f", "fetch_pdf", "Fetch PDF"),
        Binding("a", "add_pdf", "Add PDF"),
        # Rating (hidden from footer)
        Binding("0", "set_rating('0')", "Unrated", show=False),
        Binding("1", "set_rating('1')", "★", show=False),
        Binding("2", "set_rating('2')", "★★", show=False),
        Binding("3", "set_rating('3')", "★★★", show=False),
        Binding("4", "set_rating('4')", "★★★★", show=False),
        Binding("5", "set_rating('5')", "★★★★★", show=False),
        # Copy
        Binding("ctrl+c", "copy_key", "Copy key", show=False, priority=True),
        # Delete
        Binding("delete", "delete_entry", "Delete", show=False),
        Binding("backspace", "delete_entry", "Delete", show=False),
        # Help
        Binding("?", "show_help", "Help"),
        Binding("escape", "clear_search", "Clear search", show=False),
    ]

    def __init__(self, bib_path: str, **kwargs):
        super().__init__(**kwargs)
        self._bib_path = bib_path
        self._entries: list[BibEntry] = []
        self._dirty = False
        self._first_run = is_first_run()
        self._config: Config = load_config()

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-content"):
            yield EntryList([], id="entry-list")
            yield EntryDetail(id="entry-detail")
        yield Footer()

    def on_mount(self) -> None:
        self.theme = detect_theme()
        self.title = f"bibtui — {os.path.basename(self._bib_path)}"
        self._load_entries()
        if self._first_run:
            self.call_after_refresh(self._show_first_run)

    def on_resize(self, event) -> None:
        self.query_one("#main-content").set_class(
            event.size.width < event.size.height * 2, "vertical"
        )

    def on_paste(self, event: events.Paste) -> None:
        """Forward paste to a focused Input/TextArea, or open PasteModal for BibTeX text."""
        focused = self.focused
        if isinstance(focused, Input):
            focused.insert_text_at_cursor(event.text)
            return
        if isinstance(focused, TextArea):
            focused.insert(event.text)
            return
        # No text widget focused — intercept BibTeX-shaped pastes
        if event.text.strip().startswith("@"):
            event.stop()
            self.push_screen(PasteModal(event.text.strip()), self._on_paste_done)

    def _load_entries(self) -> None:
        self.notify("Loading bibliography...", timeout=2)
        try:
            import shutil as _shutil

            bak = self._bib_path + ".bak"
            if not os.path.exists(bak):
                _shutil.copy2(self._bib_path, bak)
        except Exception:
            pass  # Missing file or permission error — silently skip backup
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
            self._dirty = False
            self.notify("Written.", timeout=3)
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

    def action_paste_import(self) -> None:
        self.push_screen(PasteModal(), self._on_paste_done)

    def _on_paste_done(self, result: BibEntry | None) -> None:
        if result is None:
            return
        existing_keys = {e.key for e in self._entries}
        if result.key in existing_keys:
            self.notify(
                f"BibTeX key '{result.key}' already exists, cannot proceed.",
                severity="error",
                timeout=5,
            )
            return
        self._entries.append(result)
        self._dirty = True
        el = self.query_one(EntryList)
        el.refresh_entries(self._entries)
        try:
            idx = next(i for i, e in enumerate(el._filtered) if e.key == result.key)
            self.query_one(DataTable).move_cursor(row=idx)
            self.query_one(EntryDetail).show_entry(result)
        except StopIteration:
            pass
        self.notify(f"Added: {result.key}", timeout=3)
        self._maybe_auto_fetch(result)

    def action_doi_import(self) -> None:
        self.push_screen(DOIModal(), self._on_doi_done)

    def action_delete_entry(self) -> None:
        entry = self.query_one(EntryList).selected_entry
        if entry is None:
            self.notify("No entry selected.", severity="warning")
            return
        self.push_screen(
            ConfirmModal(
                f"Delete entry [bold]{entry.key}[/bold]?\nThis cannot be undone."
            ),
            lambda confirmed: self._do_delete_entry(entry.key) if confirmed else None,
        )

    def _do_delete_entry(self, key: str) -> None:
        self._entries = [e for e in self._entries if e.key != key]
        self._dirty = True
        el = self.query_one(EntryList)
        el.refresh_entries(self._entries)
        self.query_one(EntryDetail).show_entry(el.selected_entry)
        self.notify(f"Deleted: {key}", timeout=3)

    def _on_doi_done(self, result: BibEntry | None) -> None:
        if result is None:
            return
        existing_keys = {e.key for e in self._entries}
        if result.key in existing_keys:
            self.notify(
                f"BibTeX key '{result.key}' already exists, cannot proceed.",
                severity="error",
                timeout=5,
            )
            return
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
        self._maybe_auto_fetch(result)

    def _maybe_auto_fetch(self, entry: BibEntry) -> None:
        """Trigger PDF fetch after import if the setting is enabled and prerequisites are met."""
        if not self._config.auto_fetch_pdf:
            return
        if not (entry.doi or entry.url):
            return
        if not self._config.pdf_base_dir:
            return
        self._do_fetch_pdf(entry, True)

    def action_open_url(self) -> None:
        entry = self.query_one(EntryList).selected_entry
        if entry is None:
            self.notify("No entry selected.", severity="warning")
            return
        url = entry.url
        if not url:
            self.notify("No URL for this entry.", severity="warning")
            return
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            self.notify(f"Invalid URL: {url}", severity="error", timeout=5)
            return
        webbrowser.open(url)
        self.notify(f"Opening: {url[:60]}", timeout=3)

    def action_fetch_pdf(self) -> None:
        entry = self.query_one(EntryList).selected_entry
        if entry is None:
            self.notify("No entry selected.", severity="warning")
            return
        if not entry.doi and not entry.url:
            self.notify(
                "Entry has no DOI or URL — cannot fetch PDF.",
                severity="warning",
            )
            return
        dest_dir = self._config.pdf_base_dir
        if not dest_dir:
            self.notify(
                "PDF base directory not set. Open Settings (Ctrl+P → Settings).",
                severity="warning",
            )
            return
        from bibtui.bib.pdf_fetcher import pdf_filename

        dest_path = os.path.join(dest_dir, pdf_filename(entry))
        if os.path.exists(dest_path):
            self.push_screen(
                ConfirmModal(f"PDF already exists:\n{dest_path}\n\nOverwrite?"),
                lambda confirmed: self._do_fetch_pdf(entry, confirmed),
            )
        else:
            self._do_fetch_pdf(entry, True)

    def _do_fetch_pdf(self, entry: BibEntry, confirmed: bool) -> None:
        if not confirmed:
            return
        self.push_screen(
            FetchPDFModal(
                entry,
                self._config.pdf_base_dir,
                self._config.unpaywall_email,
            ),
            self._on_fetch_pdf_done,
        )

    def _on_fetch_pdf_done(self, result: str | None) -> None:
        if result is None:
            return
        entry = self.query_one(EntryList).selected_entry
        if entry is None:
            return
        from bibtui.utils.config import format_jabref_path

        entry.file = format_jabref_path(result, self._config.pdf_base_dir)
        self._dirty = True
        self.query_one(EntryList).refresh_row(entry)
        self.query_one(EntryDetail).show_entry(entry)
        self.notify(f"PDF saved and linked: {entry.key}", timeout=4)

    def action_add_pdf(self) -> None:
        entry = self.query_one(EntryList).selected_entry
        if entry is None:
            self.notify("No entry selected.", severity="warning")
            return
        dest_dir = self._config.pdf_base_dir
        if not dest_dir:
            self.notify(
                "PDF base directory not set. Open Settings (Ctrl+P → Settings).",
                severity="warning",
            )
            return
        self.push_screen(
            AddPDFModal(entry, dest_dir, self._config.pdf_download_dir),
            self._on_add_pdf_done,
        )

    def _on_add_pdf_done(self, result: str | None) -> None:
        if result is None:
            return
        entry = self.query_one(EntryList).selected_entry
        if entry is None:
            return
        from bibtui.utils.config import format_jabref_path

        entry.file = format_jabref_path(result, self._config.pdf_base_dir)
        self._dirty = True
        self.query_one(EntryList).refresh_row(entry)
        self.query_one(EntryDetail).show_entry(entry)
        self.notify(f"PDF added and linked: {entry.key}", timeout=4)

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

    def _show_first_run(self) -> None:
        def _after_welcome(open_settings: bool) -> None:
            # Always persist an empty config so this modal never appears again.
            if not CONFIG_PATH.exists():
                save_config(self._config)
            if open_settings:
                self.push_screen(SettingsModal(self._config), self._on_settings_done)

        self.push_screen(FirstRunModal(), _after_welcome)

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

    def action_show_help(self) -> None:
        self.push_screen(HelpModal())

    def action_copy_key(self) -> None:
        entry = self.query_one(EntryList).selected_entry
        if entry is None:
            return
        self.copy_to_clipboard(entry.key)
        self.notify(f"Copied: {entry.key}", timeout=2)

    def action_edit_keywords(self) -> None:
        entry = self.query_one(EntryList).selected_entry
        if entry is None:
            self.notify("No entry selected.", severity="warning")
            return
        all_kws, kw_counts = self._all_keywords()
        self.push_screen(
            KeywordsModal(entry, all_kws, kw_counts), self._on_keywords_done
        )

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
