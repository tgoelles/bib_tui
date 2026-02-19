from __future__ import annotations
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static
from rich.syntax import Syntax
from bib.models import BibEntry, ENTRY_TYPES
from bib.parser import entry_to_bibtex_str


def _render_entry(entry: BibEntry) -> str:
    """Build a Rich-formatted string for the entry detail pane."""
    lines: list[str] = []

    # Title
    lines.append(f"[bold cyan]{entry.title or '(no title)'}[/bold cyan]")
    lines.append("")

    # Entry type badge
    lines.append(f"[dim]@{entry.entry_type}[/dim]  [dim]key:[/dim] [yellow]{entry.key}[/yellow]")
    lines.append("")

    # Rating
    lines.append(f"[bold]Rating:[/bold] [yellow]{entry.rating_stars}[/yellow]")

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

    # Abstract (last, can be long)
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

    # PDF
    lines.append("")
    if entry.file:
        lines.append(f"[bold]PDF:[/bold] [link]{entry.file}[/link]")
    else:
        lines.append("[bold]PDF:[/bold] [dim](not linked)[/dim]")

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
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._entry: BibEntry | None = None
        self._raw_mode: bool = False

    def compose(self) -> ComposeResult:
        yield Static("Select an entry to view details.", id="detail-content")

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

    def _refresh_content(self) -> None:
        content = self.query_one("#detail-content", Static)
        if self._entry is None:
            content.update("Select an entry to view details.")
        elif self._raw_mode:
            content.update(_render_raw(self._entry))
        else:
            content.update(_render_entry(self._entry))
