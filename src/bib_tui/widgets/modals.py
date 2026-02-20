from __future__ import annotations
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static, TextArea, SelectionList
from textual.widgets._selection_list import Selection
from textual.containers import Vertical, VerticalScroll, Horizontal
from textual import on
from bib_tui.bib.models import BibEntry
from bib_tui.bib.parser import entry_to_bibtex_str, bibtex_str_to_entry
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
            yield Input(placeholder="Enter DOI (e.g. 10.1038/nature12345)", id="doi-input")
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
            yield Label(f"[bold]Edit Entry[/bold]  [dim]{e.key}[/dim]", classes="modal-title")
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
                yield Label("Tags (comma-separated)")
                yield Input(value=", ".join(e.tags), id="edit-tags")
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
        tags_str = v("#edit-tags")
        e.tags = [t.strip() for t in tags_str.split(",") if t.strip()]
        e.file = v("#edit-file")
        e.abstract = self.query_one("#edit-abstract", TextArea).text
        e.comment = self.query_one("#edit-comment", TextArea).text
        self.dismiss(e)

    def action_save_and_close(self) -> None:
        self._save()


class KeywordsModal(ModalScreen["str | None"]):
    """Keyword picker: select from all bib-wide keywords, add new ones."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    DEFAULT_CSS = """
    KeywordsModal {
        align: center middle;
    }
    KeywordsModal > Vertical {
        width: 70;
        height: 36;
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
    """

    def __init__(self, entry: BibEntry, all_keywords: list[str], **kwargs):
        super().__init__(**kwargs)
        self._all_keywords = list(all_keywords)
        self._selected: set[str] = set(entry.keywords_list)
        self._shown: list[str] = []

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]Edit Keywords[/bold]", classes="modal-title")
            yield Input(placeholder="Filter or type new keyword + Enter to add…", id="kw-filter")
            yield SelectionList(id="kw-list")
            with Horizontal(classes="modal-buttons"):
                yield Button("Write", variant="primary", id="btn-save")
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        self._rebuild_list("")
        self.call_after_refresh(self.query_one("#kw-filter", Input).focus)

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
        rest = [kw for kw in self._all_keywords if kw not in self._selected and (not f or f in kw.lower())]
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
        self.dismiss(", ".join(ordered))

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
            yield Static("[dim]Filenames in the file field are resolved relative to this path.[/dim]")
            with Horizontal(classes="modal-buttons"):
                yield Button("Write", variant="primary", id="btn-save")
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        self.call_after_refresh(self.query_one("#pdf-base-dir", Input).focus)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-save":
            self._config.pdf_base_dir = self.query_one("#pdf-base-dir", Input).value.strip()
            self.dismiss(self._config)

    def on_input_submitted(self, _: Input.Submitted) -> None:
        self._config.pdf_base_dir = self.query_one("#pdf-base-dir", Input).value.strip()
        self.dismiss(self._config)

    def action_cancel(self) -> None:
        self.dismiss(None)


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
            yield Label(f"[bold]Edit Raw BibTeX[/bold]  [dim]{self._entry.key}[/dim]", classes="modal-title")
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
