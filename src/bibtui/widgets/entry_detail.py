import textwrap

from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.markup import escape
from textual.widget import Widget
from textual.widgets import Label, Select, Static, TextArea

from bibtui.bib.authors import AUTHOR_SEPARATOR, format_authors
from bibtui.bib.latex import decode_latex
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

# The status labels in row order, as (widget id, key into _STATUS_WIDTHS).
_STATUS_LABELS = (
    ("detail-read-state", "read"),
    ("detail-priority", "priority"),
    ("detail-rating", "rating"),
    ("detail-pdf-status", "pdf"),
)

# Cells the one-line row needs: every label at its fixed width plus the 2-cell
# margin after it. The fixed widths keep the row from shifting about as values
# change, but they also stop it shrinking, so in a pane narrower than this the
# last labels would be pushed outside the pane and vanish. Below this width the
# row stacks into a 2x2 grid instead — see `_apply_status_layout`.
_STATUS_ROW_WIDTH = sum(_STATUS_WIDTHS.values()) + 2 * len(_STATUS_WIDTHS)


def _status_label(widget_id: str, width: int) -> Label:
    label = Label("", id=widget_id)
    label.styles.width = width
    return label


# The author block under the title is always this many lines tall, so a long
# author list can't push everything below it around while flicking through
# entries.
_AUTHOR_LINES = 3
_NBSP = "\u00a0"
_DEFAULT_CONTENT_WIDTH = 60

# Breathing room between the text and the scroll bar. The pane's own padding
# sits outside the scroll bar, so without this the longest line of every entry
# ends up jammed against it. Keep in step with the `padding-right` on the
# scrollable children in `EntryDetail.DEFAULT_CSS`.
_SCROLLBAR_GUTTER = 2

# Width of the field-name gutter in the detail body, before the value starts.
_FIELD_LABEL_WIDTH = 12

# A wrapped URL is unreadable and can't be clicked anyway, so URL-valued fields
# are cut to one line with an ellipsis instead of flowing on to the next line.
_URL_PREFIXES = ("http://", "https://", "ftp://", "ftps://", "www.")


def _is_url(value: str) -> bool:
    return value.lower().startswith(_URL_PREFIXES)


def _one_line(value: str, width: int) -> str:
    """*value* cut to *width* cells with a trailing "\u2026" so it never wraps."""
    if width < 2:
        return "\u2026"
    if len(value) <= width:
        return value
    return value[: width - 1] + "\u2026"


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
    content_width: int = _DEFAULT_CONTENT_WIDTH,
) -> str:
    """Build a Rich-formatted string for the main body of the detail pane.

    *colors* is a dict with keys: title, key, required, optional, tag_fg,
    tag_bg, warning.  Values are Rich-compatible color strings (hex or names).
    *content_width* is the pane's usable width: the author block wraps to it
    and URL values are cut to it.
    """
    c = colors
    lines: list[str] = []

    # Title, with the authors directly beneath it
    lines.append(f"[bold {c['title']}]{entry.title or '(no title)'}[/]")
    lines.extend(_author_lines(entry.get_field("author"), content_width))
    lines.append("")

    # Entry type badge
    lines.append(
        f"[dim]@{entry.entry_type}[/dim]  [dim]key:[/dim] [{c['key']}]{entry.key}[/]"
    )
    lines.append("")

    # Key fields
    def field_line(label: str, value: str) -> str:
        if not value:
            return f"[dim]{label:<{_FIELD_LABEL_WIDTH}}[/dim] [dim](empty)[/dim]"
        if _is_url(value):
            value = _one_line(value, content_width - _FIELD_LABEL_WIDTH - 1)
        return f"[{c['required']}]{label:<{_FIELD_LABEL_WIDTH}}[/] {value}"

    standard_fields = [
        ("Year", "year"),
        ("Journal", "journal"),
        ("DOI", "doi"),
        ("URL", "url"),
    ]

    for label, key in standard_fields:
        lines.append(field_line(label, entry.get_field(key)))

    lines.append("")
    lines.append("─" * max(content_width, 10))
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
            if not v:
                continue
            # A key longer than the gutter pushes its value further right.
            gutter = 2 + max(_FIELD_LABEL_WIDTH, len(k)) + 1
            value = _one_line(v, content_width - gutter) if _is_url(v) else v[:80]
            lines.append(f"  [dim]{k:<{_FIELD_LABEL_WIDTH}}[/dim] {value}")

    return "\n".join(lines)


