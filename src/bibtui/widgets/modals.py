from textual import events, on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Input,
    Label,
    ListItem,
    ListView,
    LoadingIndicator,
    SelectionList,
    Static,
    Switch,
    TextArea,
)
from textual.widgets._selection_list import Selection

from bibtui.bib.models import BibEntry
from bibtui.bib.parser import bibtex_str_to_entry, entry_to_bibtex_str
from bibtui.utils.config import Config


def _format_age(mtime: float) -> str:
    """Human-readable age string for a file modification time."""
    import time

    age = time.time() - mtime
    if age < 60:
        return "just now"
    if age < 3600:
        return f"{int(age / 60)} min ago"
    if age < 86400:
        return f"{int(age / 3600)} hr ago"
    return f"{int(age / 86400)} days ago"


class ConfirmModal(ModalScreen[bool]):
    """Generic yes/no confirmation dialog."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    DEFAULT_CSS = """
    ConfirmModal {
        align: center middle;
    }
    ConfirmModal > Vertical {
        width: 50;
        height: auto;
        border: double $warning;
        background: $surface;
        padding: 1 2;
    }
    ConfirmModal #btn-yes {
        background: $error;
        color: $text;
    }
    ConfirmModal #btn-no {
        background: $primary;
        color: $text;
    }
    """

    def __init__(self, message: str, **kwargs):
        super().__init__(**kwargs)
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]Confirm[/bold]", classes="modal-title")
            yield Static(self._message)
            with Horizontal(classes="modal-buttons"):
                yield Button("Yes", id="btn-yes")
                yield Button("No", id="btn-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-yes")

    def action_cancel(self) -> None:
        self.dismiss(False)


class LibraryFetchConfirmModal(ModalScreen[tuple[bool, bool] | None]):
    """Confirm library PDF fetch and choose whether broken links may be overwritten."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    DEFAULT_CSS = """
    LibraryFetchConfirmModal {
        align: center middle;
    }
    LibraryFetchConfirmModal > Vertical {
        width: 50;
        height: auto;
        border: double $accent;
        background: $surface;
        padding: 1 2;
    }
    LibraryFetchConfirmModal #overwrite-row {
        layout: horizontal;
        align: left middle;
        margin: 1 0;
        height: 3;
    }
    LibraryFetchConfirmModal #overwrite-switch {
        margin-right: 1;
    }
    LibraryFetchConfirmModal #library-fetch-note {
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]Fetch Missing PDFs[/bold]", classes="modal-title")
            yield Static("Run fetch for entries missing local PDFs?")
            with Horizontal(id="overwrite-row"):
                yield Switch(value=True, id="overwrite-switch")
                yield Label("Overwrite broken links")
            yield Static(
                "Turn off to keep entries with broken file paths untouched.",
                id="library-fetch-note",
            )
            with Horizontal(classes="modal-buttons"):
                yield Button("Start", variant="primary", id="btn-start")
                yield Button("Cancel", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
            return
        overwrite = self.query_one("#overwrite-switch", Switch).value
        self.dismiss((True, overwrite))

    def action_cancel(self) -> None:
        self.dismiss(None)


class DOIModal(ModalScreen[BibEntry | None]):
    """Modal to fetch an entry by DOI."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    DOIModal {
        align: center middle;
    }
    DOIModal > Vertical {
        width: 70;
        height: auto;
        border: double $accent;
        background: $surface;
        padding: 1 2;
    }
    #doi-status.fetching { color: $warning; }
    #doi-status.success  { color: $success; }
    #doi-status.error    { color: $error; }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]Entry from DOI[/bold]", classes="modal-title")
            yield Input(
                placeholder="Enter DOI (e.g. 10.1038/nature12345)", id="doi-input"
            )
            yield Static("", id="doi-status")
            with Horizontal(classes="modal-buttons"):
                yield Button("Fetch", variant="primary", id="btn-fetch")
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        self.call_after_refresh(self.query_one("#doi-input", Input).focus)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-fetch":
            self._do_fetch()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._do_fetch()

    def _do_fetch(self) -> None:
        doi = self.query_one("#doi-input", Input).value.strip()
        if not doi:
            return
        status = self.query_one("#doi-status", Static)
        status.set_classes("fetching")
        status.update("Fetching…")
        self._fetch_doi(doi)

    @work(thread=True)
    def _fetch_doi(self, doi: str) -> None:
        try:
            from bibtui.bib.doi import fetch_by_doi

            entry = fetch_by_doi(doi)
            self.app.call_from_thread(self._on_fetch_success, entry)
        except Exception as e:  # noqa: BLE001
            self.app.call_from_thread(self._on_fetch_error, str(e))

    def _on_fetch_success(self, entry: BibEntry) -> None:
        status = self.query_one("#doi-status", Static)
        status.set_classes("success")
        status.update(f"Found: {entry.title[:60]}")
        self.app.call_later(self._confirm, entry)

    def _on_fetch_error(self, message: str) -> None:
        status = self.query_one("#doi-status", Static)
        status.set_classes("error")
        status.update(f"Error: {message}")

    def _confirm(self, entry: BibEntry) -> None:
        self.dismiss(entry)

    def action_cancel(self) -> None:
        self.dismiss(None)


class EditModal(ModalScreen[BibEntry | None]):
    """Modal to edit key fields of an entry."""

    BINDINGS = [
        Binding("ctrl+s", "save_and_close", "Write", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    EditModal {
        align: center middle;
    }
    EditModal > Vertical {
        width: 80;
        height: auto;
        max-height: 92%;
        border: double $accent;
        background: $surface;
        padding: 1 2;
    }
    EditModal #edit-fields {
        height: 22;
    }
    EditModal Input {
        margin-bottom: 1;
    }
    EditModal Label {
        color: $accent;
    }
    EditModal TextArea {
        height: 6;
        margin-bottom: 1;
    }
    """

    def __init__(self, entry: BibEntry, **kwargs):
        super().__init__(**kwargs)
        self._entry = entry

    def compose(self) -> ComposeResult:
        e = self._entry
        with Vertical():
            yield Label(
                f"[bold]Edit Entry[/bold]  [dim]{e.key}[/dim]", classes="modal-title"
            )
            with VerticalScroll(id="edit-fields"):
                yield Label("Title")
                yield Input(value=e.title, id="edit-title")
                yield Label("Author")
                yield Input(value=e.author, id="edit-author")
                yield Label("Year")
                yield Input(value=e.year, id="edit-year")
                yield Label("Journal / Booktitle")
                yield Input(value=e.journal, id="edit-journal")
                yield Label("DOI")
                yield Input(value=e.doi, id="edit-doi")
                yield Label("Keywords")
                yield Input(value=e.keywords, id="edit-keywords")
                yield Label("PDF file path")
                yield Input(value=e.file, id="edit-file")
                yield Label("Abstract")
                yield TextArea(e.abstract, id="edit-abstract")
                yield Label("Comment")
                yield TextArea(e.comment, id="edit-comment")
            with Horizontal(classes="modal-buttons"):
                yield Button("Write", variant="primary", id="btn-save")
                yield Button("Cancel", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-save":
            self._save()

    def on_input_submitted(self, _: Input.Submitted) -> None:
        self._save()

    def _save(self) -> None:
        e = self._entry

        def v(widget_id: str) -> str:
            return self.query_one(widget_id, Input).value

        e.title = v("#edit-title")
        e.author = v("#edit-author")
        e.year = v("#edit-year")
        e.journal = v("#edit-journal")
        e.doi = v("#edit-doi")
        e.keywords = v("#edit-keywords")
        e.file = v("#edit-file")
        e.abstract = self.query_one("#edit-abstract", TextArea).text
        e.comment = self.query_one("#edit-comment", TextArea).text
        self.dismiss(e)

    def action_save_and_close(self) -> None:
        self._save()

    def action_cancel(self) -> None:
        self.dismiss(None)


class KeywordsModal(ModalScreen["tuple[str, set[str]] | None"]):
    """Keyword picker: select from all bib-wide keywords, add new ones."""

    BINDINGS = [
        Binding("ctrl+s", "save", "Write", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    KeywordsModal {
        align: center middle;
    }
    KeywordsModal > Vertical {
        width: 70;
        height: 80%;
        border: double $accent;
        background: $surface;
        padding: 1 2;
    }
    KeywordsModal #kw-filter {
        margin-bottom: 1;
    }
    KeywordsModal SelectionList {
        height: 1fr;
        border: solid $panel;
    }
    KeywordsModal #kw-hints {
        height: auto;
        margin-top: 1;
        color: $text-muted;
    }
    """

    def __init__(
        self,
        entry: BibEntry,
        all_keywords: list[str],
        keyword_counts: dict[str, int],
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._all_keywords = list(all_keywords)
        self._selected: set[str] = set(entry.keywords_list)
        self._shown: list[str] = []
        self._keyword_counts = keyword_counts
        self._delete_everywhere: set[str] = set()

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]Edit Keywords[/bold]", classes="modal-title")
            yield Input(
                placeholder="Filter or type new keyword + Enter to add…", id="kw-filter"
            )
            yield SelectionList(id="kw-list")
            yield Static(
                "[dim]Esc close · Enter add new  |  ↓/↑ navigate · Space toggle · ⌫ delete everywhere[/dim]",
                id="kw-hints",
            )
            with Horizontal(classes="modal-buttons"):
                yield Button("Write", variant="primary", id="btn-save")
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        self._rebuild_list("")
        self.call_after_refresh(self.query_one("#kw-filter", Input).focus)

    def on_key(self, event: events.Key) -> None:
        sl = self.query_one(SelectionList)
        kw_filter = self.query_one("#kw-filter", Input)
        if self.focused is kw_filter and event.key == "down":
            sl.focus()
            event.stop()
        elif self.focused is sl and event.key == "up" and sl.highlighted == 0:
            kw_filter.focus()
            event.stop()
        elif self.focused is sl and event.key == "backspace":
            self._delete_highlighted()
            event.stop()

    def _delete_highlighted(self) -> None:
        sl = self.query_one(SelectionList)
        highlighted = sl.highlighted
        if highlighted is None or highlighted >= len(self._shown):
            return
        kw = self._shown[highlighted]
        count = self._keyword_counts.get(kw, 0)
        noun = "entry" if count == 1 else "entries"
        msg = f"Remove '[bold]{kw}[/bold]' from all {count} {noun}?"
        self.app.push_screen(
            ConfirmModal(msg),
            lambda confirmed: self._on_delete_confirmed(confirmed, kw),
        )

    def _on_delete_confirmed(self, confirmed: bool | None, kw: str) -> None:
        if not confirmed:
            return
        self._delete_everywhere.add(kw)
        self._selected.discard(kw)
        if kw in self._all_keywords:
            self._all_keywords.remove(kw)
        filter_val = self.query_one("#kw-filter", Input).value
        self._rebuild_list(filter_val)

    def _sync_from_list(self) -> None:
        """Pull current checkbox state into self._selected."""
        sl = self.query_one(SelectionList)
        selected_now = set(sl.selected)
        for kw in self._shown:
            if kw in selected_now:
                self._selected.add(kw)
            else:
                self._selected.discard(kw)

    def _rebuild_list(self, filter_text: str) -> None:
        f = filter_text.lower()
        # Always show selected keywords first, then filtered rest
        selected_shown = sorted(kw for kw in self._selected if not f or f in kw.lower())
        rest = [
            kw
            for kw in self._all_keywords
            if kw not in self._selected and (not f or f in kw.lower())
        ]
        self._shown = selected_shown + rest
        sl = self.query_one(SelectionList)
        sl.clear_options()
        for kw in self._shown:
            sl.add_option(Selection(kw, kw, kw in self._selected))

    @on(Input.Changed, "#kw-filter")
    def on_filter_changed(self, event: Input.Changed) -> None:
        self._sync_from_list()
        self._rebuild_list(event.value)

    @on(Input.Submitted, "#kw-filter")
    def on_filter_submitted(self, event: Input.Submitted) -> None:
        kw = event.value.strip()
        if not kw:
            self.query_one(SelectionList).focus()
            return
        self._sync_from_list()
        if kw not in self._all_keywords:
            self._all_keywords.insert(0, kw)
        self._selected.add(kw)
        self.query_one("#kw-filter", Input).clear()
        self._rebuild_list("")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-save":
            self._save()

    def _save(self) -> None:
        self._sync_from_list()
        # Preserve original order from all_keywords, then any extras
        ordered = [kw for kw in self._all_keywords if kw in self._selected]
        self.dismiss((", ".join(ordered), self._delete_everywhere))

    def action_save(self) -> None:
        self._save()

    def action_cancel(self) -> None:
        self.dismiss(None)


class SettingsModal(ModalScreen["Config | None"]):
    """Settings dialog — currently just the PDF base directory."""

    BINDINGS = [
        Binding("ctrl+s", "save", "Write", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    SettingsModal {
        align: center middle;
    }
    SettingsModal > Vertical {
        width: 70;
        height: auto;
        border: double $accent;
        background: $surface;
        padding: 1 2;
    }
    SettingsModal Input {
        margin-bottom: 1;
    }
    SettingsModal .setting-row {
        height: auto;
        align: left middle;
        margin-bottom: 1;
    }
    SettingsModal .setting-row Label {
        width: 1fr;
    }
    """

    def __init__(self, config: Config, **kwargs):
        super().__init__(**kwargs)
        self._config = config

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]Settings[/bold]", classes="modal-title")
            yield Label("PDF base directory")
            yield Static(
                "[dim]Filenames in the file field are resolved relative to this path.[/dim]"
            )
            yield Input(
                value=self._config.pdf_base_dir,
                placeholder="/home/user/Papers",
                id="pdf-base-dir",
            )
            yield Static("")

            yield Label("Unpaywall email")
            yield Static(
                "[dim]Used for open-access PDF lookup via Unpaywall — no registration needed.[/dim]"
            )
            yield Input(
                value=self._config.unpaywall_email,
                placeholder="me@example.com",
                id="unpaywall-email",
            )
            yield Static("")

            yield Label("PDF download directory")
            yield Static(
                "[dim]PDFs listed when you press [bold]a[/bold] to add an existing PDF. Defaults to ~/Downloads.[/dim]"
            )
            yield Input(
                value=self._config.pdf_download_dir,
                placeholder=str(__import__("pathlib").Path.home() / "Downloads"),
                id="pdf-download-dir",
            )
            yield Static("")

            yield Label("Auto-fetch PDF on import")
            yield Static(
                "[dim]Automatically fetch the PDF after importing an entry by DOI or paste.[/dim]"
            )
            with Horizontal(classes="setting-row"):
                yield Switch(value=self._config.auto_fetch_pdf, id="auto-fetch-pdf")
            yield Static("")

            yield Label("Check for updates on startup")
            yield Static(
                "[dim]Checks PyPI at most once per day in the background and notifies when a newer stable release is available.[/dim]"
            )
            with Horizontal(classes="setting-row"):
                yield Switch(
                    value=self._config.check_for_updates, id="check-for-updates"
                )

            with Horizontal(classes="modal-buttons"):
                yield Button("Write", variant="primary", id="btn-save")
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        self.call_after_refresh(self.query_one("#pdf-base-dir", Input).focus)

    def _collect(self) -> None:
        self._config.pdf_base_dir = self.query_one("#pdf-base-dir", Input).value.strip()
        self._config.unpaywall_email = self.query_one(
            "#unpaywall-email", Input
        ).value.strip()
        self._config.pdf_download_dir = self.query_one(
            "#pdf-download-dir", Input
        ).value.strip()
        self._config.auto_fetch_pdf = self.query_one("#auto-fetch-pdf", Switch).value
        self._config.check_for_updates = self.query_one(
            "#check-for-updates", Switch
        ).value

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-save":
            self._collect()
            self.dismiss(self._config)

    def on_input_submitted(self, _: Input.Submitted) -> None:
        self._collect()
        self.dismiss(self._config)

    def action_save(self) -> None:
        self._collect()
        self.dismiss(self._config)

    def action_cancel(self) -> None:
        self.dismiss(None)


class HelpModal(ModalScreen[None]):
    """Keybinding reference overlay."""

    BINDINGS = [
        Binding("escape", "dismiss_help", "Close", show=False),
        Binding("?", "dismiss_help", "Close", show=False),
    ]
    DEFAULT_CSS = """
    HelpModal { align: center middle; }
    HelpModal > Vertical {
        width: 74; height: 80%;
        border: double $accent; background: $surface; padding: 1 2;
    }
    HelpModal VerticalScroll { height: 1fr; }
    HelpModal #help-about { margin-bottom: 1; color: $text-muted; }
    """

    def _make_about(self) -> str:
        try:
            from bibtui import __version__

            version = __version__
        except Exception:
            version = "unknown"
        return (
            f"[bold]bibtui[/bold] v{version}  —  BibTeX TUI\n"
            "[dim]Author:[/dim] Thomas Gölles\n"
            "[dim]Web:[/dim] https://thomasgoelles.com\n"
            "[dim]Repo:[/dim]   https://github.com/tgoelles/bib_tui"
        )

    _KEYS = """\
[bold]── Core ──────────────────────────────[/bold]
  [bold]q[/bold]         Quit
  [bold]w[/bold]         Write
  [bold]s[/bold]         Search
  [bold]e[/bold]         Edit entry (field form or raw BibTeX)
  [bold]k[/bold]         Edit keywords
    [bold]m[/bold]         Maximize/restore table pane
    [dim]Press m again to restore split view.[/dim]
  [bold]v[/bold]         Toggle raw / formatted view

[bold]── Add new entry ─────────────────────[/bold]
  [bold]d[/bold]         Import entry by DOI (fetches metadata online)
  [bold]ctrl+v[/bold]    Paste a raw BibTeX entry from clipboard
  [dim]Both methods reject duplicate cite keys.[/dim]

[bold]── Delete entry ──────────────────────[/bold]
  [bold]Del / ⌫[/bold]   Delete the selected entry (confirmation required)

[bold]── Keywords modal ────────────────────[/bold]
  [bold]Enter[/bold]     Add typed keyword
  [bold]Space[/bold]     Toggle selected keyword on/off
  [bold]⌫[/bold]         Delete highlighted keyword from all entries
  [bold]↓ / ↑[/bold]     Move between filter and list

[bold]── Entry state ───────────────────────[/bold]
  [bold]r[/bold]         Cycle read state
  [bold]p[/bold]         Cycle priority
  [bold]␣[/bold]         Show PDF
  [bold]b[/bold]         Open URL in browser (validates http/https)
    [bold]Shift+b[/bold]   Search OpenAlex (title first, then DOI)
  [bold]f[/bold]         Fetch PDF and link it to the entry
  [bold]a[/bold]         Add an existing PDF to the library and link it

[bold]── Fetch PDF ─────────────────────────[/bold]
  Sources tried in order:
  [bold]1.[/bold] arXiv      — arXiv DOI or arxiv.org URL
  [bold]2.[/bold] Unpaywall  — OA by DOI (set email in Ctrl+P)
  [bold]3.[/bold] Direct URL — entry URL pointing to a PDF
  PDF saved to base directory from Settings.
  [dim]Some publishers block automated downloads.[/dim]

[bold]── Library actions ───────────────────[/bold]
    [bold]ctrl+p[/bold]    Open command palette
    [bold]Library: Fetch missing PDFs[/bold]
    [dim]Shows a toggle for: Overwrite broken links.[/dim]
    [bold]Library: Unify citekeys (AuthorYear)[/bold]
    [dim]Entries already matching AuthorYear are left unchanged.[/dim]
    [dim]Changing citekeys may break existing LaTeX documents.[/dim]

[bold]── Rating ────────────────────────────[/bold]
  [bold]1 – 5[/bold]     Set star rating
  [bold]0[/bold]         Mark unrated

[bold]── Other ─────────────────────────────[/bold]
    [bold]ctrl+c[/bold]    Copy selected text (or cite key if none focused)
  [bold]?[/bold]         Show this help
    [bold]ctrl+p[/bold]    Command palette (Settings + Library actions)
        [bold]maximize[/bold]  (palette) maximize focused pane
  [bold]Esc[/bold]       Clear search / close modal
  [dim]  Clipboard uses OSC 52 — requires a modern terminal[/dim]
  [dim]  In all modals: Ctrl+S = Write/Save, Esc = Cancel[/dim]

[bold]── Sorting ───────────────────────────[/bold]
  Click any column header to sort by that column.
  Click the same header again to reverse the order.
  Active sort column is marked with [bold]▲[/bold] (asc) or [bold]▼[/bold] (desc).
    Cols: [bold]◉[/bold] state  [bold]![/bold] prio  [bold]◫[/bold] PDF  [bold]🔗[/bold] URL  Type  Year  Author  Journal  Title  Added  [bold]★[/bold]
"""
    _SEARCH = """\
[bold]── Plain text ────────────────────────[/bold]
  Searches title, author, keywords, and key.
  Multiple tokens are ANDed (AND keyword optional).

[bold]── Field prefixes ────────────────────[/bold]
  [bold]a:[/bold] / [bold]author:[/bold]    filter by author
  [bold]t:[/bold] / [bold]title:[/bold]     filter by title
  [bold]j:[/bold] / [bold]journal:[/bold]   filter by journal
  [bold]k:[/bold] / [bold]kw:[/bold]        filter by keyword
  [bold]y:[/bold] / [bold]year:[/bold]      filter by year or range
  [bold]u:[/bold] / [bold]url:[/bold]       filter by URL
  [bold]c:[/bold] / [bold]citekey:[/bold]   filter by cite key

[bold]── Examples ──────────────────────────[/bold]
  [dim]glacier[/dim]                    all fields
  [dim]a:smith t:glacier[/dim]          combined
  [dim]j:nature AND y:2025[/dim]        journal + year
  [dim]y:2015-2023[/dim]                year range
  [dim]k:ice a:jones[/dim]              keyword + author
  [dim]c:smith2020[/dim]                exact cite key search"""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]Help[/bold]", classes="modal-title")
            with VerticalScroll():
                yield Static(self._make_about(), id="help-about")
                yield Label("[bold]Keybindings[/bold]", classes="modal-title")
                yield Static(self._KEYS)
                yield Label("[bold]Search syntax[/bold]", classes="modal-title")
                yield Static(self._SEARCH)
            with Horizontal(classes="modal-buttons"):
                yield Button("Close", variant="primary", id="btn-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()

    def action_dismiss_help(self) -> None:
        self.dismiss()


class RawEditModal(ModalScreen[BibEntry | None]):
    """Edit a BibTeX entry as raw text."""

    BINDINGS = [
        Binding("ctrl+s", "save", "Write", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    RawEditModal {
        align: center middle;
    }
    RawEditModal > Vertical {
        width: 90;
        height: 40;
        border: double $accent;
        background: $surface;
        padding: 1 2;
    }
    RawEditModal TextArea {
        height: 1fr;
    }
    #raw-edit-error {
        color: $error;
    }
    """

    def __init__(self, entry: BibEntry, **kwargs):
        super().__init__(**kwargs)
        self._entry = entry

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(
                f"[bold]Edit Raw BibTeX[/bold]  [dim]{self._entry.key}[/dim]",
                classes="modal-title",
            )
            yield TextArea(
                entry_to_bibtex_str(self._entry),
                id="raw-edit-area",
            )
            yield Static("", id="raw-edit-error")
            with Horizontal(classes="modal-buttons"):
                yield Button("Write", variant="primary", id="btn-save")
                yield Button("Cancel", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-save":
            self._save()

    def _save(self) -> None:
        text = self.query_one("#raw-edit-area", TextArea).text
        error = self.query_one("#raw-edit-error", Static)
        try:
            entry = bibtex_str_to_entry(text)
            self.dismiss(entry)
        except Exception as e:
            error.update(f"Parse error: {e}")

    def action_save(self) -> None:
        self._save()

    def action_cancel(self) -> None:
        self.dismiss(None)


class PasteModal(ModalScreen["BibEntry | None"]):
    """Modal to import a BibTeX entry from pasted clipboard text."""

    BINDINGS = [
        Binding("ctrl+s", "do_import", "Import", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    PasteModal {
        align: center middle;
    }
    PasteModal > Vertical {
        width: 90;
        height: 40;
        border: double $accent;
        background: $surface;
        padding: 1 2;
    }
    PasteModal TextArea {
        height: 1fr;
    }
    #paste-error {
        color: $error;
    }
    """

    def __init__(self, text: str = "", **kwargs):
        super().__init__(**kwargs)
        self._text = text

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]Paste BibTeX Entry[/bold]", classes="modal-title")
            yield TextArea(
                self._text,
                id="paste-area",
            )
            yield Static("", id="paste-error")
            with Horizontal(classes="modal-buttons"):
                yield Button("Import", variant="primary", id="btn-save")
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        self.call_after_refresh(self.query_one("#paste-area", TextArea).focus)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-save":
            self._do_import()

    def _do_import(self) -> None:
        text = self.query_one("#paste-area", TextArea).text
        error = self.query_one("#paste-error", Static)
        error.update("")
        try:
            entry = bibtex_str_to_entry(text)
            self.dismiss(entry)
        except Exception as e:
            error.update(f"Parse error: {e}")

    def action_do_import(self) -> None:
        self._do_import()

    def action_cancel(self) -> None:
        self.dismiss(None)


class AddPDFModal(ModalScreen["str | None"]):
    """Pick an existing PDF from the download directory, filter by name, and link it."""

    BINDINGS = [
        Binding("ctrl+s", "add", "Add", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    AddPDFModal {
        align: center middle;
    }
    AddPDFModal > Vertical {
        width: 80;
        height: 30;
        border: double $accent;
        background: $surface;
        padding: 1 2;
    }
    AddPDFModal Input {
        margin-bottom: 1;
    }
    AddPDFModal ListView {
        height: 1fr;
        border: solid $panel;
        margin-bottom: 1;
    }
    AddPDFModal #add-hint {
        color: $text-muted;
        margin-bottom: 1;
    }
    AddPDFModal #add-preview-hint {
        color: $text-muted;
        height: auto;
        margin-bottom: 1;
    }
    AddPDFModal #add-error {
        color: $error;
    }
    """

    def __init__(
        self,
        entry: BibEntry,
        base_dir: str,
        download_dir: str,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._entry = entry
        self._base_dir = base_dir
        from pathlib import Path

        self._download_dir = download_dir or str(Path.home() / "Downloads")
        self._all_pdfs: list = []
        self._filtered: list = []

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(
                f"[bold]Add PDF[/bold]  [dim]{self._entry.key}[/dim]",
                classes="modal-title",
            )
            yield Static("", id="add-hint")
            yield Input(placeholder="type to filter…", id="add-filter")
            yield ListView(id="add-list")
            yield Static(
                "[dim]↓/↑ navigate · Space preview [/dim]",
                id="add-preview-hint",
            )
            yield Static("", id="add-error")
            with Horizontal(classes="modal-buttons"):
                yield Button("Add", variant="primary", id="btn-add")
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        self._scan()
        self.call_after_refresh(self.query_one("#add-filter", Input).focus)

    def _scan(self) -> None:
        from pathlib import Path

        dl = Path(self._download_dir).expanduser()
        hint = self.query_one("#add-hint", Static)
        if not dl.is_dir():
            hint.update(
                f"[dim]Download dir not found: {dl}  ·  enter a path manually[/dim]"
            )
            self._all_pdfs = []
        else:
            pdfs = sorted(
                dl.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True
            )
            self._all_pdfs = pdfs
            hint.update(
                f"[dim]{dl}  ·  {len(pdfs)} PDF{'s' if len(pdfs) != 1 else ''}[/dim]"
            )
        self._filtered = list(self._all_pdfs)
        self._refresh_list()

    def _refresh_list(self) -> None:
        lv = self.query_one(ListView)
        lv.clear()
        for p in self._filtered:
            stat = p.stat()
            size = stat.st_size
            size_str = (
                f"{size / 1048576:.1f} MB"
                if size >= 1048576
                else f"{size / 1024:.0f} KB"
            )
            age = _format_age(stat.st_mtime)
            lv.append(ListItem(Label(f"{p.name}  [dim]{size_str}  {age}[/dim]")))

    @on(Input.Changed, "#add-filter")
    def _on_filter(self, event: Input.Changed) -> None:
        q = event.value.strip().lower()
        self._filtered = (
            [p for p in self._all_pdfs if q in p.name.lower()]
            if q
            else list(self._all_pdfs)
        )
        self._refresh_list()

    def on_key(self, event: events.Key) -> None:
        """Down in the Input moves focus to the list; Up from the first item returns focus."""
        lv = self.query_one(ListView)
        inp = self.query_one("#add-filter", Input)
        if self.focused is inp and event.key == "down" and self._filtered:
            lv.focus()
            event.stop()
        elif self.focused is lv and event.key == "up" and (lv.index or 0) == 0:
            inp.focus()
            event.stop()
        elif self.focused is lv and event.key == "space":
            self._preview_selected()
            event.stop()

    def _preview_selected(self) -> None:
        import platform
        import subprocess

        lv = self.query_one(ListView)
        idx = lv.index
        if idx is None or idx >= len(self._filtered):
            return
        path = self._filtered[idx]
        try:
            if platform.system() == "Darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:
            self.query_one("#add-error", Static).update(f"Could not open: {e}")

    @on(Input.Submitted, "#add-filter")
    def _on_filter_submitted(self, _: Input.Submitted) -> None:
        self._confirm()

    @on(ListView.Selected)
    def _on_list_selected(self, event: ListView.Selected) -> None:
        idx = self.query_one(ListView).index
        if idx is not None and idx < len(self._filtered):
            self._add_path(self._filtered[idx])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-add":
            self._confirm()

    def _confirm(self) -> None:
        from pathlib import Path

        lv = self.query_one(ListView)
        idx = lv.index
        if self._filtered and idx is not None and idx < len(self._filtered):
            self._add_path(self._filtered[idx])
        else:
            # Fallback: treat the filter text as a custom path
            val = self.query_one("#add-filter", Input).value.strip()
            if val:
                self._add_path(Path(val))
            else:
                self.query_one("#add-error", Static).update(
                    "Select a file or enter a path."
                )

    def _add_path(self, src) -> None:
        from pathlib import Path

        from bibtui.pdf.fetcher import FetchError, add_pdf

        error = self.query_one("#add-error", Static)
        error.update("")
        try:
            dest = add_pdf(Path(src), self._entry, self._base_dir)
            self.dismiss(str(dest))
        except FetchError as exc:
            error.update(str(exc))

    def action_add(self) -> None:
        self._confirm()

    def action_cancel(self) -> None:
        self.dismiss(None)


class FetchPDFModal(ModalScreen["str | None"]):
    """Fetch a PDF for an entry in a background thread and show progress."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    DEFAULT_CSS = """
    FetchPDFModal {
        align: center middle;
    }
    FetchPDFModal > Vertical {
        width: 70;
        height: auto;
        border: double $accent;
        background: $surface;
        padding: 1 2;
    }
    FetchPDFModal LoadingIndicator {
        height: 3;
    }
    FetchPDFModal #fetch-status {
        margin-top: 1;
        margin-bottom: 1;
        color: $text;
    }
    FetchPDFModal #fetch-status.success {
        color: $success;
    }
    FetchPDFModal #fetch-status.error {
        color: $error;
    }
    """

    def __init__(
        self,
        entry: BibEntry,
        dest_dir: str,
        unpaywall_email: str = "",
        overwrite: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._entry = entry
        self._dest_dir = dest_dir
        self._email = unpaywall_email
        self._overwrite = overwrite
        self._saved_path: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(
                f"[bold]Fetch PDF[/bold]  [dim]{self._entry.key}[/dim]",
                classes="modal-title",
            )
            yield LoadingIndicator(id="fetch-loading")
            yield Static("", id="fetch-status")
            with Horizontal(classes="modal-buttons"):
                yield Button("Close", variant="primary", id="btn-close", disabled=True)
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        self._do_fetch()

    @work(thread=True)
    def _do_fetch(self) -> None:
        from bibtui.pdf.fetcher import FetchError, fetch_pdf

        try:
            path = fetch_pdf(
                self._entry, self._dest_dir, self._email, overwrite=self._overwrite
            )
            self.app.call_from_thread(self._on_success, path)
        except FetchError as exc:
            self.app.call_from_thread(self._on_error, str(exc))
        except Exception as exc:  # noqa: BLE001
            self.app.call_from_thread(self._on_error, f"Unexpected error: {exc}")

    def _on_success(self, path: str) -> None:
        self.query_one("#fetch-loading", LoadingIndicator).display = False
        status = self.query_one("#fetch-status", Static)
        status.set_class(True, "success")
        status.set_class(False, "error")
        status.update(f"Saved PDF:\n{path}")
        self.query_one("#btn-close", Button).disabled = False
        self.query_one("#btn-cancel", Button).disabled = True
        self._saved_path = path

    def _on_error(self, message: str) -> None:
        self.query_one("#fetch-loading", LoadingIndicator).display = False
        status = self.query_one("#fetch-status", Static)
        status.set_class(False, "success")
        status.set_class(True, "error")
        status.update(self._format_fetch_error(message))
        self.query_one("#btn-close", Button).disabled = False

    def _format_fetch_error(self, message: str) -> str:
        title = "Could not fetch PDF for this entry."
        lines = [line.strip() for line in message.splitlines() if line.strip()]
        if not lines:
            return title

        reasons = [
            line[1:].strip() if line.startswith("•") else line
            for line in lines
            if line.startswith("•") or line.startswith("-")
        ]
        if not reasons:
            reasons = [
                line
                for line in lines
                if not line.lower().startswith("could not fetch pdf")
            ]

        if not reasons:
            return title

        formatted_reasons = "\n".join(f"• {reason}" for reason in reasons)
        return f"{title}\n\n{formatted_reasons}"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-close":
            self.dismiss(self._saved_path)

    def action_cancel(self) -> None:
        self.dismiss(None)


class BatchFetchPDFModal(ModalScreen["dict | None"]):
    """Fetch PDFs for many entries in a background thread and show progress."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    DEFAULT_CSS = """
    BatchFetchPDFModal {
        align: center middle;
    }
    BatchFetchPDFModal > Vertical {
        width: 72;
        height: auto;
        border: double $accent;
        background: $surface;
        padding: 1 2;
    }
    BatchFetchPDFModal LoadingIndicator {
        height: 3;
    }
    BatchFetchPDFModal #batch-fetch-progress,
    BatchFetchPDFModal #batch-fetch-status {
        margin-top: 1;
        color: $text;
    }
    BatchFetchPDFModal #batch-fetch-status.success {
        color: $success;
    }
    BatchFetchPDFModal #batch-fetch-status.error {
        color: $error;
    }
    """

    def __init__(
        self,
        entries: list[BibEntry],
        dest_dir: str,
        unpaywall_email: str = "",
        overwrite_broken_links: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._entries = entries
        self._dest_dir = dest_dir
        self._email = unpaywall_email
        self._overwrite_broken_links = overwrite_broken_links
        self._cancel_requested = False
        self._done = False
        self._result: dict | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]Fetch Missing PDFs[/bold]", classes="modal-title")
            yield LoadingIndicator(id="batch-fetch-loading")
            yield Static("Preparing…", id="batch-fetch-progress")
            yield Static("", id="batch-fetch-status")
            with Horizontal(classes="modal-buttons"):
                yield Button("Close", variant="primary", id="btn-close", disabled=True)
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        self._do_fetch()

    @work(thread=True)
    def _do_fetch(self) -> None:
        from bibtui.pdf.fetcher import FetchError, fetch_pdf

        total = len(self._entries)
        success = 0
        failed = 0
        skipped = 0
        canceled = False
        paths_by_key: dict[str, str] = {}
        failures: list[str] = []

        for index, entry in enumerate(self._entries, start=1):
            if self._cancel_requested:
                canceled = True
                break

            self.app.call_from_thread(
                self._on_progress,
                f"[{index}/{total}] {entry.key}",
            )

            if not entry.doi and not entry.url:
                skipped += 1
                failures.append(f"{entry.key}: no DOI or URL")
                continue

            try:
                path = fetch_pdf(
                    entry,
                    self._dest_dir,
                    self._email,
                    overwrite=False,
                )
                paths_by_key[entry.key] = path
                success += 1
            except FetchError as exc:
                failed += 1
                failures.append(f"{entry.key}: {exc}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                failures.append(f"{entry.key}: unexpected error: {exc}")

        processed = success + failed + skipped
        self.app.call_from_thread(
            self._on_done,
            {
                "paths_by_key": paths_by_key,
                "processed": processed,
                "total": total,
                "success": success,
                "failed": failed,
                "skipped": skipped,
                "canceled": canceled,
                "failures": failures,
            },
        )

    def _on_progress(self, message: str) -> None:
        self.query_one("#batch-fetch-progress", Static).update(message)

    def _on_done(self, result: dict) -> None:
        self._done = True
        self._result = result
        self.query_one("#batch-fetch-loading", LoadingIndicator).display = False
        status = self.query_one("#batch-fetch-status", Static)
        if result["success"] > 0:
            status.set_class(True, "success")
            status.set_class(False, "error")
        else:
            status.set_class(False, "success")
            status.set_class(True, "error")

        canceled_text = " (canceled)" if result["canceled"] else ""
        status.update(
            "Finished"
            f"{canceled_text}: {result['success']} fetched, {result['failed']} failed, "
            f"{result['skipped']} skipped."
        )
        self.query_one("#batch-fetch-progress", Static).update(
            f"Processed {result['processed']} of {result['total']} entries."
        )
        self.query_one("#btn-close", Button).disabled = False
        self.query_one("#btn-cancel", Button).disabled = True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.action_cancel()
        elif event.button.id == "btn-close":
            self.dismiss(self._result)

    def action_cancel(self) -> None:
        if self._done:
            self.dismiss(self._result)
            return
        self._cancel_requested = True
        self.query_one("#batch-fetch-status", Static).update(
            "Stopping after current entry…"
        )
        self.query_one("#btn-cancel", Button).disabled = True


class FirstRunModal(ModalScreen[bool]):
    """One-time welcome notice — shown only on the very first launch."""

    BINDINGS = [Binding("escape", "got_it", "Got it", show=False)]

    DEFAULT_CSS = """
    FirstRunModal { align: center middle; }
    FirstRunModal > Vertical {
        width: 70; height: auto;
        border: double $accent; background: $surface; padding: 2 3;
    }
    FirstRunModal #welcome-title { text-align: center; margin-bottom: 1; }
    FirstRunModal #welcome-body  { margin-bottom: 1; }
    FirstRunModal .modal-buttons { height: 3; align: right middle; }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(
                "[bold]Welcome to bibtui![/bold]",
                id="welcome-title",
            )
            yield Static(
                "A terminal UI with keyboard and mouse support for your BibTeX libraries.\n\n"
                "[bold]You're ready to go[/bold] — no setup required.\n"
                "Just run  [bold]bibtui yourfile.bib[/bold]  and start browsing.\n\n"
                "[dim]Optional:[/dim] PDF fetching and attaching require a few"
                " extra settings\n"
                "(PDF dir, download dir, Unpaywall email).  Open them any time\n"
                "via [bold]Ctrl+P → Settings[/bold] or press [bold]Configure PDF features[/bold] below.",
                id="welcome-body",
            )
            with Horizontal(classes="modal-buttons"):
                yield Button("Got it", variant="primary", id="btn-got-it")
                yield Button(
                    "Configure PDF features", variant="default", id="btn-configure"
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-configure")

    def action_got_it(self) -> None:
        self.dismiss(False)
