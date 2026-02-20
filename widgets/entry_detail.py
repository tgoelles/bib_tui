from __future__ import annotations
import os
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label, Static, TextArea
from textual.containers import Horizontal
from rich.syntax import Syntax
from bib.models import BibEntry, ENTRY_TYPES
from bib.parser import entry_to_bibtex_str
from utils.config import parse_jabref_path


def _render_entry(entry: BibEntry) -> str:
    """Build a Rich-formatted string for the main body of the detail pane."""
    lines: list[str] = []

    # Title
    lines.append(f"[bold cyan]{entry.title or '(no title)'}[/bold cyan]")
    lines.append("")

    # Entry type badge
    lines.append(f"[dim]@{entry.entry_type}[/dim]  [dim]key:[/dim] [yellow]{entry.key}[/yellow]")
    lines.append("")

    # Tags
    if entry.tags:
        tag_str = " ".join(f"[white on dark_green] {t} [/white on dark_green]" for t in entry.tags)
        lines.append(f"[bold]Tags:[/bold]  {tag_str}")
    else:
        lines.append("[bold]Tags:[/bold]  [dim](none)[/dim]")

    lines.append("")
    lines.append("─" * 50)
    lines.append("")

    # Key fields
    entry_spec = ENTRY_TYPES.get(entry.entry_type, {"required": [], "optional": []})
    required = set(entry_spec["required"])

    def field_line(label: str, value: str, is_required: bool = False) -> str:
        color = "green" if is_required else "blue"
        req_marker = "[green]✓[/green] " if is_required else "  "
        if value:
            return f"{req_marker}[{color}]{label:<12}[/{color}] {value}"
        else:
            return f"{req_marker}[dim]{label:<12}[/dim] [dim](empty)[/dim]"

    standard_fields = [
        ("Author", "author"),
        ("Year", "year"),
        ("Journal", "journal"),
        ("DOI", "doi"),
        ("Keywords", "keywords"),
    ]

    for label, key in standard_fields:
        val = entry.get_field(key)
        lines.append(field_line(label, val, key in required))

    # Raw extra fields
    if entry.raw_fields:
        lines.append("")
        lines.append("[dim]── Other fields ──[/dim]")
        for k, v in entry.raw_fields.items():
            if v:
                lines.append(f"  [dim]{k:<12}[/dim] {v[:80]}")

    # Abstract
    if entry.abstract:
        lines.append("")
        lines.append("[bold]Abstract:[/bold]")
        words = entry.abstract.split()
        current = ""
        for word in words:
            if len(current) + len(word) + 1 > 70:
                lines.append(f"  {current}")
                current = word
            else:
                current = f"{current} {word}".strip()
        if current:
            lines.append(f"  {current}")


    return "\n".join(lines)


def _render_raw(entry: BibEntry) -> Syntax:
    """Render entry as raw BibTeX with syntax highlighting."""
    return Syntax(entry_to_bibtex_str(entry), "bibtex", theme="monokai", word_wrap=True)


class EntryDetail(Widget):
    """Right pane: formatted entry detail view, togglable to raw BibTeX."""

    DEFAULT_CSS = """
    EntryDetail {
        height: 100%;
        overflow-y: scroll;
        padding: 1 2;
    }
    #detail-meta {
        height: auto;
        layout: horizontal;
        margin-bottom: 1;
    }
    #detail-read-state {
        width: auto;
        margin-right: 3;
    }
    #detail-rating {
        width: auto;
        margin-right: 3;
    }
    #detail-file {
        width: auto;
    }
    #detail-content {
        height: auto;
    }
    #detail-raw {
        display: none;
        height: 1fr;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._entry: BibEntry | None = None
        self._raw_mode: bool = False
        self._pdf_base_dir: str = ""

    def set_pdf_base_dir(self, base_dir: str) -> None:
        self._pdf_base_dir = base_dir

    def compose(self) -> ComposeResult:
        with Horizontal(id="detail-meta"):
            yield Label("", id="detail-read-state")
            yield Label("", id="detail-rating")
            yield Label("", id="detail-file")
        yield Static("Select an entry to view details.", id="detail-content")
        yield TextArea("", id="detail-raw", read_only=True)

    def show_entry(self, entry: BibEntry | None) -> None:
        self._entry = entry
        self._refresh_content()

    @property
    def raw_mode(self) -> bool:
        return self._raw_mode

    def toggle_view(self) -> None:
        self._raw_mode = not self._raw_mode
        self._refresh_content()
        mode = "raw BibTeX" if self._raw_mode else "formatted"
        self.border_title = f"Entry Detail [{mode}]"

    def _file_icon(self, entry: BibEntry) -> str:
        if not entry.file:
            return " "
        path = parse_jabref_path(entry.file, self._pdf_base_dir)
        return "■" if os.path.exists(path) else "□"

    def _refresh_content(self) -> None:
        read_label = self.query_one("#detail-read-state", Label)
        rating_label = self.query_one("#detail-rating", Label)
        file_label = self.query_one("#detail-file", Label)
        content = self.query_one("#detail-content", Static)

        if self._entry is None:
            read_label.update("")
            rating_label.update("")
            file_label.update("")
            content.update("Select an entry to view details.")
            self.query_one("#detail-raw", TextArea).display = False
            content.display = True
            return

        e = self._entry
        state_label = e.read_state if e.read_state else "unset"
        read_label.update(f"[bold]Read:[/bold] {e.read_state_icon} {state_label}")

        stars = e.rating_stars or "[dim]unrated[/dim]"
        rating_label.update(f"[bold]Rating:[/bold] [yellow]{stars}[/yellow]")

        icon = self._file_icon(e)
        if not e.file:
            file_label.update("[dim]PDF: —[/dim]")
        elif icon == "■":
            file_label.update(f"[bold]PDF:[/bold] ■")
        else:
            file_label.update(f"[bold]PDF:[/bold] [dim]□ not found[/dim]")

        raw = self.query_one("#detail-raw", TextArea)
        if self._raw_mode:
            content.display = False
            raw.display = True
            raw.load_text(entry_to_bibtex_str(e))
        else:
            raw.display = False
            content.display = True
            content.update(_render_entry(e))
