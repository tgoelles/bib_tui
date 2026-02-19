from __future__ import annotations
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static, TextArea
from textual.containers import Vertical, Horizontal
from bib.models import BibEntry


class ConfirmModal(ModalScreen[bool]):
    """Generic yes/no confirmation dialog."""

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
            yield Label("[bold]Confirm[/bold]", id="modal-title")
            yield Static(self._message)
            with Horizontal(id="modal-buttons"):
                yield Button("Yes", variant="error", id="btn-yes")
                yield Button("No", variant="primary", id="btn-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-yes")


class DOIModal(ModalScreen[BibEntry | None]):
    """Modal to fetch an entry by DOI."""

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
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold cyan]Add Entry by DOI[/bold cyan]")
            yield Input(placeholder="Enter DOI (e.g. 10.1038/nature12345)", id="doi-input")
            yield Static("", id="doi-status")
            with Horizontal(id="modal-buttons"):
                yield Button("Fetch", variant="primary", id="btn-fetch")
                yield Button("Cancel", id="btn-cancel")

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
        status.update("[yellow]Fetching...[/yellow]")
        try:
            from bib.doi import fetch_by_doi
            entry = fetch_by_doi(doi)
            status.update(f"[green]Found:[/green] {entry.title[:60]}")
            # Auto-dismiss with the result after a short display
            self.app.call_later(self._confirm, entry)
        except Exception as e:
            status.update(f"[red]Error:[/red] {e}")

    def _confirm(self, entry: BibEntry) -> None:
        self.dismiss(entry)


class EditModal(ModalScreen[BibEntry | None]):
    """Modal to edit key fields of an entry."""

    DEFAULT_CSS = """
    EditModal {
        align: center middle;
    }
    EditModal > Vertical {
        width: 80;
        height: 36;
        border: double $accent;
        background: $surface;
        padding: 1 2;
        overflow-y: scroll;
    }
    EditModal Input {
        margin-bottom: 1;
    }
    EditModal Label {
        color: $accent;
    }
    """

    def __init__(self, entry: BibEntry, **kwargs):
        super().__init__(**kwargs)
        self._entry = entry

    def compose(self) -> ComposeResult:
        e = self._entry
        with Vertical():
            yield Label(f"[bold cyan]Edit Entry[/bold cyan]  [dim]{e.key}[/dim]")
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
            with Horizontal(id="modal-buttons"):
                yield Button("Save", variant="primary", id="btn-save")
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
        self.dismiss(e)


class TagsModal(ModalScreen[list[str] | None]):
    """Quick modal to edit tags for an entry."""

    DEFAULT_CSS = """
    TagsModal {
        align: center middle;
    }
    TagsModal > Vertical {
        width: 60;
        height: auto;
        border: double $accent;
        background: $surface;
        padding: 1 2;
    }
    """

    def __init__(self, entry: BibEntry, **kwargs):
        super().__init__(**kwargs)
        self._entry = entry

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"[bold cyan]Edit Tags[/bold cyan]  [dim]{self._entry.key}[/dim]")
            yield Input(
                value=", ".join(self._entry.tags),
                placeholder="tag1, tag2, tag3",
                id="tags-input",
            )
            with Horizontal(id="modal-buttons"):
                yield Button("Save", variant="primary", id="btn-save")
                yield Button("Cancel", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-save":
            val = self.query_one("#tags-input", Input).value
            tags = [t.strip() for t in val.split(",") if t.strip()]
            self.dismiss(tags)

    def on_input_submitted(self, _: Input.Submitted) -> None:
        val = self.query_one("#tags-input", Input).value
        tags = [t.strip() for t in val.split(",") if t.strip()]
        self.dismiss(tags)
