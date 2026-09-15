from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Label, Select, Static, TextArea

from bibtui.bib.citation_preview import (
    available_csl_styles,
    default_csl_style_key,
    render_citation_preview,
)
from bibtui.bib.models import BibEntry
from bibtui.bib.parser import entry_to_bibtex_str
from bibtui.pdf.paths import pdf_link_state


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

    return "\n".join(lines)


def _render_abstract(entry: BibEntry) -> str:
    """Render abstract block separately so citation controls can sit above it."""
    if not entry.abstract:
        return ""

    lines: list[str] = ["[bold]Abstract:[/bold]"]
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
    #detail-pdf-status {
        width: auto;
        margin-right: 2;
    }
    #detail-url {
        width: 1fr;
        margin-left: 2;
        color: $text-muted;
    }
    #detail-csl-row {
        height: auto;
        layout: horizontal;
        align: left middle;
        margin: 0 0 1 0;
    }
    #detail-citation-panel {
        margin: 1 0;
        padding: 0 0 1 0;
        height: auto;
    }
    #detail-citation-title {
        margin: 0 0 1 0;
    }
    #detail-csl-select {
        width: 1fr;
        max-width: 52;
    }
    #detail-citation-preview {
        margin: 0 0 1 0;
        color: $text;
        height: auto;
    }
    #detail-abstract {
        margin: 0 0 1 0;
        color: $text;
        height: auto;
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

    def __init__(self, default_csl_style: str = "", **kwargs):
        super().__init__(**kwargs)
        self._entry: BibEntry | None = None
        self._raw_mode: bool = False
        self._pdf_base_dir: str = ""
        self._csl_styles = available_csl_styles()
        self._selected_csl_style = self._resolve_csl_style(default_csl_style)

    def _resolve_csl_style(self, preferred_style: str) -> str:
        keys = [key for _label, key in self._csl_styles]
        if preferred_style and preferred_style in keys:
            return preferred_style
        fallback = default_csl_style_key()
        if fallback in keys:
            return fallback
        return keys[0] if keys else fallback

    def on_mount(self) -> None:
        self.app.theme_changed_signal.subscribe(self, self._on_theme_changed)

    def _on_theme_changed(self, _theme) -> None:
        if self._entry is not None:
            self._refresh_content()

    def set_pdf_base_dir(self, base_dir: str) -> None:
        self._pdf_base_dir = base_dir

    def set_default_csl_style(self, style_key: str) -> None:
        resolved = self._resolve_csl_style(style_key)
        self._selected_csl_style = resolved
        if self.is_mounted:
            self.query_one("#detail-csl-select", Select).value = resolved
        if self._entry is not None:
            self._refresh_content()

    def compose(self) -> ComposeResult:
        with Horizontal(id="detail-meta"):
            yield Label("", id="detail-read-state")
            yield Label("", id="detail-priority")
            yield Label("", id="detail-rating")
            yield Label("", id="detail-pdf-status")
            yield Label("", id="detail-url")
        yield Static("Select an entry to view details.", id="detail-content")
        with Vertical(id="detail-citation-panel"):
            yield Label("[bold]Citation[/bold]", id="detail-citation-title")
            with Horizontal(id="detail-csl-row"):
                yield Select(
                    self._csl_styles,
                    allow_blank=False,
                    value=self._selected_csl_style,
                    compact=True,
                    id="detail-csl-select",
                )
            yield Static("", id="detail-citation-preview")
        yield Static("", id="detail-abstract")
        yield TextArea("", id="detail-raw", read_only=True)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "detail-csl-select":
            return
        if not isinstance(event.value, str):
            return
        self._selected_csl_style = event.value
        if self._entry is not None:
            self._refresh_content()

    def show_entry(self, entry: BibEntry | None) -> None:
        self._entry = entry
        self._refresh_content()

    def citation_preview_text(self) -> str:
        """Return rendered citation preview for the selected CSL style."""
        if self._entry is None:
            return ""
        return render_citation_preview(self._entry, self._selected_csl_style).strip()

    @property
    def raw_mode(self) -> bool:
        return self._raw_mode

    def toggle_view(self) -> None:
        self._raw_mode = not self._raw_mode
        self._refresh_content()
        mode = "raw BibTeX" if self._raw_mode else "formatted"
        self.border_title = f"Entry Detail [{mode}]"

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
        pdf_status_label = self.query_one("#detail-pdf-status", Label)
        url_label = self.query_one("#detail-url", Label)
        citation_panel = self.query_one("#detail-citation-panel", Vertical)
        citation_preview_widget = self.query_one("#detail-citation-preview", Static)
        abstract_widget = self.query_one("#detail-abstract", Static)
        content = self.query_one("#detail-content", Static)

        if self._entry is None:
            read_label.update("")
            priority_label.update("")
            rating_label.update("")
            pdf_status_label.update("")
            url_label.update("")
            citation_panel.display = False
            citation_preview_widget.update("")
            abstract_widget.display = False
            abstract_widget.update("")
            content.update("Select an entry to view details.")
            self.query_one("#detail-raw", TextArea).display = False
            content.display = True
            return

        e = self._entry
        colors = self._theme_colors()
        citation_preview = render_citation_preview(e, self._selected_csl_style)
        citation_panel.display = True
        if citation_preview:
            citation_preview_widget.update(citation_preview)
        else:
            citation_preview_widget.update("[dim](unavailable)[/dim]")

        abstract_text = _render_abstract(e)
        if abstract_text:
            abstract_widget.display = True
            abstract_widget.update(abstract_text)
        else:
            abstract_widget.display = False
            abstract_widget.update("")

        state_label = e.read_state if e.read_state else "unset"
        read_label.update(f"[bold]Read:[/bold] {e.read_state_icon} {state_label}")

        if e.priority:
            priority_label.update(
                f"[bold]Urgency:[/bold] {e.priority_icon} {e.priority_label}"
            )
        else:
            priority_label.update("[dim]Urgency: —[/dim]")

        stars = e.rating_stars or "[dim]unrated[/dim]"
        rating_label.update(f"[bold]Rating:[/bold] [{colors['warning']}]{stars}[/]")

        state = pdf_link_state(e.file, e.key, self._pdf_base_dir)
        if state == "found":
            pdf_status_label.update("[bold]PDF:[/bold] ■ linked")
        elif state == "missing":
            pdf_status_label.update("[dim]PDF: □ missing[/dim]")
        else:
            pdf_status_label.update("[dim]PDF: — none[/dim]")

        if e.url:
            short = e.url if len(e.url) <= 34 else e.url[:31] + "…"
            url_label.update(f"[bold]↗ URL:[/bold] {short}")
        else:
            url_label.update("[dim]↗ URL: —[/dim]")

        raw = self.query_one("#detail-raw", TextArea)
        if self._raw_mode:
            content.display = False
            citation_panel.display = False
            abstract_widget.display = False
            raw.display = True
            raw.load_text(entry_to_bibtex_str(e))
        else:
            raw.display = False
            content.display = True
            citation_panel.display = True
            if abstract_text:
                abstract_widget.display = True
            content.update(_render_entry(e, colors))
