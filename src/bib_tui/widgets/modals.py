from __future__ import annotations

from textual import events, on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Input,
    Label,
    LoadingIndicator,
    SelectionList,
    Static,
    TextArea,
)
from textual.widgets._selection_list import Selection

from bib_tui.bib.models import BibEntry
from bib_tui.bib.parser import bibtex_str_to_entry, entry_to_bibtex_str
from bib_tui.utils.config import Config


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
    """

    def __init__(self, message: str, **kwargs):
        super().__init__(**kwargs)
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]Confirm[/bold]", classes="modal-title")
            yield Static(self._message)
            with Horizontal(classes="modal-buttons"):
                yield Button("Yes", variant="error", id="btn-yes")
                yield Button("No", variant="primary", id="btn-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-yes")

    def action_cancel(self) -> None:
        self.dismiss(False)


class DOIModal(ModalScreen[BibEntry | None]):
    """Modal to fetch an entry by DOI."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

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
        try:
            from bib_tui.bib.doi import fetch_by_doi

            entry = fetch_by_doi(doi)
            status.set_classes("success")
            status.update(f"Found: {entry.title[:60]}")
            self.app.call_later(self._confirm, entry)
        except Exception as e:
            status.set_classes("error")
            status.update(f"Error: {e}")

    def _confirm(self, entry: BibEntry) -> None:
        self.dismiss(entry)

    def action_cancel(self) -> None:
        self.dismiss(None)


class EditModal(ModalScreen[BibEntry | None]):
    """Modal to edit key fields of an entry."""

    BINDINGS = [Binding("escape", "save_and_close", "Write", show=False)]

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


class KeywordsModal(ModalScreen["tuple[str, set[str]] | None"]):
    """Keyword picker: select from all bib-wide keywords, add new ones."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

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
                "[dim]Esc close · Enter add new  |  ↓/↑ navigate · Space toggle · d delete everywhere[/dim]",
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
        elif self.focused is sl and event.key == "d":
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

    def _on_delete_confirmed(self, confirmed: bool, kw: str) -> None:
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

    def action_cancel(self) -> None:
        self.dismiss(None)


class SettingsModal(ModalScreen["Config | None"]):
    """Settings dialog — currently just the PDF base directory."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

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
    """

    def __init__(self, config: Config, **kwargs):
        super().__init__(**kwargs)
        self._config = config

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]Settings[/bold]", classes="modal-title")
            yield Label("PDF base directory")
            yield Input(
                value=self._config.pdf_base_dir,
                placeholder="/home/user/Papers",
                id="pdf-base-dir",
            )
            yield Static(
                "[dim]Filenames in the file field are resolved relative to this path.[/dim]"
            )
            yield Label("Unpaywall email")
            yield Input(
                value=self._config.unpaywall_email,
                placeholder="me@example.com",
                id="unpaywall-email",
            )
            yield Static(
                "[dim]Used for open-access PDF lookup via Unpaywall (free service).[/dim]"
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

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-save":
            self._collect()
            self.dismiss(self._config)

    def on_input_submitted(self, _: Input.Submitted) -> None:
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

    _ABOUT = (
        "[bold]bib-tui[/bold] v0.1.0  —  BibTeX TUI\n"
        "[dim]Author:[/dim] Thomas Gölles\n"
        "[dim]Repo:[/dim]   github.com/tgoelles/bib_tui\n"
        "[dim]Built with Claude Code (Anthropic)[/dim]"
    )

    _KEYS = """\
[bold]── Core ──────────────────────────────[/bold]
  [bold]q[/bold]         Quit
  [bold]w[/bold]         Write
  [bold]s[/bold]         Search
  [bold]e[/bold]         Edit entry (field form or raw BibTeX)
  [bold]k[/bold]         Edit keywords
  [bold]v[/bold]         Toggle raw / formatted view

[bold]── Add new entry ─────────────────────[/bold]
  [bold]d[/bold]         Import entry by DOI (fetches metadata online)
  [bold]ctrl+v[/bold]    Paste a raw BibTeX entry from clipboard
  [dim]Both methods reject duplicate cite keys.[/dim]