_ABSTRACT_INDENT = 2


def _render_abstract(
    entry: BibEntry,
    content_width: int = _DEFAULT_CONTENT_WIDTH,
) -> str:
    """Render abstract block separately so citation controls can sit above it.

    Wrapped to *content_width* rather than a fixed column, so the text doesn't
    get folded a second time by the pane and left half-indented.
    """
    if not entry.abstract:
        return ""

    indent = " " * _ABSTRACT_INDENT
    body = textwrap.wrap(
        decode_latex(entry.abstract),
        width=max(content_width, _ABSTRACT_INDENT + 20),
        initial_indent=indent,
        subsequent_indent=indent,
    )
    return "\n".join(["[bold]Abstract:[/bold]", *(escape(line) for line in body)])


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
    #detail-meta.-stacked {
        layout: grid;
        grid-size: 2;
        grid-rows: 1 1;
        height: 2;
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
    /* Keep the text clear of the scroll bar — see _SCROLLBAR_GUTTER. */
    #detail-content, #detail-abstract, #detail-citation-preview {
        padding-right: 2;
    }
    """

    def __init__(self, default_csl_style: str = "", **kwargs):
        super().__init__(**kwargs)
        self._entry: BibEntry | None = None
        self._raw_mode: bool = False
        self._pdf_base_dir: str = ""
        self._content_width: int = _DEFAULT_CONTENT_WIDTH
        # None until the first resize, so the first call always applies a layout.
        self._status_stacked: bool | None = None
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
        """Re-lay out the status row and author block when the width changes."""
        self._apply_status_layout(self._current_content_width())
        if (
            self._entry is not None
            and not self._raw_mode
            and self._current_content_width() != self._content_width
        ):
            self._refresh_content()

    def _apply_status_layout(self, width: int) -> None:
        """Keep the status row on one line, or stack it into a 2x2 grid.

        Stacking costs a line of height but is the only way the whole row stays
        inside a narrow pane — the labels are fixed-width so that they hold
        still while flicking through entries, which also means they can't
        shrink to fit. The height stays the same for every entry either way.
        """
        stacked = width < _STATUS_ROW_WIDTH
        if stacked == self._status_stacked:
            return
        self._status_stacked = stacked
        self.query_one("#detail-meta").set_class(stacked, "-stacked")
        for widget_id, key in _STATUS_LABELS:
            label = self.query_one(f"#{widget_id}", Label)
            label.styles.width = "1fr" if stacked else _STATUS_WIDTHS[key]

    def _current_content_width(self) -> int:
        width = self.scrollable_content_region.width
        if not width:
            return _DEFAULT_CONTENT_WIDTH
        return max(width - _SCROLLBAR_GUTTER, 10)

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
            for widget_id, key in _STATUS_LABELS:
                yield _status_label(widget_id, _STATUS_WIDTHS[key])
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
        # Both the abstract and the body below wrap to this, so measure once up
        # front rather than after the abstract has already been rendered.
        self._content_width = self._current_content_width()
        citation_preview = render_citation_preview(e, self._selected_csl_style)
        citation_panel.display = True
        if citation_preview:
            citation_preview_widget.update(citation_preview)
        else:
            citation_preview_widget.update("[dim](unavailable)[/dim]")

        abstract_text = _render_abstract(e, self._content_width)
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
            content.update(_render_entry(e, colors, self._content_width))
