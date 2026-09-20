import textwrap

from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.markup import escape
from textual.widget import Widget
from textual.widgets import Label, Select, Static, TextArea

from bibtui.bib.authors import AUTHOR_SEPARATOR, format_authors
from bibtui.bib.citation_preview import (
    available_csl_styles,
    default_csl_style_key,
    render_citation_preview,
)
from bibtui.bib.models import PRIORITIES, READ_STATES, BibEntry
from bibtui.bib.parser import entry_to_bibtex_str
from bibtui.pdf.paths import pdf_link_state


def _read_markup(entry: BibEntry) -> str:
    return f"[bold]Read:[/bold] {entry.read_state_icon} {entry.read_state or 'unset'}"


def _priority_markup(entry: BibEntry) -> str:
    if entry.priority:
        return f"[bold]Urgency:[/bold] {entry.priority_icon} {entry.priority_label}"
    return "[dim]Urgency: —[/dim]"


def _rating_markup(entry: BibEntry, color: str) -> str:
    stars = entry.rating_stars or "[dim]unrated[/dim]"
    return f"[bold]Rating:[/bold] [{color}]{stars}[/]"


_PDF_MARKUP = {
    "found": "[bold]PDF:[/bold] ■ linked",
    "missing": "[dim]PDF: □ missing[/dim]",
    "none": "[dim]PDF: — none[/dim]",
}


def _status_widths() -> dict[str, int]:
    """Cell width each status-row label needs for its widest possible text.

    The labels get these as fixed widths so the row keeps the same horizontal
    layout while flicking through entries, instead of every label resizing to
    its current text and shoving the ones after it sideways.
    """

    def widest(markups) -> int:
        return max(Text.from_markup(m).cell_len for m in markups)

    def probe(**fields) -> BibEntry:
        return BibEntry(key="", entry_type="", **fields)

    return {
        "read": widest(_read_markup(probe(read_state=s)) for s in READ_STATES),
        "priority": widest(_priority_markup(probe(priority=p)) for p in PRIORITIES),
        "rating": widest(_rating_markup(probe(rating=r), "white") for r in range(6)),
        "pdf": widest(_PDF_MARKUP.values()),
    }


_STATUS_WIDTHS = _status_widths()


def _status_label(widget_id: str, width: int) -> Label:
    label = Label("", id=widget_id)
    label.styles.width = width
    return label


# The author block under the title is always this many lines tall, so a long
# author list can't push everything below it around while flicking through
# entries.
_AUTHOR_LINES = 3
_NBSP = "\u00a0"
_DEFAULT_AUTHOR_WIDTH = 60


def _author_lines(author: str, width: int) -> list[str]:
    """Markup lines for the author block: exactly ``_AUTHOR_LINES`` tall.

    Shown JabRef-style as ``Last, First / Last, First`` and wrapped to *width*
    without ever splitting a name across lines; anything past the last line is
    cut off with "…", and a shorter list is padded with blank lines.
    """
    names = format_authors(author)
    if not names:
        return ["[dim](no author)[/dim]"] + [""] * (_AUTHOR_LINES - 1)
    width = max(width, 10)
    # Each name (plus its trailing separator) is glued into one unbreakable
    # word with non-breaking spaces, unless it is too wide to fit a line.
    sep = AUTHOR_SEPARATOR.strip()
    tokens = [f"{name} {sep}" for name in names[:-1]] + [names[-1]]
    words = [t if len(t) > width else t.replace(" ", _NBSP) for t in tokens]
    wrapped = textwrap.wrap(
        " ".join(words),
        width=width,
        max_lines=_AUTHOR_LINES,
        placeholder=" …",
        break_on_hyphens=False,
    )
    lines = [escape(line.replace(_NBSP, " ")) for line in wrapped]
    return lines + [""] * (_AUTHOR_LINES - len(lines))


def _render_entry(
    entry: BibEntry,
    colors: dict[str, str],
    author_width: int = _DEFAULT_AUTHOR_WIDTH,
) -> str:
    """Build a Rich-formatted string for the main body of the detail pane.

    *colors* is a dict with keys: title, key, required, optional, tag_fg,
    tag_bg, warning.  Values are Rich-compatible color strings (hex or names).
    *author_width* is the width the author block wraps to.
    """
    c = colors
    lines: list[str] = []

    # Title, with the authors directly beneath it
    lines.append(f"[bold {c['title']}]{entry.title or '(no title)'}[/]")
    lines.extend(_author_lines(entry.get_field("author"), author_width))
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
        ("Year", "year"),
        ("Journal", "journal"),
        ("DOI", "doi"),
        ("URL", "url"),
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
        margin-bottom: 1;
    }
    #detail-meta Label {
        height: 1;
        margin-right: 2;
        text-wrap: nowrap;
        text-overflow: ellipsis;
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
        self._author_width: int = _DEFAULT_AUTHOR_WIDTH
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

    def on_resize(self, event) -> None:
        """Re-wrap the author block when the pane's width changes."""
        if (
            self._entry is not None
            and not self._raw_mode
            and self._current_author_width() != self._author_width
        ):
            self._refresh_content()

    def _current_author_width(self) -> int:
        return self.scrollable_content_region.width or _DEFAULT_AUTHOR_WIDTH

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
            yield _status_label("detail-read-state", _STATUS_WIDTHS["read"])
            yield _status_label("detail-priority", _STATUS_WIDTHS["priority"])
            yield _status_label("detail-rating", _STATUS_WIDTHS["rating"])
            yield _status_label("detail-pdf-status", _STATUS_WIDTHS["pdf"])
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
        citation_panel = self.query_one("#detail-citation-panel", Vertical)
        citation_preview_widget = self.query_one("#detail-citation-preview", Static)
        abstract_widget = self.query_one("#detail-abstract", Static)
        content = self.query_one("#detail-content", Static)

        if self._entry is None:
            read_label.update("")
            priority_label.update("")
            rating_label.update("")
            pdf_status_label.update("")
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

        read_label.update(_read_markup(e))
        priority_label.update(_priority_markup(e))
        rating_label.update(_rating_markup(e, colors["warning"]))
        pdf_status_label.update(
            _PDF_MARKUP[pdf_link_state(e.file, e.key, self._pdf_base_dir)]
        )

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
            self._author_width = self._current_author_width()
            content.update(_render_entry(e, colors, self._author_width))