[bold]── Entry state ───────────────────────[/bold]
  [bold]r[/bold]         Cycle read state
  [bold]p[/bold]         Cycle priority
  [bold]␣[/bold]         Show PDF
  [bold]b[/bold]         Open URL in browser (validates http/https)
  [bold]f[/bold]         Fetch PDF (arXiv → Unpaywall → direct URL)

[bold]── Rating ────────────────────────────[/bold]
  [bold]1 – 5[/bold]     Set star rating
  [bold]0[/bold]         Mark unrated

[bold]── Other ─────────────────────────────[/bold]
  [bold]ctrl+c[/bold]    Copy cite key to clipboard
  [bold]?[/bold]         Show this help
  [bold]ctrl+p[/bold]    Command palette (Settings…)
  [bold]Esc[/bold]       Clear search / close modal
[dim]  Clipboard uses OSC 52 — requires a modern terminal[/dim]

[bold]── Sorting ───────────────────────────[/bold]
  Click any column header to sort by that column.
  Click the same header again to reverse the order.
  Active sort column is marked with [bold]▲[/bold] (asc) or [bold]▼[/bold] (desc).
  Cols: [bold]◉[/bold] state  [bold]![/bold] prio  [bold]◫[/bold] PDF  [bold]◍[/bold] URL  Type  Year  Author  Journal  Title  [bold]★[/bold]
"""
    _SEARCH = """\
[bold]── Plain text ────────────────────────[/bold]
  Searches title, author, keywords, and key.
  Multiple words are ANDed together.

[bold]── Field prefixes ────────────────────[/bold]
  [bold]a:[/bold] / [bold]author:[/bold]    filter by author
  [bold]t:[/bold] / [bold]title:[/bold]     filter by title
  [bold]k:[/bold] / [bold]kw:[/bold]        filter by keyword
  [bold]y:[/bold] / [bold]year:[/bold]      filter by year or range
  [bold]u:[/bold] / [bold]url:[/bold]       filter by URL

[bold]── Examples ──────────────────────────[/bold]
  [dim]glacier[/dim]              all fields
  [dim]a:smith t:glacier[/dim]    combined
  [dim]y:2015-2023[/dim]          year range
  [dim]k:ice a:jones[/dim]        keyword + author"""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]Help[/bold]", classes="modal-title")
            with VerticalScroll():
                yield Static(self._ABOUT, id="help-about")
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

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

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

    def action_cancel(self) -> None:
        self.dismiss(None)


class PasteModal(ModalScreen["BibEntry | None"]):
    """Modal to import a BibTeX entry from pasted clipboard text."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

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
    }
    """

    def __init__(
        self,
        entry: BibEntry,
        dest_dir: str,
        unpaywall_email: str = "",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._entry = entry
        self._dest_dir = dest_dir
        self._email = unpaywall_email
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
        from bib_tui.bib.pdf_fetcher import FetchError, fetch_pdf

        try:
            path = fetch_pdf(self._entry, self._dest_dir, self._email)
            self.app.call_from_thread(self._on_success, path)
        except FetchError as exc:
            self.app.call_from_thread(self._on_error, str(exc))
        except Exception as exc:  # noqa: BLE001
            self.app.call_from_thread(self._on_error, f"Unexpected error: {exc}")

    def _on_success(self, path: str) -> None:
        self.query_one("#fetch-loading", LoadingIndicator).display = False
        self.query_one("#fetch-status", Static).update(f"[green]Saved:[/green] {path}")
        self.query_one("#btn-close", Button).disabled = False
        self.query_one("#btn-cancel", Button).disabled = True
        self._saved_path = path

    def _on_error(self, message: str) -> None:
        self.query_one("#fetch-loading", LoadingIndicator).display = False
        self.query_one("#fetch-status", Static).update(f"[red]{message}[/red]")
        self.query_one("#btn-close", Button).disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-close":
            self.dismiss(self._saved_path)

    def action_cancel(self) -> None:
        self.dismiss(None)
