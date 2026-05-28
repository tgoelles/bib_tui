import os
from typing import TYPE_CHECKING, cast

from rich.syntax import Syntax
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Collapsible, Label, Static, TextArea

from bibtui.bib.models import BibEntry
from bibtui.bib.parser import entry_to_bibtex_str
from bibtui.pdf.paths import parse_jabref_path

if TYPE_CHECKING:
    from bibtui.app import BibTuiApp


def _render_entry(entry: BibEntry, colors: dict[str, str]) -> str:
    """Build a Rich-formatted string for the main body of the detail pane.

    *colors* is a dict with keys: title, key, required, optional, tag_fg,
    tag_bg, warning.  Values are Rich-compatible color strings (hex or names).
    """
    c = colors
    lines: list[str] = []

    # Title
    lines.append(f"[bold {c['title']}]{entry.title or '(no title)'}[/]")
    lines.append("")

    # Entry type badge
    lines.append(
        f"[dim]@{entry.entry_type}[/dim]  [dim]key:[/dim] [{c['key']}]{entry.key}[/]"
    )
    lines.append("")

    # Key fields
    def field_line(label: str, value: str) -> str:
        if value:
            return f"[{c['required']}]{label:<12}[/] {value}"
        else:
            return f"[dim]{label:<12}[/dim] [dim](empty)[/dim]"

    standard_fields = [
        ("Author", "author"),
        ("Year", "year"),
        ("Journal", "journal"),
        ("DOI", "doi"),
    ]

    for label, key in standard_fields:
        lines.append(field_line(label, entry.get_field(key)))

    lines.append("")
    lines.append("─" * 50)
    lines.append("")

    # Keywords as badges
    if entry.keywords_list:
        kw_str = " ".join(
            f"[{c['tag_fg']} on {c['tag_bg']}] {k} [/]" for k in entry.keywords_list
        )
        lines.append(f"[bold]Keywords:[/bold]  {kw_str}")
    else:
        lines.append("[bold]Keywords:[/bold]  [dim](none)[/dim]")

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
        margin-bottom: 0;
    }
    #detail-read-state {
        width: auto;
        margin-right: 2;
    }
    #detail-rating {
        width: auto;
        margin-right: 2;
    }
    #detail-priority {
        width: auto;
        margin-right: 2;
    }
    #detail-url {
        width: 1fr;
        margin-left: 2;
        color: $text-muted;
    }
    #detail-pdf-collapsible {
        margin: 1 0;
    }
    #detail-pdf-panel {
        padding: 0 1;
        height: auto;
    }
    #detail-pdf-title {
        margin: 1 0 0 0;
    }
    #detail-pdf-status {
        color: $text-muted;
        margin: 0 0 1 0;
    }
    #detail-pdf-actions-main {
        height: auto;
        layout: horizontal;
        margin-bottom: 0;
    }
    #detail-pdf-actions-extra {
        height: auto;
        layout: horizontal;
        margin-bottom: 1;
    }
    #detail-pdf-actions-main Button,
    #detail-pdf-actions-extra Button {
        min-width: 12;
        margin-right: 1;
    }
    #detail-pdf-actions-main Button {
        width: 1fr;
    }
    #detail-pdf-actions-extra Button {
        width: 1fr;
    }
    EntryDetail.narrow #detail-pdf-actions-main,
    EntryDetail.narrow #detail-pdf-actions-extra {
        layout: vertical;
    }
    EntryDetail.narrow #detail-pdf-actions-main Button,
    EntryDetail.narrow #detail-pdf-actions-extra Button {
        width: 1fr;
        margin-right: 0;
        margin-bottom: 1;
    }
    #detail-content {
        height: auto;
        color: $text;
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

    def on_mount(self) -> None:
        self.app.theme_changed_signal.subscribe(self, self._on_theme_changed)

    def _on_theme_changed(self, _theme) -> None:
        if self._entry is not None:
            self._refresh_content()

    def on_resize(self, event: events.Resize) -> None:
        # Keep button rows usable on narrow terminal panes.
        self.set_class(event.size.width < 90, "narrow")

    def set_pdf_base_dir(self, base_dir: str) -> None:
        self._pdf_base_dir = base_dir

    def compose(self) -> ComposeResult:
        with Horizontal(id="detail-meta"):
            yield Label("", id="detail-read-state")
            yield Label("", id="detail-priority")
            yield Label("", id="detail-rating")
            yield Label("", id="detail-url")
        with Collapsible(collapsed=True, title="PDF", id="detail-pdf-collapsible"):
            with Vertical(id="detail-pdf-panel"):
                yield Label("[bold]PDF Actions[/bold]", id="detail-pdf-title")
                yield Label("", id="detail-pdf-status")
                with Horizontal(id="detail-pdf-actions-main"):
                    yield Button("Open", id="detail-pdf-open")
                    yield Button("Fetch", id="detail-pdf-fetch")
                    yield Button("Add", id="detail-pdf-add")
                with Horizontal(id="detail-pdf-actions-extra"):
                    yield Button("Copy PDF", id="detail-pdf-copy-file")
                    yield Button("Copy path", id="detail-pdf-copy-path")
                    yield Button("Delete", id="detail-pdf-delete", variant="error")
        yield Static("Select an entry to view details.", id="detail-content")
        yield TextArea("", id="detail-raw", read_only=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        app = cast("BibTuiApp", self.app)
        if event.button.id == "detail-pdf-open":
            app.action_open_pdf()
        elif event.button.id == "detail-pdf-fetch":
            app.action_fetch_pdf()
        elif event.button.id == "detail-pdf-add":
            app.action_add_pdf()
        elif event.button.id == "detail-pdf-copy-file":
            getattr(app, "action_pdf_copy_file")()
        elif event.button.id == "detail-pdf-copy-path":
            app.action_pdf_copy_path()
        elif event.button.id == "detail-pdf-delete":
            app.action_pdf_delete()

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

    def _theme_colors(self) -> dict[str, str]:
        """Return Rich color strings derived from the current Textual theme.

        Only used for semantic highlights (title, key, field labels, tags).
        Plain body text uses CSS ``color: $text`` on the Static widget so that
        it automatically follows the theme without any Python involvement.
        """
        tv = self.app.theme_variables
        return {
            "title": tv.get("text-primary", "cyan"),
            "key": tv.get("text-accent", "yellow"),
            "required": tv.get("text-success", "green"),
            "optional": tv.get("text-accent", "blue"),
            "warning": tv.get("text-warning", "yellow"),
            "tag_fg": "white",
            "tag_bg": tv.get("primary", "dark_green"),
        }

    def _refresh_content(self) -> None:
        read_label = self.query_one("#detail-read-state", Label)
        priority_label = self.query_one("#detail-priority", Label)
        rating_label = self.query_one("#detail-rating", Label)
        pdf_collapsible = self.query_one("#detail-pdf-collapsible", Collapsible)
        pdf_status_label = self.query_one("#detail-pdf-status", Label)
        pdf_open_btn = self.query_one("#detail-pdf-open", Button)
        pdf_add_btn = self.query_one("#detail-pdf-add", Button)
        pdf_fetch_btn = self.query_one("#detail-pdf-fetch", Button)
        pdf_copy_file_btn = self.query_one("#detail-pdf-copy-file", Button)
        pdf_copy_path_btn = self.query_one("#detail-pdf-copy-path", Button)
        pdf_delete_btn = self.query_one("#detail-pdf-delete", Button)
        url_label = self.query_one("#detail-url", Label)
        content = self.query_one("#detail-content", Static)

        if self._entry is None:
            read_label.update("")
            priority_label.update("")
            rating_label.update("")
            pdf_collapsible.display = False
            pdf_status_label.update("")
            url_label.update("")
            content.update("Select an entry to view details.")
            self.query_one("#detail-raw", TextArea).display = False
            content.display = True
            return

        e = self._entry
        colors = self._theme_colors()

        state_label = e.read_state if e.read_state else "unset"
        read_label.update(f"[bold]Read:[/bold] {e.read_state_icon} {state_label}")

        if e.priority:
            priority_label.update(
                f"[bold]Priority:[/bold] {e.priority_icon} {e.priority_label}"
            )
        else:
            priority_label.update("[dim]Priority: —[/dim]")

        stars = e.rating_stars or "[dim]unrated[/dim]"
        rating_label.update(f"[bold]Rating:[/bold] [{colors['warning']}]{stars}[/]")

        pdf_collapsible.display = True

        icon = self._file_icon(e)
        if not e.file:
            pdf_status_label.update(
                "[bold]Status:[/bold] [dim]No linked PDF. Use Fetch or Add.[/dim]"
            )
            pdf_fetch_btn.disabled = False
            pdf_add_btn.disabled = False
            pdf_open_btn.disabled = True
            pdf_copy_file_btn.disabled = True
            pdf_copy_path_btn.disabled = True
            pdf_delete_btn.disabled = True
        elif icon == "■":
            pdf_status_label.update("[bold]Status:[/bold] ■ Local PDF linked")
            pdf_fetch_btn.disabled = True
            pdf_add_btn.disabled = True
            pdf_open_btn.disabled = False
            pdf_copy_file_btn.disabled = False
            pdf_copy_path_btn.disabled = False
            pdf_delete_btn.disabled = False
        else:
            pdf_status_label.update(
                "[bold]Status:[/bold] [dim]□ Linked file not found. Use Fetch/Add or Delete.[/dim]"
            )
            pdf_fetch_btn.disabled = False
            pdf_add_btn.disabled = False
            pdf_open_btn.disabled = True
            pdf_copy_file_btn.disabled = True
            pdf_copy_path_btn.disabled = True
            pdf_delete_btn.disabled = False

        if e.url:
            short = e.url if len(e.url) <= 34 else e.url[:31] + "…"
            url_label.update(f"[bold]🔗 URL:[/bold] {short}")
        else:
            url_label.update("[dim]🔗 URL: —[/dim]")

        raw = self.query_one("#detail-raw", TextArea)
        if self._raw_mode:
            content.display = False
            raw.display = True
            raw.load_text(entry_to_bibtex_str(e))
        else:
            raw.display = False
            content.display = True
            content.update(_render_entry(e, colors))
