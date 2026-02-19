from __future__ import annotations
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label, Static
from textual.containers import Horizontal
from rich.syntax import Syntax
from bib.models import BibEntry, ENTRY_TYPES, READ_STATE_ICONS
from bib.parser import entry_to_bibtex_str

_READ_STATE_TOOLTIP = (
    "Read state — press [r] to cycle:\n"
    "  (unset)  nothing yet\n"
    "  ○  to-read\n"
    "  ◑  skimmed\n"
    "  ●  read"
)

_RATING_TOOLTIP = (
    "Rating — press [1]–[5] to set, [0] to clear\n"
    "  ★       1 star\n"
    "  ★★      2 stars\n"
    "  ★★★     3 stars\n"
    "  ★★★★    4 stars\n"
    "  ★★★★★   5 stars"
)


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
    }
    #detail-content {
        height: auto;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._entry: BibEntry | None = None
        self._raw_mode: bool = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="detail-meta"):
            yield Label("", id="detail-read-state")
            yield Label("", id="detail-rating")
        yield Static("Select an entry to view details.", id="detail-content")

    def on_mount(self) -> None:
        self.query_one("#detail-read-state", Label).tooltip = _READ_STATE_TOOLTIP
        self.query_one("#detail-rating", Label).tooltip = _RATING_TOOLTIP

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
        read_label = self.query_one("#detail-read-state", Label)
        rating_label = self.query_one("#detail-rating", Label)
        content = self.query_one("#detail-content", Static)

        if self._entry is None:
            read_label.update("")
            rating_label.update("")
            content.update("Select an entry to view details.")
            return

        e = self._entry
        state_label = e.read_state if e.read_state else "unset"
        read_label.update(f"[bold]Read:[/bold] {e.read_state_icon} {state_label}")

        stars = e.rating_stars or "[dim]unrated[/dim]"
        rating_label.update(f"[bold]Rating:[/bold] [yellow]{stars}[/yellow]")

        if self._raw_mode:
            content.update(_render_raw(e))
        else:
            content.update(_render_entry(e))
