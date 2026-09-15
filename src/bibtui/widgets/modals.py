import copy
import re
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TypeVar

from rich.text import Text

from textual import events, on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DirectoryTree,
    Input,
    Label,
    ListItem,
    ListView,
    LoadingIndicator,
    OptionList,
    Select,
    SelectionList,
    Static,
    Switch,
    TextArea,
)
from textual.widgets._selection_list import Selection
from textual.widgets.option_list import Option

from bibtui import DOCS_URL
from bibtui.bib.citation_preview import available_csl_styles, default_csl_style_key
from bibtui.bib.citekeys import author_year_base
from bibtui.bib.models import COMMON_FIELDS, ENTRY_TYPES, BibEntry
from bibtui.bib.parser import bibtex_str_to_entry, entry_to_bibtex_str
from bibtui.bib.validate import validate_entry
from bibtui.pdf.paths import pdf_link_state
from bibtui.utils.config import Config
from bibtui.utils.dates import DATE_ADDED_KEYS
from bibtui.utils.doi import normalize_doi
from bibtui.utils.filters import FilterPreset, FilterStore
from bibtui.utils.keymap import SAVE
from bibtui.utils.opener import open_with_default_app
from bibtui.widgets.columns import DEFAULT_TABLE_COLUMNS, ColumnSpec

_ModalResult = TypeVar("_ModalResult")


class _BaseModal(ModalScreen[_ModalResult]):
    """Shared base for all dialogs.

    Holds the styling common to every modal — centered on screen, a double
    accent border over the surface colour, and standard padding. Subclasses
    only declare what differs (typically ``width``/``height`` on their
    ``> Vertical`` container) and may override the border colour or padding.
    """

    DEFAULT_CSS = """
    _BaseModal {
        align: center middle;
    }
    _BaseModal > Vertical {
        height: auto;
        border: double $accent;
        background: $surface;
        padding: 1 2;
    }
    """


def _format_age(mtime: float) -> str:
    """Human-readable age string for a file modification time."""
    age = time.time() - mtime
    if age < 60:
        return "just now"
    if age < 3600:
        return f"{int(age / 60)} min ago"
    if age < 86400:
        return f"{int(age / 3600)} hr ago"
    return f"{int(age / 86400)} days ago"


def _report_row_text(app, ok: bool, body: str) -> Text:
    """A ✓/✗ styled report-list row, shared by :class:`PdfImportReviewModal`
    and :class:`BibFileImportReviewModal`: ✓ in the current theme's success
    color, ✗ in its error color, in front of whatever text describes the row."""
    mark = "✓" if ok else "✗"
    color = app.current_theme.success if ok else app.current_theme.error
    return Text(f"{mark} {body}", style=color)


def _import_button_label(n: int) -> str:
    """"Import N Entries" button label, shared by both import-review modals."""
    if not n:
        return "Import"
    return f"Import {n} {'Entry' if n == 1 else 'Entries'}"


def _file_row_label(path: Path) -> str:
    """Row label for a file-picker list: ``name  size  age``, shared by every
    picker that lists files from a directory (:class:`AddPDFModal`,
    :class:`PdfImportPickerModal`, :class:`ImportBibPickerModal`)."""
    stat = path.stat()
    size = stat.st_size
    size_str = (
        f"{size / 1048576:.1f} MB" if size >= 1048576 else f"{size / 1024:.0f} KB"
    )
    return f"{path.name}  [dim]{size_str}  {_format_age(stat.st_mtime)}[/dim]"


class _FileBrowseMixin:
    """Shared browse/filter/choose machinery for a single-file ``ListView``
    picker: list a directory (falling back to ``~/Downloads`` when unset),
    filter by typing, preview the highlighted row on Space, and choose it on
    Enter/`x`. Used by :class:`AddPDFModal` (pick a PDF for one entry) and
    :class:`ImportBibPickerModal` (pick a `.bib` file to import) — the two
    "choose a single file" pickers in the app; :class:`PdfImportPickerModal`
    is a checklist instead and doesn't fit this shape.

    A subclass sets ``_ID_PREFIX`` (its widgets' id prefix, e.g. ``"add"``
    for ``#add-filter``/``#add-hint``/``#add-error``), ``_GLOB`` (e.g.
    ``"*.pdf"``) and ``_NOUN`` (e.g. ``"PDF"``, used in "3 PDFs"), composes a
    bare ``ListView`` plus those three widgets, and implements
    :meth:`_choose_path` for what "choosing" a file actually does. Because
    ``@on`` selectors are literal strings, each subclass still declares thin
    ``@on``-decorated wrappers for its own widget ids that delegate to the
    shared ``_filter_changed``/``_filter_submitted``/``_list_selected``
    methods below.
    """

    # Screen's own AUTO_FOCUS defaults to "*" (first focusable widget —
    # here, the filter Input, since it's composed before the list). Textual
    # applies that during _compose(), before on_mount()'s _focus_initial()
    # runs, so without this the Input would visibly flash focused for one
    # frame before focus jumps to the list. Disabling it here makes
    # _focus_initial() the *only* thing that ever sets initial focus.
    AUTO_FOCUS = ""

    _ID_PREFIX: str = ""
    _GLOB: str = "*"
    _NOUN: str = "file"

    _download_dir: str
    _all_files: list[Path]
    _filtered: list[Path]

    def _wid(self, suffix: str) -> str:
        return f"#{self._ID_PREFIX}-{suffix}"

    def _scan(self) -> None:
        dl = Path(self._download_dir).expanduser()
        hint = self.query_one(self._wid("hint"), Static)
        if not dl.is_dir():
            hint.update(
                f"[dim]Folder not found: {dl}  ·  paste a file or folder path below[/dim]"
            )
            self._all_files = []
        else:
            files = sorted(
                dl.glob(self._GLOB), key=lambda p: p.stat().st_mtime, reverse=True
            )
            self._all_files = files
            hint.update(
                f"[dim]{dl}  ·  {len(files)} {self._NOUN}{'s' if len(files) != 1 else ''}"
                "  ·  paste another folder path to browse elsewhere[/dim]"
            )
        self._filtered = list(self._all_files)
        self._refresh_list()

    def _refresh_list(self) -> None:
        lv = self.query_one(ListView)
        lv.clear()
        for p in self._filtered:
            lv.append(ListItem(Label(_file_row_label(p))))

    def _filter_changed(self, event: Input.Changed) -> None:
        q = event.value.strip().lower()
        self._filtered = (
            [p for p in self._all_files if q in p.name.lower()]
            if q
            else list(self._all_files)
        )
        self._refresh_list()

    def on_mount(self) -> None:
        self._scan()
        self._focus_initial()

    def _focus_initial(self) -> None:
        """Default focus is the first row in the list — so Enter/`x` chooses
        immediately, the common case — not the filter input. `s` jumps to
        the filter from the list, matching the main view's Search key.
        Falls back to the filter when there's nothing to list yet."""
        lv = self.query_one(ListView)
        if self._filtered:
            lv.index = 0
            self.call_after_refresh(lv.focus)
        else:
            self.call_after_refresh(self.query_one(self._wid("filter"), Input).focus)

    def on_key(self, event: events.Key) -> None:
        """Down in the Input moves focus to the list; Up from the first item
        or `s` returns focus to the filter; Space previews, `x` chooses
        (same as Enter)."""
        lv = self.query_one(ListView)
        inp = self.query_one(self._wid("filter"), Input)
        if self.focused is inp and event.key == "down" and self._filtered:
            lv.focus()
            event.stop()
        elif self.focused is lv and event.key == "up" and (lv.index or 0) == 0:
            inp.focus()
            event.stop()
        elif self.focused is lv and event.key == "s":
            inp.focus()
            event.stop()
        elif self.focused is lv and event.key == "space":
            self._preview_selected()
            event.stop()
        elif self.focused is lv and event.key == "x":
            self._confirm()
            event.stop()

    def _preview_selected(self) -> None:
        lv = self.query_one(ListView)
        idx = lv.index
        if idx is None or idx >= len(self._filtered):
            return
        try:
            open_with_default_app(str(self._filtered[idx]))
        except Exception as e:
            self.query_one(self._wid("error"), Static).update(f"Could not open: {e}")

    def _filter_submitted(self, event: Input.Submitted) -> None:
        val = event.value.strip()
        if val:
            expanded = Path(val).expanduser()
            if expanded.is_dir():
                self._download_dir = str(expanded)
                self.query_one(self._wid("filter"), Input).value = ""
                self.query_one(self._wid("error"), Static).update("")
                self._scan()
                return
        self._confirm()

    def _list_selected(self, event: ListView.Selected) -> None:
        idx = self.query_one(ListView).index
        if idx is not None and idx < len(self._filtered):
            self._choose_path(self._filtered[idx])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id and event.button.id.startswith("btn-"):
            self._confirm()

    def _confirm(self) -> None:
        lv = self.query_one(ListView)
        idx = lv.index
        if self._filtered and idx is not None and idx < len(self._filtered):
            self._choose_path(self._filtered[idx])
        else:
            val = self.query_one(self._wid("filter"), Input).value.strip()
            if val:
                self._choose_path(Path(val).expanduser())
            else:
                self.query_one(self._wid("error"), Static).update(
                    "Select a file or enter a path."
                )

    def _choose_path(self, path: Path) -> None:
        """Subclasses decide what "choosing" a file means."""
        raise NotImplementedError

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmModal(_BaseModal[bool]):
    """Generic yes/no confirmation dialog."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    DEFAULT_CSS = """
    ConfirmModal > Vertical {
        width: 50;
        border: double $warning;
    }
    ConfirmModal #btn-yes {
        background: $error;
        color: $text;
    }
    ConfirmModal #btn-no {
        background: $primary;
        color: $text;
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
                yield Button("Yes", id="btn-yes")
                yield Button("No", id="btn-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-yes")

    def action_cancel(self) -> None:
        self.dismiss(False)


class LibraryFetchConfirmModal(_BaseModal[tuple[bool, bool] | None]):
    """Confirm library PDF fetch and choose whether broken links may be overwritten."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    DEFAULT_CSS = """
    LibraryFetchConfirmModal > Vertical {
        width: 50;
    }
    LibraryFetchConfirmModal #overwrite-row {
        layout: horizontal;
        align: left middle;
        margin: 1 0;
        height: 3;
    }
    LibraryFetchConfirmModal #overwrite-switch {
        margin-right: 1;
    }
    LibraryFetchConfirmModal #library-fetch-note {
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]Fetch Missing PDFs[/bold]", classes="modal-title")
            yield Static("Run fetch for entries missing local PDFs?")
            with Horizontal(id="overwrite-row"):
                yield Switch(value=True, id="overwrite-switch")
                yield Label("Overwrite broken links")
            yield Static(
                "Turn off to keep entries with broken file paths untouched.",
                id="library-fetch-note",
            )
            with Horizontal(classes="modal-buttons"):
                yield Button("Start", variant="primary", id="btn-start")
                yield Button("Cancel", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
            return
        overwrite = self.query_one("#overwrite-switch", Switch).value
        self.dismiss((True, overwrite))

    def action_cancel(self) -> None:
        self.dismiss(None)


class DOIModal(_BaseModal[BibEntry | None]):
    """Modal to fetch an entry by DOI."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    DOIModal > Vertical {
        width: 70;
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
        self._fetch_doi(doi)

    @work(thread=True)
    def _fetch_doi(self, doi: str) -> None:
        try:
            from bibtui.bib.doi import fetch_by_doi

            entry = fetch_by_doi(doi)
            self.app.call_from_thread(self._on_fetch_success, entry)
        except Exception as e:  # noqa: BLE001
            self.app.call_from_thread(self._on_fetch_error, str(e))

    def _on_fetch_success(self, entry: BibEntry) -> None:
        status = self.query_one("#doi-status", Static)
        status.set_classes("success")
        status.update(f"Found: {entry.title[:60]}")
        self.app.call_later(self._confirm, entry)

    def _on_fetch_error(self, message: str) -> None:
        status = self.query_one("#doi-status", Static)
        status.set_classes("error")
        status.update(f"Error: {message}")

    def _confirm(self, entry: BibEntry) -> None:
        self.dismiss(entry)

    def action_cancel(self) -> None:
        self.dismiss(None)


class NewEntryChooserModal(_BaseModal["str | None"]):
    """First step of `n`: pick how the new entry should be created.

    Dismisses with one of ``"blank"``, ``"doi"``, ``"pdf"``, ``"bibfile"``,
    ``"paste"``, or ``None`` if canceled. Kept as a single entry point
    (rather than separate top-level keybindings per method) so there's one
    obvious place to start adding a reference from.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
        Binding("1,m", "choose('blank')", show=False),
        Binding("2,d", "choose('doi')", show=False),
        Binding("3,p", "choose('pdf')", show=False),
        Binding("4,v", "choose('paste')", show=False),
        Binding("5,b", "choose('bibfile')", show=False),
    ]

    # (result key, mnemonic letter, title, short description)
    _OPTIONS: list[tuple[str, str, str, str]] = [
        ("doi", "d", "Import by DOI", "Fetch metadata from a DOI"),
        ("pdf", "p", "Import from PDF", "Fetch metadata from PDF files"),
        ("bibfile", "b", "Import .bib File", "Pick a downloaded .bib file"),
        ("paste", "v", "Paste BibTeX", "Paste a raw BibTeX entry"),
        ("blank", "m", "Fill out manually", "Pick a type, fill in fields"),
    ]

    DEFAULT_CSS = """
    NewEntryChooserModal > Vertical {
        width: 68;
    }
    NewEntryChooserModal ListView {
        height: auto;
        border: solid $panel;
    }
    NewEntryChooserModal ListItem {
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]New Entry[/bold]", classes="modal-title")
            with ListView(id="chooser-list"):
                for _key, letter, title, desc in self._OPTIONS:
                    yield ListItem(
                        Label(f"[bold]{letter}[/bold] · {title}  [dim]— {desc}[/dim]")
                    )
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        self.call_after_refresh(self.query_one(ListView).focus)

    @on(ListView.Selected, "#chooser-list")
    def _on_selected(self, event: ListView.Selected) -> None:
        idx = self.query_one(ListView).index
        if idx is not None and idx < len(self._OPTIONS):
            self.dismiss(self._OPTIONS[idx][0])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)

    def action_choose(self, key: str) -> None:
        self.dismiss(key)

    def action_cancel(self) -> None:
        self.dismiss(None)


# Fields the New/Edit entry form never shows as editable inputs: keywords are
# managed separately through the Keywords modal (press `k`).
_FORM_EXCLUDED_FIELDS: set[str] = {"keywords"}

# Optional fields promoted to the top of the optional section (in this order)
# because they are the ones most people want to fill in right away.
_FORM_PROMOTED_FIELDS: list[str] = ["doi", "url", "note"]

# Raw fields the form never shows and must never wipe — auto-managed metadata
# such as the date-added timestamp.
_FORM_HIDDEN_RAW_FIELDS: set[str] = set(DATE_ADDED_KEYS)

# BibEntry attributes that map to real BibTeX content fields — everything except
# keywords and the app-only metadata (rating, read_state, priority). Used when
# editing to know which content fields the form owns and may clear/rewrite.
_FORM_CONTENT_FIELDS: list[str] = [
    "title",
    "author",
    "year",
    "journal",
    "doi",
    "url",
    "abstract",
    "comment",
    "file",
]


class _EntryFormModal(_BaseModal[BibEntry | None]):
    """Shared dynamic BibTeX field form used by New and Edit.

    Renders inputs labelled with the real BibTeX field names for the chosen
    entry type (required fields marked ``*``), driven by
    :data:`bibtui.bib.models.ENTRY_TYPES`, plus a custom-field section for any
    additional field (picked from a common shortlist or typed freely).
    ``doi``, ``url`` and ``note`` are surfaced near the top; ``keywords`` is deliberately
    excluded — it is managed through the Keywords modal.
    """

    BINDINGS = [
        Binding(SAVE, "save", "Write", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    _EntryFormModal > Vertical {
        width: 84;
        max-height: 92%;
    }
    _EntryFormModal #new-fields {
        height: 30;
    }
    _EntryFormModal #type-fields,
    _EntryFormModal #custom-fields {
        height: auto;
    }
    _EntryFormModal Input {
        margin-bottom: 1;
    }
    _EntryFormModal Label {
        color: $accent;
    }
    _EntryFormModal TextArea {
        height: 6;
        margin-bottom: 1;
    }
    _EntryFormModal .type-row {
        height: auto;
        align: left middle;
        margin-bottom: 1;
    }
    _EntryFormModal .type-row Label {
        width: 10;
    }
    _EntryFormModal #required-hint {
        margin-bottom: 1;
        color: $text-muted;
    }
    _EntryFormModal #new-key.auto {
        color: $text-muted;
        text-style: italic;
    }
    _EntryFormModal #key-hint {
        margin-bottom: 1;
    }
    _EntryFormModal .section-label {
        margin-top: 1;
    }
    _EntryFormModal #kw-note {
        color: $text-muted;
        margin-top: 1;
        height: auto;
    }
    _EntryFormModal .custom-row {
        height: auto;
    }
    _EntryFormModal .custom-row Label {
        width: 18;
        content-align: left middle;
        height: 3;
    }
    _EntryFormModal .custom-row Input {
        width: 1fr;
    }
    _EntryFormModal .custom-remove {
        min-width: 4;
        width: 4;
    }
    _EntryFormModal .add-field-row {
        height: auto;
        margin-top: 1;
    }
    _EntryFormModal .add-field-row Input {
        width: 1fr;
    }
    _EntryFormModal #new-error {
        color: $error;
    }
    _EntryFormModal #form-notice {
        color: $text-muted;
        height: auto;
    }
    _EntryFormModal .field-error {
        border: tall $error;
    }
    _EntryFormModal .field-fixed {
        border: tall $success;
    }
    """

    # Only New auto-suggests a cite key; Edit keeps the existing key.
    _autofill_enabled: bool = False

    # "new" hard-blocks missing required fields; "edit" only blocks fields the
    # user emptied this session (see validate_entry / _validation_baseline).
    _validate_mode: str = "new"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_type = self._initial_type()
        # Field values are kept here so they survive an entry-type switch.
        self._values: dict[str, str] = {}
        self._custom_names: list[str] = []
        self._key_touched = False
        # The last value we auto-filled into the cite-key input. Used to tell
        # our own programmatic edits apart from real user typing (the Changed
        # message arrives after any transient flag would have been reset).
        self._auto_key_value = ""

    # -- hooks for subclasses ---------------------------------------------

    def _initial_type(self) -> str:
        return "article"

    def _form_title(self) -> str:
        return "[bold]Entry[/bold]"

    def _compose_key_row(self) -> ComposeResult:
        return iter(())  # no cite-key row by default

    def _focus_after_mount(self) -> None:
        return None

    def _make_entry(self) -> BibEntry | None:
        raise NotImplementedError

    def _validation_baseline(self) -> BibEntry | None:
        """Original entry to compare against (Edit only); None for New."""
        return None

    # -- compose -----------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._form_title(), classes="modal-title")
            with VerticalScroll(id="new-fields"):
                with Horizontal(classes="type-row"):
                    yield Label("Type")
                    # Include the current type even if it isn't one of the
                    # built-ins (e.g. editing an existing @unpublished entry) —
                    # Select rejects a value that isn't among its options.
                    types = list(ENTRY_TYPES)
                    if self._current_type not in ENTRY_TYPES:
                        types.append(self._current_type)
                    yield Select(
                        [(t, t) for t in types],
                        value=self._current_type,
                        allow_blank=False,
                        id="new-type",
                    )
                yield Static("", id="required-hint")
                yield from self._compose_key_row()
                yield Vertical(id="type-fields")
                yield Label("Custom fields", classes="section-label")
                yield Vertical(id="custom-fields")
                with Horizontal(classes="add-field-row"):
                    yield Select(
                        [(f, f) for f in COMMON_FIELDS],
                        prompt="Common field…",
                        id="add-common",
                    )
                    yield Input(placeholder="or type a field name…", id="add-name")
                    yield Button("Add", id="btn-add")
                yield Static(
                    "[dim]Keywords are managed separately — press "
                    "[bold]k[/bold] to edit them.[/dim]",
                    id="kw-note",
                )
            yield Static("", id="form-notice")
            yield Static("", id="new-error")
            with Horizontal(classes="modal-buttons"):
                yield Button("Write", variant="primary", id="btn-save")
                yield Button("Cancel", id="btn-cancel")

    async def on_mount(self) -> None:
        await self._rebuild_type_fields()
        cf = self.query_one("#custom-fields", Vertical)
        for name in self._custom_names:
            await cf.mount(self._make_custom_row(name))
        self._update_required_hint()
        self._refresh_common_field_options()
        self._focus_after_mount()

    # -- field helpers -----------------------------------------------------

    @staticmethod
    def _sanitize(name: str) -> str:
        return re.sub(r"[^a-z0-9]", "", (name or "").strip().lower())

    @staticmethod
    def _field_id(name: str) -> str:
        return f"field-{name}"

    def _iter_field_widgets(self):
        """Yield every value-carrying field widget, in DOM order."""
        for widget in self.query("Input, TextArea"):
            wid = widget.id or ""
            if wid.startswith("field-"):
                yield widget

    @staticmethod
    def _widget_value(widget) -> str:
        return widget.text if isinstance(widget, TextArea) else widget.value

    def _current_field_names(self) -> set[str]:
        return {w.id.removeprefix("field-") for w in self._iter_field_widgets()}

    def _snapshot_values(self) -> None:
        for widget in self._iter_field_widgets():
            name = widget.id.removeprefix("field-")
            self._values[name] = self._widget_value(widget)

    def _ordered_type_fields(self) -> list[tuple[str, bool]]:
        """Return ``(field_name, is_required)`` for the current type, in order.

        Required fields first, then the promoted fields (``doi``, ``url``,
        ``note``), then the type's remaining optional fields. Keywords and
        already-added custom fields are omitted.
        """
        spec = ENTRY_TYPES.get(self._current_type, {})
        required = [
            n for n in spec.get("required", []) if n not in _FORM_EXCLUDED_FIELDS
        ]
        optional = [
            n for n in spec.get("optional", []) if n not in _FORM_EXCLUDED_FIELDS
        ]
        promoted = [n for n in _FORM_PROMOTED_FIELDS if n not in required]
        rest = [n for n in optional if n not in promoted]
        custom = set(self._custom_names)
        result: list[tuple[str, bool]] = []
        seen: set[str] = set()
        for name in [*required, *promoted, *rest]:
            if name in seen or name in custom:
                continue
            seen.add(name)
            result.append((name, name in required))
        return result

    def _make_field_widgets(self, name: str, required: bool) -> list:
        label = f"{name.capitalize()}{' *' if required else ''}"
        fid = self._field_id(name)
        value = self._values.get(name, "")
        if name == "abstract":
            return [Label(label), TextArea(value, id=fid)]
        return [Label(label), Input(value=value, id=fid)]

    def _make_custom_row(self, name: str) -> Horizontal:
        return Horizontal(
            Label(f"{name}"),
            Input(value=self._values.get(name, ""), id=self._field_id(name)),
            Button("✕", id=f"rm-{name}", classes="custom-remove"),
            classes="custom-row",
            id=f"custom-row-{name}",
        )

    async def _rebuild_type_fields(self) -> None:
        self._snapshot_values()
        container = self.query_one("#type-fields", Vertical)
        # Await the removal so the old widgets are gone before the new ones are
        # mounted — otherwise reused field ids (e.g. field-author) collide.
        await container.remove_children()
        widgets: list = []
        for name, required in self._ordered_type_fields():
            widgets += self._make_field_widgets(name, required=required)
        if widgets:
            await container.mount(*widgets)

    def _refresh_common_field_options(self) -> None:
        """Limit the common-field dropdown to fields not already in the form."""
        try:
            select = self.query_one("#add-common", Select)
        except Exception:
            return
        present = {name for name, _ in self._ordered_type_fields()}
        present.update(self._custom_names)
        available = [f for f in COMMON_FIELDS if f not in present]
        select.set_options((f, f) for f in available)

    def _update_required_hint(self) -> None:
        required = [
            n
            for n in ENTRY_TYPES.get(self._current_type, {}).get("required", [])
            if n not in _FORM_EXCLUDED_FIELDS
        ]
        if required:
            text = "Required: " + ", ".join(required)
        else:
            text = "No required fields for this type."
        self.query_one("#required-hint", Static).update(text)

    # -- cite key auto-suggest --------------------------------------------

    def _field_value(self, name: str) -> str:
        try:
            widget = self.query_one(f"#{self._field_id(name)}")
        except Exception:
            return ""
        return self._widget_value(widget)

    def _set_key_hint(self, *, auto: bool) -> None:
        try:
            hint = self.query_one("#key-hint", Static)
        except Exception:
            return
        if auto:
            hint.update(
                "[dim]✎ auto-generated from author + year — edit to override[/dim]"
            )
        else:
            hint.update("[dim]custom cite key[/dim]")

    def _autofill_key(self) -> None:
        author = self._field_value("author")
        year = self._field_value("year")
        if not author and not year:
            return
        key_input = self.query_one("#new-key", Input)
        self._auto_key_value = author_year_base(author, year)
        key_input.value = self._auto_key_value
        key_input.add_class("auto")
        self._set_key_hint(auto=True)

    # -- custom fields -----------------------------------------------------

    def _add_custom_field(self, raw_name: str) -> None:
        name = self._sanitize(raw_name)
        add_name = self.query_one("#add-name", Input)
        if not name or name in _FORM_EXCLUDED_FIELDS:
            add_name.value = ""
            return
        if name in self._current_field_names():
            # Already present (a type field or a prior custom field) — focus it.
            try:
                self.query_one(f"#{self._field_id(name)}").focus()
            except Exception:
                pass
            add_name.value = ""
            return
        self._custom_names.append(name)
        self.query_one("#custom-fields", Vertical).mount(self._make_custom_row(name))
        add_name.value = ""
        self._refresh_common_field_options()

    def _remove_custom_field(self, name: str) -> None:
        if name in self._custom_names:
            self._custom_names.remove(name)
        self._values.pop(name, None)
        try:
            self.query_one(f"#custom-row-{name}").remove()
        except Exception:
            pass
        self._refresh_common_field_options()

    # -- events ------------------------------------------------------------

    @on(Select.Changed, "#new-type")
    async def _on_type_changed(self, event: Select.Changed) -> None:
        new_type = str(event.value)
        # Ignore the spurious Changed the Select posts for its initial value;
        # on_mount already builds the fields for the starting type.
        if new_type == self._current_type:
            return
        self._current_type = new_type
        await self._rebuild_type_fields()
        self._update_required_hint()
        self._refresh_common_field_options()

    @on(Select.Changed, "#add-common")
    def _on_common_field_chosen(self, event: Select.Changed) -> None:
        # A real pick is always one of our string options; the blank/cleared
        # state is a non-string sentinel (whose name differs across Textual
        # versions), so filter by type rather than comparing to a sentinel.
        if not isinstance(event.value, str):
            return
        self._add_custom_field(event.value)
        # Reset the dropdown back to its prompt. Assigning the sentinel directly
        # is rejected by the value validator; clear() is the supported API.
        event.select.clear()

    @on(Input.Submitted, "#add-name")
    def _on_add_name_submitted(self, event: Input.Submitted) -> None:
        self._add_custom_field(event.value)

    @on(Input.Changed)
    def _on_input_changed(self, event: Input.Changed) -> None:
        if not self._autofill_enabled:
            return
        wid = event.input.id or ""
        if wid == "new-key":
            # Ignore the echo of our own autofill; anything else is a real edit.
            if event.input.value == self._auto_key_value:
                return
            self._key_touched = True
            event.input.remove_class("auto")
            self._set_key_hint(auto=False)
            return
        if wid in ("field-author", "field-year") and not self._key_touched:
            self._autofill_key()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "btn-cancel":
            self.dismiss(None)
        elif bid == "btn-save":
            self._save()
        elif bid == "btn-add":
            self._add_custom_field(self.query_one("#add-name", Input).value)
        elif bid.startswith("rm-"):
            self._remove_custom_field(bid[len("rm-") :])

    def _collect_into(self, entry: BibEntry) -> None:
        """Write every non-empty form field into *entry* by its real name."""
        for widget in self._iter_field_widgets():
            name = widget.id.removeprefix("field-")
            value = self._widget_value(widget).strip()
            if value:
                entry.set_field(name, value)

    # -- validation / submit ----------------------------------------------

    def _clear_field_marks(self) -> None:
        for widget in self.query("Input, TextArea"):
            widget.remove_class("field-error")
            widget.remove_class("field-fixed")
        self.query_one("#new-error", Static).update("")
        self.query_one("#form-notice", Static).update("")

    def _field_widget(self, name: str):
        target_id = "new-key" if name == "key" else self._field_id(name)
        try:
            return self.query_one(f"#{target_id}")
        except Exception:
            return None

    def _show_blocking(self, errors: list[dict]) -> None:
        messages: list[str] = []
        for err in errors:
            messages.append(err["message"])
            widget = self._field_widget(err["field"])
            if widget is not None:
                widget.add_class("field-error")
        self.query_one("#new-error", Static).update("\n".join(messages))

    def _apply_fixes_to_form(
        self, normalized: BibEntry, fixes: list[str], warnings: list[str]
    ) -> None:
        for widget in self._iter_field_widgets():
            name = widget.id.removeprefix("field-")
            new_value = normalized.get_field(name)
            if self._widget_value(widget) != new_value:
                if isinstance(widget, TextArea):
                    widget.load_text(new_value)
                else:
                    widget.value = new_value
                widget.add_class("field-fixed")
        notice = "Auto-fixed — " + "; ".join(fixes)
        if warnings:
            notice += "  ⚠ " + "; ".join(warnings)
        notice += ".  Review, then press Write again to confirm."
        self.query_one("#form-notice", Static).update(notice)

    def _save(self) -> None:
        entry = self._make_entry()
        if entry is None:
            return
        self._clear_field_marks()
        result = validate_entry(
            entry, mode=self._validate_mode, baseline=self._validation_baseline()
        )
        if result.blocking_errors:
            self._show_blocking(result.blocking_errors)
            return
        # Re-validation is idempotent, so applying fixes into the form and
        # returning gives the user a chance to review; the next Write finds
        # nothing left to fix and goes through.
        if result.applied_fixes:
            self._apply_fixes_to_form(
                result.entry, result.applied_fixes, result.warnings
            )
            return
        if result.warnings:
            self.app.notify(
                "\n".join(result.warnings), severity="warning", timeout=6
            )
        self.dismiss(result.entry)

    def action_save(self) -> None:
        self._save()

    def action_cancel(self) -> None:
        self.dismiss(None)


class EditModal(_EntryFormModal):
    """Edit an existing entry's BibTeX fields, under their real field names.

    Shows the entry's fields for its type plus any extra fields it already has.
    Keywords, rating, read state and priority are managed elsewhere and are
    preserved untouched. The cite key is not editable here.
    """

    def __init__(self, entry: BibEntry, **kwargs) -> None:
        self._entry = entry
        super().__init__(**kwargs)
        # Seed the form with the entry's existing content fields…
        for name in _FORM_CONTENT_FIELDS:
            if name in _FORM_EXCLUDED_FIELDS:
                continue
            value = entry.get_field(name)
            if value:
                self._values[name] = value
        # …and any custom / non-standard fields it carries, except the
        # auto-managed ones (e.g. date-added) which stay hidden and untouched.
        for key, value in entry.raw_fields.items():
            if key in _FORM_EXCLUDED_FIELDS or key in _FORM_HIDDEN_RAW_FIELDS:
                continue
            if value:
                self._values[key] = value
        # Fields the entry has that aren't part of this type's template become
        # custom rows so they stay editable under their real names.
        template = {name for name, _ in self._ordered_type_fields()}
        self._custom_names = [name for name in self._values if name not in template]

    _validate_mode = "edit"

    def _initial_type(self) -> str:
        return self._entry.entry_type

    def _form_title(self) -> str:
        return f"[bold]Edit Entry[/bold]  [dim]{self._entry.key}[/dim]"

    def _focus_after_mount(self) -> None:
        inputs = list(self.query("#type-fields Input"))
        if inputs:
            self.call_after_refresh(inputs[0].focus)

    def _validation_baseline(self) -> BibEntry | None:
        return self._entry

    def _make_entry(self) -> BibEntry | None:
        # Build a candidate copy — the original stays untouched until a
        # successful, validated write, so a blocked save never mutates it.
        entry = copy.deepcopy(self._entry)
        entry.entry_type = self._current_type
        # Clear the content fields this form owns, then rewrite them from the
        # inputs. Keywords and metadata (rating/read_state/priority) are left
        # untouched on the copy.
        for name in _FORM_CONTENT_FIELDS:
            if name not in _FORM_EXCLUDED_FIELDS:
                entry.set_field(name, "")
        # Keep hidden auto-managed raw fields (e.g. date-added); rebuild the
        # rest from the form inputs.
        entry.raw_fields = {
            k: v for k, v in entry.raw_fields.items() if k in _FORM_HIDDEN_RAW_FIELDS
        }
        self._collect_into(entry)
        return entry


class NewEntryModal(_EntryFormModal):
    """Create a new BibTeX entry from scratch.

    The user picks an entry type; the form shows that type's fields under their
    real BibTeX names (required marked ``*``), with ``doi``/``note`` near the
    top and a custom-field section at the bottom. The cite key is auto-suggested
    from author + year until the user edits it manually.
    """

    _autofill_enabled = True

    def _form_title(self) -> str:
        return "[bold]New Entry[/bold]"

    def _compose_key_row(self) -> ComposeResult:
        yield Label("Cite key *")
        yield Input(id="new-key")
        yield Static(
            "[dim]✎ auto-generated from author + year — edit to override[/dim]",
            id="key-hint",
        )

    def _focus_after_mount(self) -> None:
        # The cite key is auto-generated, so start the cursor in the first
        # content field (typically author) instead of the key input.
        inputs = list(self.query("#type-fields Input"))
        target = inputs[0] if inputs else self.query_one("#new-key", Input)
        self.call_after_refresh(target.focus)

    def _make_entry(self) -> BibEntry | None:
        # Key/field validation is handled centrally by validate_entry in _save.
        key = self.query_one("#new-key", Input).value.strip()
        entry = BibEntry(key=key, entry_type=self._current_type)
        self._collect_into(entry)
        return entry


class KeywordsModal(_BaseModal["tuple[str, set[str]] | None"]):
    """Keyword picker: select from all bib-wide keywords, add new ones."""

    BINDINGS = [
        Binding(SAVE, "save", "Write", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    KeywordsModal > Vertical {
        width: 70;
        height: 80%;
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
            yield PreviewSelectionList(id="kw-list")
            yield Static(
                "[dim]Esc close · Enter add new (in filter)  |  ↓/↑ navigate · "
                "Enter/x toggle · ⌫ delete everywhere[/dim]",
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
        elif self.focused is sl and event.key == "backspace":
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

    def _on_delete_confirmed(self, confirmed: bool | None, kw: str) -> None:
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

    def action_save(self) -> None:
        self._save()

    def action_cancel(self) -> None:
        self.dismiss(None)


class SettingsModal(_BaseModal["Config | None"]):
    """Settings dialog — currently just the PDF base directory."""

    BINDINGS = [
        Binding(SAVE, "save", "Write", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    SettingsModal > Vertical {
        width: 70;
    }
    SettingsModal Input {
        margin-bottom: 1;
    }
    SettingsModal .setting-row {
        height: auto;
        align: left middle;
        margin-bottom: 1;
    }
    SettingsModal .setting-row Label {
        width: 1fr;
    }
    """

    def __init__(self, config: Config, **kwargs):
        super().__init__(**kwargs)
        self._config = config
        self._citation_styles = available_csl_styles()
        configured = (self._config.default_citation_style or "").strip()
        style_keys = {key for _label, key in self._citation_styles}
        fallback = default_csl_style_key()
        if configured and configured in style_keys:
            self._selected_style = configured
        elif fallback in style_keys:
            self._selected_style = fallback
        elif self._citation_styles:
            self._selected_style = self._citation_styles[0][1]
        else:
            self._selected_style = fallback

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]Settings[/bold]", classes="modal-title")
            yield Label("PDF base directory")
            yield Static(
                "[dim]Filenames in the file field are resolved relative to this path.[/dim]"
            )
            yield Input(
                value=self._config.pdf_base_dir,
                placeholder="/home/user/Papers",
                id="pdf-base-dir",
            )
            yield Static("")

            yield Label("Unpaywall email")
            yield Static(
                "[dim]Used for open-access PDF lookup via Unpaywall — no registration needed.[/dim]"
            )
            yield Input(
                value=self._config.unpaywall_email,
                placeholder="me@example.com",
                id="unpaywall-email",
            )
            yield Static("")

            yield Label("OpenAlex API key (optional)")
            yield Static(
                "[dim]Used for optional OpenAlex PDF lookup. API key is free and highly recommended. https://openalex.org/[/dim]"
            )
            yield Input(
                value=self._config.openalex_api_key,
                placeholder="...",
                id="openalex-api-key",
            )
            yield Static("")

            yield Label("PDF download directory")
            yield Static(
                "[dim]PDFs listed when you press [bold]p[/bold] then [bold]a[/bold] to add an existing PDF. Defaults to ~/Downloads.[/dim]"
            )
            yield Input(
                value=self._config.pdf_download_dir,
                placeholder=str(__import__("pathlib").Path.home() / "Downloads"),
                id="pdf-download-dir",
            )
            yield Static("")

            yield Label("Auto-fetch PDF on import")
            yield Static(
                "[dim]Automatically fetch the PDF after importing an entry by DOI or paste.[/dim]"
            )
            with Horizontal(classes="setting-row"):
                yield Switch(value=self._config.auto_fetch_pdf, id="auto-fetch-pdf")
            yield Static("")

            yield Label("Check for updates on startup")
            yield Static(
                "[dim]Checks PyPI at most once per day in the background and notifies when a newer stable release is available.[/dim]"
            )
            with Horizontal(classes="setting-row"):
                yield Switch(
                    value=self._config.check_for_updates, id="check-for-updates"
                )

            yield Static("")
            yield Label("Default citation style")
            yield Static(
                "[dim]Used as the default selection in the citation preview dropdown.[/dim]"
            )
            yield Select(
                self._citation_styles,
                allow_blank=False,
                value=self._selected_style,
                id="default-citation-style",
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
        self._config.openalex_api_key = self.query_one(
            "#openalex-api-key", Input
        ).value.strip()
        self._config.pdf_download_dir = self.query_one(
            "#pdf-download-dir", Input
        ).value.strip()
        self._config.auto_fetch_pdf = self.query_one("#auto-fetch-pdf", Switch).value
        self._config.check_for_updates = self.query_one(
            "#check-for-updates", Switch
        ).value
        selected_style = self.query_one("#default-citation-style", Select).value
        if isinstance(selected_style, str):
            self._config.default_citation_style = selected_style

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-save":
            self._collect()
            self.dismiss(self._config)

    def on_input_submitted(self, _: Input.Submitted) -> None:
        self._collect()
        self.dismiss(self._config)

    def action_save(self) -> None:
        self._collect()
        self.dismiss(self._config)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ColumnConfigModal(_BaseModal["list[str] | None"]):
    """Choose which entry-table columns are shown and in what order.

    Configures the read-only browsing table (left pane / maximized "Max table"
    view) — not the entry-editing forms. Space toggles a column on/off;
    Shift+↑/↓ (or the ▲/▼ buttons) reorder the highlighted column. The result
    is the ordered list of enabled column keys.
    """

    BINDINGS = [
        Binding(SAVE, "save", "Write", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    ColumnConfigModal > Vertical {
        width: 60;
        height: 80%;
    }
    ColumnConfigModal OptionList {
        height: 1fr;
        border: solid $panel;
    }
    ColumnConfigModal #col-hints {
        height: auto;
        margin-top: 1;
        color: $text-muted;
    }
    ColumnConfigModal .move-buttons {
        height: auto;
        margin-bottom: 1;
    }
    """

    def __init__(
        self, available: list[ColumnSpec], active_keys: list[str], **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self._names: dict[str, str] = {s.key: s.name for s in available}
        # Enabled columns first (in their saved order), then the rest.
        active = [k for k in active_keys if k in self._names]
        rest = [s.key for s in available if s.key not in active]
        self._order: list[str] = active + rest
        self._active: set[str] = set(active)

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]Configure Table Columns[/bold]", classes="modal-title")
            yield OptionList(id="col-list")
            yield Static(
                "[dim]● shown · ○ hidden — Space toggle · Shift+↑/↓ move · "
                "sets the entry table view[/dim]",
                id="col-hints",
            )
            with Horizontal(classes="move-buttons"):
                yield Button("▲ Up", id="btn-up")
                yield Button("▼ Down", id="btn-down")
                yield Button("Reset", id="btn-reset")
            with Horizontal(classes="modal-buttons"):
                yield Button("Write", variant="primary", id="btn-save")
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        self._rebuild(0)
        self.call_after_refresh(self.query_one("#col-list", OptionList).focus)

    def _option_text(self, key: str) -> Text:
        """Style a row by state: a filled marker + theme accent when shown,
        a hollow marker + dimmed text when hidden (color *and* shape so the
        state reads without relying on color alone)."""
        name = self._names.get(key, key)
        if key in self._active:
            color = self.app.current_theme.success
            return Text(f"● {name}", style=f"bold {color}")
        return Text(f"○ {name}", style="dim")

    def _rebuild(self, highlight: int) -> None:
        ol = self.query_one("#col-list", OptionList)
        ol.clear_options()
        for key in self._order:
            ol.add_option(Option(self._option_text(key)))
        if self._order:
            ol.highlighted = max(0, min(highlight, len(self._order) - 1))

    @property
    def _highlighted_index(self) -> int:
        highlighted = self.query_one("#col-list", OptionList).highlighted
        return highlighted if highlighted is not None else -1

    def _toggle(self, index: int) -> None:
        if not 0 <= index < len(self._order):
            return
        key = self._order[index]
        if key in self._active:
            self._active.discard(key)
        else:
            self._active.add(key)
        self._rebuild(index)

    def _move(self, index: int, delta: int) -> None:
        target = index + delta
        if not (0 <= index < len(self._order) and 0 <= target < len(self._order)):
            return
        self._order[index], self._order[target] = (
            self._order[target],
            self._order[index],
        )
        self._rebuild(target)

    def _reset(self) -> None:
        rest = [k for k in self._order if k not in DEFAULT_TABLE_COLUMNS]
        self._order = list(DEFAULT_TABLE_COLUMNS) + rest
        self._active = set(DEFAULT_TABLE_COLUMNS)
        self._rebuild(0)

    def on_key(self, event: events.Key) -> None:
        if event.key == "space":
            self._toggle(self._highlighted_index)
            event.stop()
        elif event.key == "shift+up":
            self._move(self._highlighted_index, -1)
            event.stop()
        elif event.key == "shift+down":
            self._move(self._highlighted_index, 1)
            event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-cancel":
            self.dismiss(None)
        elif bid == "btn-save":
            self._save()
        elif bid == "btn-up":
            self._move(self._highlighted_index, -1)
        elif bid == "btn-down":
            self._move(self._highlighted_index, 1)
        elif bid == "btn-reset":
            self._reset()

    def _save(self) -> None:
        chosen = [k for k in self._order if k in self._active]
        if not chosen:
            self.app.notify("Select at least one column.", severity="warning")
            return
        self.dismiss(chosen)

    def action_save(self) -> None:
        self._save()

    def action_cancel(self) -> None:
        self.dismiss(None)


# Layout constants for the keybindings reference. Keys are rendered in a
# fixed-width gutter so every description starts at the same column regardless
# of how long the key combo is.
_HELP_KEY_WIDTH = 12
_HELP_GAP = 1
_HELP_DESC_INDENT = 2 + _HELP_KEY_WIDTH + _HELP_GAP
_HELP_HEADER_WIDTH = 50

# Each section is (title, items). An item is one of:
#   (key, desc)      -> a key row (key rendered bold in the gutter)
#   (None, note)     -> a dim note, aligned under the description column
#   (line,)          -> a free-form line (markup allowed), indented 2 spaces
_HELP_SECTIONS = [
    (
        "Core",
        [
            ("q", "Quit"),
            ("w", "Write"),
            ("s", "Search"),
            ("f", "Filters — pick, save, edit or delete a saved filter"),
            ("e", "Edit entry (field form or raw BibTeX)"),
            ("k", "Edit keywords"),
            ("m", "Maximize/restore table pane"),
            (None, "Press m again to restore split view."),
            ("< / >", "Grow / shrink the detail pane (5% steps, saved)"),
            ("v", "Toggle raw / formatted view"),
        ],
    ),
    (
        "Copy",
        [
            ("ctrl+c / ⌘c", "Copy selected text (or cite key if none focused)"),
            (None, "Copy uses the OS clipboard tool, falling back to OSC 52"),
            (None, "Default copy variant for entries: cite key"),
            ("Shift+c", "Copy formatted citation (current citation style)"),
            (None, "Alternative copy variant: rendered citation text"),
            (None, "Citation styles are loaded from ~/.config/bibtui/csl"),
            (None, "Add more styles: github.com/citation-style-language/styles"),
            ("ctrl+y", "Copy current BibTeX entry"),
            (None, "Also: ctrl+shift+c / ⌘⇧c (terminal-dependent)"),
            (
                None,
                "⌘ shortcuts need a Kitty-protocol terminal — see Keybindings "
                "in the online docs for details",
            ),
        ],
    ),
    (
        "Add new entry",
        [
            ("n", "New entry — choose how:"),
            (None, "  m  Fill out manually — pick a type, fill in the fields"),
            (None, "  d  Import by DOI — fetches metadata online"),
            (None, "  p  Import from PDF — finds a DOI/arXiv id, reports the"),
            (None, "     outcome per file before writing anything"),
            (None, "  b  Import .bib File — one entry is added directly;"),
            (None, "     several show a report, DOI duplicates are skipped"),
            (None, "  v  Paste BibTeX — from clipboard"),
            (None, "All methods reject duplicate cite keys."),
            ("ctrl+v", "Also auto-detects a pasted BibTeX entry anywhere"),
        ],
    ),
    (
        "Delete entry",
        [
            ("Del / ⌫", "Delete the selected entry (confirmation required)"),
        ],
    ),
    (
        "Keywords modal",
        [
            ("Enter", "Add the typed keyword (while the filter is focused)"),
            ("Enter / x", "Toggle the highlighted keyword (while the list is focused)"),
            ("⌫", "Delete highlighted keyword from all entries"),
            ("↓ / ↑", "Move between filter and list"),
        ],
    ),
    (
        "Filters modal",
        [
            ("0", "Select 'All entries' (clears the active filter)"),
            ("1 – 9", "Jump straight to that saved filter"),
            ("Enter", "Select the highlighted row"),
            ("w", "Write the current search as a new (or updated) filter"),
            ("e", "Edit the highlighted filter's name/query"),
            ("d", "Delete the highlighted filter (confirmation required)"),
            (None, "Deleting always drops back to 'All entries', even if"),
            (None, "the deleted filter wasn't the active one."),
            (None, "'All entries' (row 0) can't be deleted."),
            (None, "The active filter is marked ● and highlighted on open."),
            (
                None,
                "A filter narrows the library; the search box then refines "
                "further within it.",
            ),
            (None, "Esc in the main view clears only the search — the active"),
            (None, "filter stays on until you pick a different one here."),
        ],
    ),
    (
        "Entry state",
        [
            ("r", "Cycle read state"),
            ("u", "Cycle urgency"),
            ("␣", "Show PDF"),
            ("b", "Open URL in browser (validates http/https)"),
            ("Shift+b", "Search OpenAlex (title first, then DOI)"),
        ],
    ),
    (
        "PDF actions",
        [
            ("p", "PDF actions — choose:"),
            (None, "  o  Open — open the linked PDF"),
            (None, "  f  Fetch — download the open-access PDF automatically"),
            (None, "  a  Add — link an existing PDF from disk"),
            (None, "  c  Copy PDF — copy the file to the clipboard"),
            (None, "  p  Copy path — copy the file's path as text"),
            (None, "  d  Delete — remove the file and unlink it"),
            (None, "Actions that don't apply to the entry's current PDF state are grayed out."),
        ],
    ),
    (
        "Fetch PDF",
        [
            ("Sources tried in order:",),
            ("[bold]1.[/bold] arXiv      — arXiv DOI or arxiv.org URL",),
            ("[bold]2.[/bold] Unpaywall  — OA by DOI (set email in Ctrl+P)",),
            ("[bold]3.[/bold] Direct URL — entry URL pointing to a PDF",),
            ("PDF saved to base directory from Settings.",),
            ("[dim]Some publishers block automated downloads.[/dim]",),
        ],
    ),
    (
        "Library actions",
        [
            ("ctrl+p / ⌘p", "Open command palette"),
            ("[bold]Table: Configure columns[/bold]",),
            (None, "Choose which columns show and their order; saved to config."),
            ("[bold]Library: Fetch missing PDFs[/bold]",),
            (None, "Shows a toggle for: Overwrite broken links."),
            ("[bold]Library: Unify citekeys (AuthorYear)[/bold]",),
            (None, "Entries already matching AuthorYear are left unchanged."),
            (None, "Changing citekeys may break existing LaTeX documents."),
            ("[bold]Check for updates[/bold]",),
            (None, "Checks PyPI for a newer bibtui release."),
        ],
    ),
    (
        "Rating",
        [
            ("1 – 5", "Set star rating"),
            ("0", "Mark unrated"),
        ],
    ),
    (
        "Other",
        [
            ("?", "Show this help"),
            ("ctrl+d", "Open the online documentation in your browser"),
            ("ctrl+p / ⌘p", "Command palette (Settings + Library actions)"),
            ("maximize", "(palette) maximize focused pane"),
            ("Esc", "Clear search / close modal"),
            (None, "In all modals: Ctrl+S / ⌘S = Write/Save, Esc = Cancel"),
        ],
    ),
    (
        "Sorting",
        [
            ("Click any column header to sort by that column.",),
            ("Click the same header again to reverse the order.",),
            (
                "Active sort column is marked with "
                "[bold]▲[/bold] (asc) or [bold]▼[/bold] (desc).",
            ),
            (
                "Default cols: [bold]◉[/bold] state  [bold]![/bold] prio  "
                "[bold]◫[/bold] PDF  [bold]↗[/bold] URL  Type  Year  "
                "Author  Journal  Title  Added  [bold]★[/bold]",
            ),
            (
                "[dim]Customize via Ctrl+P → Table: Configure columns.[/dim]",
            ),
        ],
    ),
]


def _build_help_keys() -> str:
    """Render the keybindings reference with a consistent key/description column."""
    lines: list[str] = []
    for index, (title, items) in enumerate(_HELP_SECTIONS):
        if index:
            lines.append("")
        dashes = "─" * max(3, _HELP_HEADER_WIDTH - len(title) - 4)
        lines.append(f"[bold]── {title} {dashes}[/bold]")
        for item in items:
            if len(item) == 1:
                lines.append("  " + item[0])
            elif item[0] is None:
                lines.append(" " * _HELP_DESC_INDENT + f"[dim]{item[1]}[/dim]")
            else:
                key, desc = item
                pad = _HELP_KEY_WIDTH + _HELP_GAP - len(key)
                lines.append("  " + f"[bold]{key}[/bold]" + " " * pad + desc)
    return "\n".join(lines)


class HelpModal(_BaseModal[None]):
    """Keybinding reference overlay."""

    BINDINGS = [
        Binding("escape", "dismiss_help", "Close", show=False),
        Binding("?", "dismiss_help", "Close", show=False),
    ]
    DEFAULT_CSS = """
    HelpModal > Vertical {
        width: 90; height: 80%;
    }
    HelpModal VerticalScroll { height: 1fr; }
    HelpModal #help-about { margin-bottom: 1; color: $text-muted; }
    """

    def _make_about(self) -> str:
        try:
            from bibtui import __version__

            version = __version__
        except Exception:
            version = "unknown"
        return (
            f"[bold]bibtui[/bold] v{version}  —  BibTeX TUI\n"
            "[dim]Author:[/dim] Thomas Gölles\n"
            f"[dim]Docs:[/dim] {DOCS_URL}  [dim](press ctrl+d to open)[/dim]\n"
            "[dim]Repo:[/dim]   https://github.com/tgoelles/bib_tui"
        )

    _SEARCH = """\
[bold]── Plain text ────────────────────────[/bold]
  Searches title, author, keywords, and key.
  Multiple tokens are ANDed (AND keyword optional).
  Quote a value to include a space: [dim]k:"sea ice"[/dim]

[bold]── Field prefixes ────────────────────[/bold]
  [bold]a:[/bold] / [bold]author:[/bold]      filter by author
  [bold]t:[/bold] / [bold]title:[/bold]       filter by title
  [bold]j:[/bold] / [bold]journal:[/bold]     filter by journal
  [bold]k:[/bold] / [bold]kw:[/bold]          filter by keyword
  [bold]y:[/bold] / [bold]year:[/bold]        filter by year, range or comparison
  [bold]u:[/bold] / [bold]url:[/bold]         filter by URL
  [bold]c:[/bold] / [bold]citekey:[/bold]     filter by cite key
  [bold]r:[/bold] / [bold]state:[/bold]       filter by read state
  [bold]pr:[/bold] / [bold]urgency:[/bold]    filter by urgency

[bold]── Year filters ──────────────────────[/bold]
  [dim]y:2015-2023[/dim]                closed range
  [dim]y:2015-[/dim]                    2015 or later
  [dim]y:-2015[/dim]                    up to 2015
  [dim]y:>2015[/dim] / [dim]y:>=2015[/dim]        greater than / or equal
  [dim]y:<2015[/dim] / [dim]y:<=2015[/dim]        less than / or equal

[bold]── Examples ──────────────────────────[/bold]
  [dim]glacier[/dim]                    all fields
  [dim]a:smith t:glacier[/dim]          combined
  [dim]j:nature AND y:2025[/dim]        journal + year
  [dim]k:ice a:jones[/dim]              keyword + author
  [dim]c:smith2020[/dim]                exact cite key search
  [dim]r:to-read[/dim]                  entries still to read
  [dim]pr:high[/dim]                    high-urgency entries

[bold]── Saved filters ─────────────────────[/bold]
  Press [bold]f[/bold] to open Filters — a permanent, named search you can
  jump back to. Type a search, press [bold]f[/bold] then [bold]w[/bold] to
  write it as a filter, then pick it by number any time. The search box
  then refines further inside the active filter; Esc clears only the
  search, not the filter."""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]Help[/bold]", classes="modal-title")
            with VerticalScroll():
                yield Static(self._make_about(), id="help-about")
                yield Label("[bold]Keybindings[/bold]", classes="modal-title")
                yield Static(_build_help_keys())
                yield Label("[bold]Search syntax[/bold]", classes="modal-title")
                yield Static(self._SEARCH)
            with Horizontal(classes="modal-buttons"):
                yield Button("Close", variant="primary", id="btn-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()

    def action_dismiss_help(self) -> None:
        self.dismiss()


class RawEditModal(_BaseModal[BibEntry | None]):
    """Edit a BibTeX entry as raw text."""

    BINDINGS = [
        Binding(SAVE, "save", "Write", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    RawEditModal > Vertical {
        width: 90;
        height: 40;
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

    def action_save(self) -> None:
        self._save()

    def action_cancel(self) -> None:
        self.dismiss(None)


class PasteModal(_BaseModal["BibEntry | None"]):
    """Modal to import a BibTeX entry from pasted clipboard text."""

    BINDINGS = [
        Binding(SAVE, "do_import", "Import", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    PasteModal > Vertical {
        width: 90;
        height: 40;
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

    def action_do_import(self) -> None:
        self._do_import()

    def action_cancel(self) -> None:
        self.dismiss(None)


class PdfActionsModal(_BaseModal["str | None"]):
    """`p`: pick a PDF action for the selected entry.

    Modeled on :class:`NewEntryChooserModal` — a ``ListView`` of
    ``letter · Title — desc`` rows, chosen instantly by pressing the letter
    (no separate confirm step). All six rows are always listed, in the same
    order, so the menu always looks the same; the ones not valid for the
    entry's current PDF state (:func:`bibtui.pdf.paths.pdf_link_state`) are
    dimmed and inert — matching how the old button panel always showed all
    six buttons and just disabled the inapplicable ones, rather than the
    set of buttons itself changing shape. Dismisses with the chosen action's
    key, or ``None`` if canceled — the caller
    (``BibTuiApp._on_pdf_actions_choice``) dispatches to the existing
    ``action_*`` methods, unchanged.
    """

    # (result key, mnemonic letter, title, desc, states it applies to)
    _ALL_ACTIONS: list[tuple[str, str, str, str, set[str]]] = [
        ("open", "o", "Open PDF", "Open the linked PDF file", {"found"}),
        (
            "fetch",
            "f",
            "Fetch PDF",
            "Download the open-access PDF automatically",
            {"none", "missing"},
        ),
        ("add", "a", "Add PDF", "Link an existing PDF from disk", {"none", "missing"}),
        (
            "copy_file",
            "c",
            "Copy PDF File",
            "Copy the file to the clipboard",
            {"found"},
        ),
        ("copy_path", "p", "Copy PDF Path", "Copy the file's path as text", {"found"}),
        ("delete", "d", "Delete PDF", "Remove the file and unlink it", {"found", "missing"}),
    ]

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
        Binding("o", "choose('open')", show=False),
        Binding("f", "choose('fetch')", show=False),
        Binding("a", "choose('add')", show=False),
        Binding("c", "choose('copy_file')", show=False),
        Binding("p", "choose('copy_path')", show=False),
        Binding("d", "choose('delete')", show=False),
    ]

    DEFAULT_CSS = """
    PdfActionsModal > Vertical {
        width: 68;
    }
    PdfActionsModal ListView {
        height: auto;
        border: solid $panel;
    }
    PdfActionsModal ListItem {
        padding: 0 1;
    }
    """

    def __init__(self, entry: BibEntry, pdf_base_dir: str, **kwargs):
        super().__init__(**kwargs)
        self._entry = entry
        state = pdf_link_state(entry.file, entry.key, pdf_base_dir)
        self._available: set[str] = {
            opt[0] for opt in self._ALL_ACTIONS if state in opt[4]
        }

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(
                f"[bold]PDF Actions[/bold]  [dim]{self._entry.key}[/dim]",
                classes="modal-title",
            )
            with ListView(id="pdf-actions-list"):
                for key, letter, title, desc, _states in self._ALL_ACTIONS:
                    if key in self._available:
                        text = f"[bold]{letter}[/bold] · {title}  [dim]— {desc}[/dim]"
                    else:
                        # Grayed out, not just its desc — the whole row reads
                        # as inert, like a disabled button. `[dim]` rides on
                        # whatever the active theme resolves, so this stays
                        # theme-aware without a hardcoded color.
                        text = f"[dim]{letter} · {title}  — {desc}[/dim]"
                    yield ListItem(Label(text))
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        self.call_after_refresh(self.query_one(ListView).focus)

    @on(ListView.Selected, "#pdf-actions-list")
    def _on_selected(self, event: ListView.Selected) -> None:
        idx = self.query_one(ListView).index
        if idx is not None and idx < len(self._ALL_ACTIONS):
            self.action_choose(self._ALL_ACTIONS[idx][0])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)

    def action_choose(self, key: str) -> None:
        # A letter (or Enter on a row) for an action not valid right now
        # (e.g. `o` while the PDF isn't linked) is a silent no-op — same
        # effect as a disabled button, since that row is grayed out.
        if key in self._available:
            self.dismiss(key)

    def action_cancel(self) -> None:
        self.dismiss(None)


class FilterEditModal(_BaseModal["tuple[str, str] | None"]):
    """Create or edit one saved filter preset: a name and a query.

    The query field uses exactly the same syntax as the main search box
    (see :mod:`bibtui.widgets.entry_list`) — there's no separate filter
    language, so anything typed into search can be saved verbatim.
    Dismisses with ``(name, query)``, or ``None`` if canceled.
    """

    BINDINGS = [
        Binding(SAVE, "save", "Write", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    FilterEditModal > Vertical {
        width: 70;
    }
    FilterEditModal Input {
        margin-bottom: 1;
    }
    FilterEditModal #filter-edit-error {
        color: $error;
        height: auto;
    }
    """

    def __init__(self, name: str = "", query: str = "", **kwargs):
        super().__init__(**kwargs)
        self._initial_name = name
        self._initial_query = query

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]Save Filter[/bold]", classes="modal-title")
            yield Label("Name")
            yield Input(
                value=self._initial_name, placeholder="e.g. Project X", id="filter-name"
            )
            yield Label("Query")
            yield Input(
                value=self._initial_query,
                placeholder="k:sepp y:2010-",
                id="filter-query",
            )
            yield Static("", id="filter-edit-error")
            with Horizontal(classes="modal-buttons"):
                yield Button("Write", variant="primary", id="btn-save")
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        self.call_after_refresh(self.query_one("#filter-name", Input).focus)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-save":
            self._save()

    def _save(self) -> None:
        name = self.query_one("#filter-name", Input).value.strip()
        query = self.query_one("#filter-query", Input).value.strip()
        error = self.query_one("#filter-edit-error", Static)
        if not name:
            error.update("Name is required.")
            return
        if not query:
            error.update("Query is required.")
            return
        self.dismiss((name, query))

    def action_save(self) -> None:
        self._save()

    def action_cancel(self) -> None:
        self.dismiss(None)


class FilterPresetModal(_BaseModal["str | None"]):
    """`f`: pick a saved filter preset, or manage the saved list.

    Modeled on :class:`NewEntryChooserModal` / :class:`PdfActionsModal` — a
    single ``ListView`` chosen by number. Row 0 is always "All entries"
    (clears any active preset); rows 1-9 are the user's saved presets in
    file order, each selectable by its number, with the active one marked
    ``●``. Selecting a row (number, Enter, or click) dismisses the modal
    with that preset's name (``""`` for "All entries").

    ``w``/``e``/``d`` (write current search as a filter / edit / delete) act
    on the store immediately, persisting through the *persist* callback and
    refreshing the list in place — they do not dismiss the modal, so
    managing several presets in one visit doesn't need reopening it, and a
    later Esc never rolls any of it back.

    Deleting always drops back to "All entries" — both the highlighted row
    and, through the *reset_to_all* callback, the live entry list and title
    if a filter was actually applied — rather than leaving a just-deleted
    filter's results on screen. "All entries" itself (row 0) isn't a real
    preset and can't be deleted; trying to shows a notification instead of
    silently doing nothing.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
        Binding("0", "choose_index(0)", show=False),
        Binding("1", "choose_index(1)", show=False),
        Binding("2", "choose_index(2)", show=False),
        Binding("3", "choose_index(3)", show=False),
        Binding("4", "choose_index(4)", show=False),
        Binding("5", "choose_index(5)", show=False),
        Binding("6", "choose_index(6)", show=False),
        Binding("7", "choose_index(7)", show=False),
        Binding("8", "choose_index(8)", show=False),
        Binding("9", "choose_index(9)", show=False),
        Binding("w", "save_current", "Write", show=True),
        Binding("e", "edit_highlighted", "Edit", show=True),
        Binding("d", "delete_highlighted", "Delete", show=True),
    ]

    DEFAULT_CSS = """
    FilterPresetModal > Vertical {
        width: 76;
    }
    FilterPresetModal ListView {
        height: auto;
        max-height: 16;
        border: solid $panel;
    }
    FilterPresetModal ListItem {
        padding: 0 1;
    }
    FilterPresetModal #filter-hints {
        height: auto;
        margin-top: 1;
        color: $text-muted;
    }
    """

    def __init__(
        self,
        store: FilterStore,
        current_search: str,
        persist: "Callable[[FilterStore], None]",
        reset_to_all: "Callable[[], None]",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._store = store
        self._current_search = current_search
        self._persist = persist
        self._reset_to_all = reset_to_all

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]Filters[/bold]", classes="modal-title")
            yield ListView(id="filter-list")
            yield Static(
                "[dim]Esc close · Enter select  |  ↓/↑ navigate · 0-9 jump · "
                "w write current search · e edit · d delete[/dim]",
                id="filter-hints",
            )
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        # Highlight the active preset's row (or "All entries") so it's
        # obvious at a glance what's currently selected, matching the
        # active-marker convention on the row text itself.
        self._rebuild_list(highlight_name=self._store.active)
        self.call_after_refresh(self.query_one(ListView).focus)

    def _row_label(self, index: int) -> str:
        active = self._store.active.strip().lower()
        if index == 0:
            marker = "●" if not active else " "
            return f"[bold]0[/bold] · {marker} All entries"
        preset = self._store.presets[index - 1]
        num = str(index) if index <= 9 else " "
        marker = "●" if preset.name.lower() == active else " "
        return f"[bold]{num}[/bold] · {marker} {preset.name}  [dim]— {preset.query}[/dim]"

    def _rebuild_list(self, highlight_name: str | None = None) -> None:
        lv = self.query_one(ListView)
        lv.clear()
        for index in range(len(self._store.presets) + 1):
            lv.append(ListItem(Label(self._row_label(index))))
        if highlight_name is not None:
            idx = self._index_for_name(highlight_name)
            if idx is not None:
                lv.index = idx

    def _index_for_name(self, name: str) -> int | None:
        if not name:
            return 0
        for i, preset in enumerate(self._store.presets, start=1):
            if preset.name.lower() == name.lower():
                return i
        return None

    def _name_for_index(self, index: int) -> str | None:
        if index == 0:
            return ""
        preset_idx = index - 1
        if 0 <= preset_idx < len(self._store.presets):
            return self._store.presets[preset_idx].name
        return None

    def _highlighted_preset(self) -> "FilterPreset | None":
        idx = self.query_one(ListView).index
        if idx is None or idx == 0:
            return None
        preset_idx = idx - 1
        if 0 <= preset_idx < len(self._store.presets):
            return self._store.presets[preset_idx]
        return None

    @on(ListView.Selected, "#filter-list")
    def _on_selected(self, event: ListView.Selected) -> None:
        idx = self.query_one(ListView).index
        if idx is not None:
            self._choose(idx)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)

    def _choose(self, index: int) -> None:
        name = self._name_for_index(index)
        if name is not None:
            self.dismiss(name)

    def action_choose_index(self, index: int) -> None:
        self._choose(index)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_save_current(self) -> None:
        active_preset = self._store.find(self._store.active) if self._store.active else None
        parts = [
            p for p in (active_preset.query if active_preset else "", self._current_search) if p
        ]
        prefill_query = " ".join(parts)
        self.app.push_screen(
            FilterEditModal(query=prefill_query), self._on_save_current_done
        )

    def _on_save_current_done(self, result: "tuple[str, str] | None") -> None:
        if result is None:
            return
        name, query = result
        self._store.upsert(FilterPreset(name=name, query=query))
        self._persist(self._store)
        self._rebuild_list(highlight_name=name)

    def action_edit_highlighted(self) -> None:
        preset = self._highlighted_preset()
        if preset is None:
            return
        self.app.push_screen(
            FilterEditModal(name=preset.name, query=preset.query),
            lambda result: self._on_edit_done(preset.name, result),
        )

    def _on_edit_done(self, old_name: str, result: "tuple[str, str] | None") -> None:
        if result is None:
            return
        new_name, query = result
        was_active = self._store.active.strip().lower() == old_name.lower()
        if new_name.lower() != old_name.lower():
            self._store.remove(old_name)
        self._store.upsert(FilterPreset(name=new_name, query=query))
        if was_active:
            self._store.active = new_name
        self._persist(self._store)
        self._rebuild_list(highlight_name=new_name)

    def action_delete_highlighted(self) -> None:
        if self.query_one(ListView).index == 0:
            self.app.notify("'All entries' can't be deleted.", severity="warning")
            return
        preset = self._highlighted_preset()
        if preset is None:
            return
        msg = f"Delete filter '[bold]{preset.name}[/bold]'?"
        self.app.push_screen(
            ConfirmModal(msg),
            lambda confirmed: self._on_delete_confirmed(confirmed, preset.name),
        )

    def _on_delete_confirmed(self, confirmed: bool | None, name: str) -> None:
        if not confirmed:
            return
        self._store.remove(name)
        # Deleting always drops back to "All entries" — never leaves a
        # just-deleted filter's results on screen, active or not.
        self._store.active = ""
        self._persist(self._store)
        self._reset_to_all()
        self._rebuild_list(highlight_name="")


class AddPDFModal(_FileBrowseMixin, _BaseModal["str | None"]):
    """Pick an existing PDF from the download directory, filter by name, and link it."""

    _ID_PREFIX = "add"
    _GLOB = "*.pdf"
    _NOUN = "PDF"

    BINDINGS = [
        Binding(SAVE, "add", "Add", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    AddPDFModal > Vertical {
        width: 80;
        height: 30;
    }
    AddPDFModal Input {
        margin-bottom: 1;
    }
    AddPDFModal ListView {
        height: 1fr;
        border: solid $panel;
        margin-bottom: 1;
    }
    AddPDFModal #add-hint {
        color: $text-muted;
        margin-bottom: 1;
    }
    AddPDFModal #add-preview-hint {
        color: $text-muted;
        height: auto;
        margin-bottom: 1;
    }
    AddPDFModal #add-error {
        color: $error;
    }
    """

    def __init__(
        self,
        entry: BibEntry,
        base_dir: str,
        download_dir: str,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._entry = entry
        self._base_dir = base_dir
        self._download_dir = download_dir or str(Path.home() / "Downloads")
        self._all_files: list[Path] = []
        self._filtered: list[Path] = []

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(
                f"[bold]Add PDF[/bold]  [dim]{self._entry.key}[/dim]",
                classes="modal-title",
            )
            yield Static("", id="add-hint")
            yield Input(
                placeholder="type to filter, or paste a file/folder path…",
                id="add-filter",
            )
            yield ListView(id="add-list")
            yield Static(
                "[dim]↓/↑ navigate · Space preview · Enter/x add · s search[/dim]",
                id="add-preview-hint",
            )
            yield Static("", id="add-error")
            with Horizontal(classes="modal-buttons"):
                yield Button("Add", variant="primary", id="btn-add")
                yield Button("Cancel", id="btn-cancel")

    @on(Input.Changed, "#add-filter")
    def _on_filter(self, event: Input.Changed) -> None:
        self._filter_changed(event)

    @on(Input.Submitted, "#add-filter")
    def _on_filter_submitted(self, event: Input.Submitted) -> None:
        self._filter_submitted(event)

    @on(ListView.Selected)
    def _on_list_selected(self, event: ListView.Selected) -> None:
        self._list_selected(event)

    def _choose_path(self, path: Path) -> None:
        from bibtui.pdf.fetcher import FetchError, add_pdf

        error = self.query_one("#add-error", Static)
        error.update("")
        try:
            dest = add_pdf(path, self._entry, self._base_dir)
            self.dismiss(str(dest))
        except FetchError as exc:
            error.update(str(exc))

    def action_add(self) -> None:
        self._confirm()


class FetchPDFModal(_BaseModal["tuple[str, str] | None"]):
    """Fetch a PDF for an entry in a background thread and show progress."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    DEFAULT_CSS = """
    FetchPDFModal > Vertical {
        width: 70;
    }
    FetchPDFModal LoadingIndicator {
        height: 3;
    }
    FetchPDFModal #fetch-status {
        margin-top: 1;
        margin-bottom: 1;
        color: $text;
    }
    FetchPDFModal #fetch-status.success {
        color: $success;
    }
    FetchPDFModal #fetch-status.error {
        color: $error;
    }
    """

    def __init__(
        self,
        entry: BibEntry,
        dest_dir: str,
        unpaywall_email: str = "",
        openalex_api_key: str = "",
        overwrite: bool = False,
        just_created: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._entry = entry
        self._dest_dir = dest_dir
        self._email = unpaywall_email
        self._openalex_api_key = openalex_api_key
        self._overwrite = overwrite
        # True when this fetch is the automatic one right after the entry
        # was just added (see BibTuiApp._maybe_auto_fetch) — on failure the
        # entry itself is still there, only the PDF is missing, so say so
        # instead of a bare "could not fetch" that reads like nothing happened.
        self._just_created = just_created
        self._saved_result: tuple[str, str] | None = None

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
        from bibtui.pdf.fetcher import FetchError, fetch_pdf

        try:
            result = fetch_pdf(
                self._entry,
                self._dest_dir,
                self._email,
                openalex_api_key=self._openalex_api_key,
                overwrite=self._overwrite,
            )  # type: ignore[call-arg]
            self.app.call_from_thread(self._on_success, result.path, result.provider)
        except FetchError as exc:
            self.app.call_from_thread(self._on_error, str(exc))
        except Exception as exc:  # noqa: BLE001
            self.app.call_from_thread(self._on_error, f"Unexpected error: {exc}")

    def _on_success(self, path: str, provider: str) -> None:
        self.query_one("#fetch-loading", LoadingIndicator).display = False
        status = self.query_one("#fetch-status", Static)
        status.set_class(True, "success")
        status.set_class(False, "error")
        status.update(f"Saved PDF via {provider}:\n{path}")
        self.query_one("#btn-close", Button).disabled = False
        self.query_one("#btn-cancel", Button).disabled = True
        self._saved_result = (path, provider)

    def _on_error(self, message: str) -> None:
        self.query_one("#fetch-loading", LoadingIndicator).display = False
        status = self.query_one("#fetch-status", Static)
        status.set_class(False, "success")
        status.set_class(True, "error")
        status.update(self._format_fetch_error(message))
        self.query_one("#btn-close", Button).disabled = False

    def _format_fetch_error(self, message: str) -> str:
        title = (
            f"Added '{self._entry.key}', but its PDF could not be fetched."
            if self._just_created
            else "Could not fetch PDF for this entry."
        )
        lines = [line.strip() for line in message.splitlines() if line.strip()]
        if not lines:
            return title

        reasons = [
            line[1:].strip() if line.startswith("•") else line
            for line in lines
            if line.startswith("•") or line.startswith("-")
        ]
        if not reasons:
            reasons = [
                line
                for line in lines
                if not line.lower().startswith("could not fetch pdf")
            ]

        if not reasons:
            return title

        formatted_reasons = "\n".join(f"• {reason}" for reason in reasons)
        return f"{title}\n\n{formatted_reasons}"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-close":
            self.dismiss(self._saved_result)

    def action_cancel(self) -> None:
        self.dismiss(None)


class BatchFetchPDFModal(_BaseModal["dict | None"]):
    """Fetch PDFs for many entries in a background thread and show progress."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    DEFAULT_CSS = """
    BatchFetchPDFModal > Vertical {
        width: 72;
    }
    BatchFetchPDFModal LoadingIndicator {
        height: 3;
    }
    BatchFetchPDFModal #batch-fetch-progress,
    BatchFetchPDFModal #batch-fetch-status {
        margin-top: 1;
        color: $text;
    }
    BatchFetchPDFModal #batch-fetch-status.success {
        color: $success;
    }
    BatchFetchPDFModal #batch-fetch-status.error {
        color: $error;
    }
    """

    def __init__(
        self,
        entries: list[BibEntry],
        dest_dir: str,
        unpaywall_email: str = "",
        openalex_api_key: str = "",
        overwrite_broken_links: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._entries = entries
        self._dest_dir = dest_dir
        self._email = unpaywall_email
        self._openalex_api_key = openalex_api_key
        self._overwrite_broken_links = overwrite_broken_links
        self._cancel_requested = False
        self._done = False
        self._result: dict | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]Fetch Missing PDFs[/bold]", classes="modal-title")
            yield LoadingIndicator(id="batch-fetch-loading")
            yield Static("Preparing…", id="batch-fetch-progress")
            yield Static("", id="batch-fetch-status")
            with Horizontal(classes="modal-buttons"):
                yield Button("Close", variant="primary", id="btn-close", disabled=True)
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        self._do_fetch()

    @work(thread=True)
    def _do_fetch(self) -> None:
        from bibtui.pdf.fetcher import FetchError, fetch_pdf

        total = len(self._entries)
        success = 0
        failed = 0
        skipped = 0
        canceled = False
        paths_by_key: dict[str, str] = {}
        failures: list[str] = []

        for index, entry in enumerate(self._entries, start=1):
            if self._cancel_requested:
                canceled = True
                break

            self.app.call_from_thread(
                self._on_progress,
                f"[{index}/{total}] {entry.key}",
            )

            if not entry.doi and not entry.url and not entry.title:
                skipped += 1
                failures.append(f"{entry.key}: no DOI, URL, or title")
                continue

            try:
                result = fetch_pdf(
                    entry,
                    self._dest_dir,
                    self._email,
                    openalex_api_key=self._openalex_api_key,
                    overwrite=False,
                )  # type: ignore[call-arg]
                paths_by_key[entry.key] = result.path
                success += 1
            except FetchError as exc:
                failed += 1
                failures.append(f"{entry.key}: {exc}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                failures.append(f"{entry.key}: unexpected error: {exc}")

        processed = success + failed + skipped
        self.app.call_from_thread(
            self._on_done,
            {
                "paths_by_key": paths_by_key,
                "processed": processed,
                "total": total,
                "success": success,
                "failed": failed,
                "skipped": skipped,
                "canceled": canceled,
                "failures": failures,
            },
        )

    def _on_progress(self, message: str) -> None:
        self.query_one("#batch-fetch-progress", Static).update(message)

    def _on_done(self, result: dict) -> None:
        self._done = True
        self._result = result
        self.query_one("#batch-fetch-loading", LoadingIndicator).display = False
        status = self.query_one("#batch-fetch-status", Static)
        if result["success"] > 0:
            status.set_class(True, "success")
            status.set_class(False, "error")
        else:
            status.set_class(False, "success")
            status.set_class(True, "error")

        canceled_text = " (canceled)" if result["canceled"] else ""
        status.update(
            "Finished"
            f"{canceled_text}: {result['success']} fetched, {result['failed']} failed, "
            f"{result['skipped']} skipped."
        )
        self.query_one("#batch-fetch-progress", Static).update(
            f"Processed {result['processed']} of {result['total']} entries."
        )
        self.query_one("#btn-close", Button).disabled = False
        self.query_one("#btn-cancel", Button).disabled = True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.action_cancel()
        elif event.button.id == "btn-close":
            self.dismiss(self._result)

    def action_cancel(self) -> None:
        if self._done:
            self.dismiss(self._result)
            return
        self._cancel_requested = True
        self.query_one("#batch-fetch-status", Static).update(
            "Stopping after current entry…"
        )
        self.query_one("#btn-cancel", Button).disabled = True


class PreviewSelectionList(SelectionList):
    """A SelectionList where Space previews the highlighted row instead of
    toggling it, and Enter/`x` toggle instead — the checklist counterpart of
    every single-choice picker's Space-previews/Enter-or-x-chooses
    convention (:class:`AddPDFModal` and friends). Space delegates to the
    screen's ``_preview_highlighted`` if it defines one; on a screen that
    doesn't (nothing to preview — e.g. :class:`KeywordsModal`), Space is
    simply a no-op rather than falling back to plain ``SelectionList``'s
    default of toggling on Space.
    """

    BINDINGS = [
        Binding("space", "preview", "Preview", show=False),
        Binding("x", "select", "Toggle", show=False),
    ]

    def action_preview(self) -> None:
        preview = getattr(self.screen, "_preview_highlighted", None)
        if callable(preview):
            preview()


class PdfImportPickerModal(_BaseModal["list[str] | None"]):
    """Pick one or more existing PDFs to import, filtered by name.

    Same browsing model as :class:`AddPDFModal` (list the configured download
    directory, filter by typing, ``Space`` previews the highlighted row) but
    as a checklist — ``Enter``/``x`` toggle a row instead of choosing it
    outright — so several files can be picked at once, since
    there's no single entry to attach them to yet — that happens per-file in
    the review step after metadata is fetched. Submitting an existing
    directory path in the filter re-points the listing at that folder
    (e.g. an old downloads folder or a migrated Papers/Zotero export)
    instead of only ever showing the configured download directory.
    """

    # See _FileBrowseMixin's AUTO_FOCUS for why this is disabled: without
    # it, the filter Input (composed before the list) would flash focused
    # for one frame before _focus_initial() moves focus to the list.
    AUTO_FOCUS = ""

    BINDINGS = [
        Binding(SAVE, "import_selected", "Import", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    PdfImportPickerModal > Vertical {
        width: 80;
        height: 34;
    }
    PdfImportPickerModal Input {
        margin-bottom: 1;
    }
    PdfImportPickerModal SelectionList {
        height: 1fr;
        border: solid $panel;
        margin-bottom: 1;
    }
    PdfImportPickerModal #pip-hint {
        color: $text-muted;
        margin-bottom: 1;
    }
    PdfImportPickerModal #pip-nav-hint {
        color: $text-muted;
        height: auto;
        margin-bottom: 1;
    }
    PdfImportPickerModal #pip-error {
        color: $error;
    }
    """

    def __init__(self, download_dir: str, **kwargs):
        super().__init__(**kwargs)
        self._download_dir = download_dir or str(Path.home() / "Downloads")
        self._all_files: list[Path] = []
        self._filtered: list[Path] = []
        self._selected: set[str] = set()

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]Import from PDF[/bold]", classes="modal-title")
            yield Static("", id="pip-hint")
            yield Input(
                placeholder="type to filter, or paste a file/folder path…",
                id="pip-filter",
            )
            yield PreviewSelectionList(id="pip-list")
            yield Static(
                "[dim]↓/↑ navigate · Space preview · Enter/x toggle · s search[/dim]",
                id="pip-nav-hint",
            )
            yield Static("", id="pip-error")
            with Horizontal(classes="modal-buttons"):
                yield Button("Import", variant="primary", id="btn-import")
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        self._scan()
        self._focus_initial()

    def _focus_initial(self) -> None:
        """Default focus is the first row in the list, not the filter — same
        convention as every other file picker in the app. `s` jumps back to
        the filter from the list, matching the main view's Search key."""
        sl = self.query_one(SelectionList)
        if self._filtered:
            sl.highlighted = 0
            self.call_after_refresh(sl.focus)
        else:
            self.call_after_refresh(self.query_one("#pip-filter", Input).focus)

    def _scan(self) -> None:
        dl = Path(self._download_dir).expanduser()
        hint = self.query_one("#pip-hint", Static)
        if not dl.is_dir():
            hint.update(
                f"[dim]Folder not found: {dl}  ·  paste a file or folder path below[/dim]"
            )
            self._all_files = []
        else:
            pdfs = sorted(
                dl.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True
            )
            self._all_files = pdfs
            hint.update(
                f"[dim]{dl}  ·  {len(pdfs)} PDF{'s' if len(pdfs) != 1 else ''}  ·  "
                "paste another folder path to browse elsewhere[/dim]"
            )
        self._filtered = list(self._all_files)
        self._rebuild_list()

    def _sync_from_list(self) -> None:
        """Pull the checkbox state of currently shown rows into self._selected."""
        sl = self.query_one(SelectionList)
        selected_now = set(sl.selected)
        for p in self._filtered:
            path = str(p)
            if path in selected_now:
                self._selected.add(path)
            else:
                self._selected.discard(path)

    def _rebuild_list(self) -> None:
        sl = self.query_one(SelectionList)
        sl.clear_options()
        for p in self._filtered:
            label = _file_row_label(p)
            sl.add_option(Selection(label, str(p), str(p) in self._selected))

    @on(Input.Changed, "#pip-filter")
    def _on_filter(self, event: Input.Changed) -> None:
        self._sync_from_list()
        q = event.value.strip().lower()
        self._filtered = (
            [p for p in self._all_files if q in p.name.lower()]
            if q
            else list(self._all_files)
        )
        self._rebuild_list()

    def on_key(self, event: events.Key) -> None:
        """Down in the Input moves focus to the list; Up from the first item
        or `s` returns focus to the filter."""
        sl = self.query_one(SelectionList)
        inp = self.query_one("#pip-filter", Input)
        if self.focused is inp and event.key == "down" and self._filtered:
            sl.focus()
            event.stop()
        elif self.focused is sl and event.key == "up" and (sl.highlighted or 0) == 0:
            inp.focus()
            event.stop()
        elif self.focused is sl and event.key == "s":
            inp.focus()
            event.stop()

    def _preview_highlighted(self) -> None:
        sl = self.query_one(SelectionList)
        idx = sl.highlighted
        if idx is None or idx >= len(self._filtered):
            return
        try:
            open_with_default_app(str(self._filtered[idx]))
        except Exception as e:
            self.query_one("#pip-error", Static).update(f"Could not open: {e}")

    @on(Input.Submitted, "#pip-filter")
    def _on_filter_submitted(self, _: Input.Submitted) -> None:
        val = self.query_one("#pip-filter", Input).value.strip()
        if not val:
            return
        error = self.query_one("#pip-error", Static)
        error.update("")

        expanded = Path(val).expanduser()
        if expanded.is_dir():
            self._download_dir = str(expanded)
            self.query_one("#pip-filter", Input).value = ""
            self._scan()
            return

        if expanded.is_file() and expanded.suffix.lower() == ".pdf":
            if expanded not in self._all_files:
                self._all_files.insert(0, expanded)
            self._selected.add(str(expanded))
            self.query_one("#pip-filter", Input).value = ""
            self._filtered = list(self._all_files)
            self._rebuild_list()
            return

        self._sync_from_list()
        if len(self._filtered) == 1:
            path = str(self._filtered[0])
            if path in self._selected:
                self._selected.discard(path)
            else:
                self._selected.add(path)
            self._rebuild_list()
            return

        error.update("No matching file or folder — refine the filter or pick from the list.")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-import":
            self._confirm()

    def _confirm(self) -> None:
        self._sync_from_list()
        if not self._selected:
            self.query_one("#pip-error", Static).update("Select at least one PDF.")
            return
        self.dismiss(sorted(self._selected))

    def action_import_selected(self) -> None:
        self._confirm()

    def action_cancel(self) -> None:
        self.dismiss(None)


class PdfImportReviewModal(_BaseModal["dict | None"]):
    """Scan PDFs for an identifier, fetch metadata, and report the outcome.

    Scanning (offline extraction + CrossRef lookups, one file at a time)
    runs in a background thread. Once it finishes, every file is listed —
    which PDF to try was already decided in :class:`PdfImportPickerModal`,
    so this isn't a second yes/no per file — with a ✓/✗ mark: matched files
    (a new entry will be created) and files that matched an existing entry
    with no PDF yet (that PDF will be linked to it, no new entry created)
    are ✓; anything ambiguous, unidentified, already present, or that failed
    to look up is ✗ with the reason (an ambiguous row's candidate DOIs are
    included, so you can copy one out and use "Import by DOI" yourself if
    the right one isn't obvious). Space previews the highlighted row's
    source PDF, success or failure. Nothing is written until "Import N
    Entries" is pressed — one action for every ✓ row at once, no per-file
    toggle. Dismisses with ``{"new": [...], "relinked": [...]}`` (new
    entries to append vs. existing entries that got a PDF linked in place)
    or ``None`` if canceled or nothing was importable.
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    DEFAULT_CSS = """
    PdfImportReviewModal > Vertical {
        width: 96;
        height: 88%;
    }
    PdfImportReviewModal LoadingIndicator {
        height: 3;
    }
    PdfImportReviewModal #import-progress {
        margin-top: 1;
        color: $text;
    }
    PdfImportReviewModal OptionList {
        height: 1fr;
        border: solid $panel;
        margin-top: 1;
    }
    PdfImportReviewModal #import-nav-hint {
        color: $text-muted;
        height: auto;
        margin-top: 1;
    }
    """

    _STATUS_LABELS = {
        "already_present": "Already present",
        "no_identifier": "No identifier found",
        "ambiguous": "Ambiguous",
        "lookup_failed": "Lookup failed",
    }

    # Pause between PDFs that actually hit CrossRef, so a large folder
    # doesn't fire dozens of back-to-back anonymous-pool requests. Skipped
    # for rows resolved without a network call (no identifier, ambiguous,
    # already present, or matched a library entry by DOI alone) and after
    # the last file (nothing left to protect).
    _CROSSREF_PAUSE_SECONDS = 0.2

    def __init__(
        self,
        paths: list[str],
        existing_by_doi: dict[str, BibEntry],
        base_dir: str,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._paths = paths
        self._existing_by_doi = existing_by_doi
        self._base_dir = base_dir
        self._cancel_requested = False
        self._scanning = True
        self._rows: list = []

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(
                f"[bold]Import from PDF[/bold]  [dim]{len(self._paths)} file"
                f"{'s' if len(self._paths) != 1 else ''}[/dim]",
                classes="modal-title",
            )
            yield LoadingIndicator(id="import-loading")
            yield Static("Preparing…", id="import-progress")
            yield OptionList(id="import-list")
            yield Static(
                "[dim]↓/↑ navigate · Space preview[/dim]",
                id="import-nav-hint",
            )
            with Horizontal(classes="modal-buttons"):
                yield Button("Import", variant="primary", id="btn-import", disabled=True)
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        self.query_one(OptionList).display = False
        self._scan()

    @work(thread=True)
    def _scan(self) -> None:
        from bibtui.pdf.import_scan import ImportStatus, process_pdf

        seen_in_batch: set[str] = set()
        rows = []
        total = len(self._paths)
        for index, path in enumerate(self._paths, start=1):
            if self._cancel_requested:
                break
            self.app.call_from_thread(
                self._on_progress, f"[{index}/{total}] {Path(path).name}"
            )
            row = process_pdf(path, self._existing_by_doi, seen_in_batch)
            if (
                row.status in (ImportStatus.MATCHED, ImportStatus.LINK_EXISTING)
                and row.entry
                and row.entry.doi
            ):
                seen_in_batch.add(normalize_doi(row.entry.doi))
            rows.append(row)
            hit_crossref = row.status in (ImportStatus.MATCHED, ImportStatus.LOOKUP_FAILED)
            if hit_crossref and index < total and not self._cancel_requested:
                time.sleep(self._CROSSREF_PAUSE_SECONDS)
        self.app.call_from_thread(self._on_scan_done, rows)

    def _on_progress(self, message: str) -> None:
        self.query_one("#import-progress", Static).update(message)

    def _importable_rows(self) -> list:
        from bibtui.pdf.import_scan import ImportStatus

        return [
            r for r in self._rows if r.status in (ImportStatus.MATCHED, ImportStatus.LINK_EXISTING)
        ]

    def _row_text(self, row) -> Text:
        from bibtui.pdf.import_scan import ImportStatus

        if row.status == ImportStatus.MATCHED:
            entry = row.entry
            body = (
                f"{row.filename} → {entry.title_short} "
                f"({entry.authors_short}, {entry.year or '?'})"
            )
            return _report_row_text(self.app, True, body)
        if row.status == ImportStatus.LINK_EXISTING:
            body = f"{row.filename} → link to existing entry '{row.entry.key}'"
            return _report_row_text(self.app, True, body)
        label = self._STATUS_LABELS.get(str(row.status), str(row.status))
        candidates = f" ({', '.join(row.candidates)})" if row.candidates else ""
        body = f"{row.filename} — {label}: {row.message}{candidates}"
        return _report_row_text(self.app, False, body)

    def _on_scan_done(self, rows: list) -> None:
        self._scanning = False
        self._rows = rows
        self.query_one("#import-loading", LoadingIndicator).display = False

        ol = self.query_one(OptionList)
        ol.display = True
        for row in rows:
            ol.add_option(Option(self._row_text(row)))

        importable = self._importable_rows()
        skipped = len(rows) - len(importable)
        self.query_one("#import-progress", Static).update(
            f"Scanned {len(rows)} file{'s' if len(rows) != 1 else ''}: "
            f"{len(importable)} to import, {skipped} skipped."
        )

        btn = self.query_one("#btn-import", Button)
        btn.disabled = not importable
        btn.label = _import_button_label(len(importable))

    def on_key(self, event: events.Key) -> None:
        """Space previews the highlighted row's source PDF."""
        ol = self.query_one(OptionList)
        if self.focused is ol and event.key == "space":
            self._preview_highlighted()
            event.stop()

    def _preview_highlighted(self) -> None:
        ol = self.query_one(OptionList)
        idx = ol.highlighted
        if idx is None or idx >= len(self._rows):
            return
        try:
            open_with_default_app(self._rows[idx].path)
        except Exception as e:
            self.app.notify(f"Could not open: {e}", severity="error", timeout=5)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.action_cancel()
        elif event.button.id == "btn-import":
            self._confirm()

    def _confirm(self) -> None:
        if self._scanning:
            return
        importable = self._importable_rows()
        if not importable:
            self.dismiss(None)
            return

        from bibtui.pdf.fetcher import FetchError, add_pdf
        from bibtui.pdf.import_scan import ImportStatus
        from bibtui.pdf.paths import format_jabref_path

        new_entries: list[BibEntry] = []
        relinked_entries: list[BibEntry] = []
        errors: list[str] = []
        reused_count = 0
        for row in importable:
            entry = row.entry
            if entry is None:
                continue
            if self._base_dir:
                try:
                    src = Path(row.path)
                    dest = add_pdf(src, entry, self._base_dir)
                    # add_pdf reuses an identical PDF already in the library
                    # instead of moving src there a second time under a new
                    # name — src still being on disk afterwards is how we
                    # tell that happened, without add_pdf needing to say so
                    # explicitly (every other caller just wants the path).
                    if src.exists():
                        reused_count += 1
                    entry.file = format_jabref_path(str(dest), self._base_dir)
                except FetchError as exc:
                    errors.append(f"{row.filename}: {exc}")
                    continue
            if row.status == ImportStatus.LINK_EXISTING:
                # `entry` is the same object already in the library (see
                # process_pdf) — mutating .file above already updated it in
                # place; the caller just needs to know to refresh, not append.
                relinked_entries.append(entry)
            else:
                new_entries.append(entry)

        if reused_count:
            noun = "PDF was" if reused_count == 1 else "PDFs were"
            self.app.notify(
                f"{reused_count} {noun} already in your library — "
                "linked to the existing file instead of copying it again.",
                timeout=5,
            )
        if errors:
            self.app.notify(
                "Some PDFs could not be linked:\n" + "\n".join(errors),
                severity="warning",
                timeout=8,
            )

        if not new_entries and not relinked_entries:
            self.dismiss(None)
            return
        self.dismiss({"new": new_entries, "relinked": relinked_entries})

    def action_cancel(self) -> None:
        if self._scanning:
            self._cancel_requested = True
            self.query_one("#import-progress", Static).update("Stopping…")
            return
        self.dismiss(None)


class BibFileImportReviewModal(_BaseModal["list[BibEntry] | None"]):
    """Report the outcome of parsing a multi-entry .bib file and commit it.

    Parsing already happened synchronously (:func:`bibtui.bib.parser.load`)
    before this modal opens — unlike the PDF import review screen there's no
    background work here. Each parsed entry is marked ✓ (no DOI, or a DOI
    not already in the library — will be added) or ✗ (its DOI already
    matches a library entry, including a duplicate DOI within this same
    file — skipped). Duplicate detection is DOI-only, matching "Import from
    PDF": an entry with no DOI is always ✓, never auto-skipped. Dismisses
    with the list of ✓ entries to append, or ``None`` if none are new or
    the user cancels — nothing is written until "Import N Entries".

    Like :class:`PdfImportReviewModal`, Space previews a file — here there's
    only one file (the `.bib` file itself, the same one on every row), not
    one per row, but the keybinding is kept consistent rather than dropped.
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    DEFAULT_CSS = """
    BibFileImportReviewModal > Vertical {
        width: 96;
        height: 88%;
    }
    BibFileImportReviewModal #bfi-summary {
        margin-top: 1;
        color: $text;
    }
    BibFileImportReviewModal OptionList {
        height: 1fr;
        border: solid $panel;
        margin-top: 1;
    }
    BibFileImportReviewModal #bfi-nav-hint {
        color: $text-muted;
        height: auto;
        margin-top: 1;
    }
    """

    def __init__(
        self,
        entries: list[BibEntry],
        existing_by_doi: dict[str, BibEntry],
        path: str = "",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._path = path
        self._new_entries: list[BibEntry] = []
        self._rows: list[tuple[BibEntry, str | None]] = []  # (entry, skip-reason)
        seen_in_batch: set[str] = set()

        for entry in entries:
            doi = (entry.doi or "").strip()
            normalized = normalize_doi(doi) if doi else ""
            reason: str | None = None
            if normalized:
                if normalized in existing_by_doi:
                    reason = f"Already in library as '{existing_by_doi[normalized].key}'"
                elif normalized in seen_in_batch:
                    reason = "Duplicate of another entry in this file"
            if reason is None:
                if normalized:
                    seen_in_batch.add(normalized)
                self._new_entries.append(entry)
            self._rows.append((entry, reason))

    def compose(self) -> ComposeResult:
        total = len(self._rows)
        with Vertical():
            yield Label(
                f"[bold]Import .bib File[/bold]  [dim]{total} entr"
                f"{'y' if total == 1 else 'ies'}[/dim]",
                classes="modal-title",
            )
            yield Static(self._summary_text(), id="bfi-summary")
            yield OptionList(id="bfi-list")
            yield Static(
                "[dim]↓/↑ navigate · Space preview the .bib file[/dim]",
                id="bfi-nav-hint",
            )
            with Horizontal(classes="modal-buttons"):
                yield Button(
                    _import_button_label(len(self._new_entries)),
                    variant="primary",
                    id="btn-import",
                    disabled=not self._new_entries,
                )
                yield Button("Cancel", id="btn-cancel")

    def _summary_text(self) -> str:
        total = len(self._rows)
        new = len(self._new_entries)
        skipped = total - new
        return (
            f"{total} entr{'y' if total == 1 else 'ies'} found: "
            f"{new} new, {skipped} already in your library."
        )

    def on_mount(self) -> None:
        ol = self.query_one(OptionList)
        for entry, reason in self._rows:
            ol.add_option(Option(self._row_text(entry, reason)))

    def _row_text(self, entry: BibEntry, reason: str | None) -> Text:
        if reason is None:
            body = (
                f"{entry.key} → {entry.title_short} "
                f"({entry.authors_short}, {entry.year or '?'})"
            )
            return _report_row_text(self.app, True, body)
        return _report_row_text(self.app, False, f"{entry.key} — {reason}")

    def on_key(self, event: events.Key) -> None:
        """Space previews the source .bib file, regardless of which row is
        highlighted — matching PdfImportReviewModal's Space-to-preview
        convention, even though here every row shares the same one file."""
        ol = self.query_one(OptionList)
        if self.focused is ol and event.key == "space":
            self._preview_source()
            event.stop()

    def _preview_source(self) -> None:
        if not self._path:
            return
        try:
            open_with_default_app(self._path)
        except Exception as e:
            self.app.notify(f"Could not open: {e}", severity="error", timeout=5)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-import":
            self._confirm()

    def _confirm(self) -> None:
        self.dismiss(self._new_entries or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class FirstRunModal(_BaseModal[bool]):
    """One-time welcome notice — shown only on the very first launch."""

    BINDINGS = [Binding("escape", "got_it", "Got it", show=False)]

    DEFAULT_CSS = """
    FirstRunModal > Vertical {
        width: 70; padding: 2 3;
    }
    FirstRunModal #welcome-title { text-align: center; margin-bottom: 1; }
    FirstRunModal #welcome-body  { margin-bottom: 1; }
    FirstRunModal .modal-buttons { height: 3; align: right middle; }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(
                "[bold]Welcome to bibtui![/bold]",
                id="welcome-title",
            )
            yield Static(
                "A terminal UI with keyboard and mouse support for your BibTeX libraries.\n\n"
                "[bold]You're ready to go[/bold] — no setup required.\n"
                "Just run  [bold]bibtui yourfile.bib[/bold]  and start browsing.\n\n"
                "[dim]Optional:[/dim] PDF fetching and attaching require a few"
                " extra settings\n"
                "(PDF dir, download dir, Unpaywall email).  Open them any time\n"
                "via [bold]Ctrl+P → Settings[/bold] or press [bold]Configure PDF features[/bold] below.",
                id="welcome-body",
            )
            with Horizontal(classes="modal-buttons"):
                yield Button("Got it", variant="primary", id="btn-got-it")
                yield Button(
                    "Configure PDF features", variant="default", id="btn-configure"
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-configure")

    def action_got_it(self) -> None:
        self.dismiss(False)


class BibDirectoryTree(DirectoryTree):
    """DirectoryTree that shows only directories and .bib files."""

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        return [p for p in paths if p.is_dir() or p.suffix == ".bib"]


class FilePickerModal(_BaseModal["str | None"]):
    """Browse the filesystem and select a .bib file, with recent-files shortcuts."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=True)]

    DEFAULT_CSS = """
    FilePickerModal > Vertical {
        width: 90;
        height: 82%;
    }
    FilePickerModal #fp-recent-label,
    FilePickerModal #fp-browse-label {
        color: $accent;
        margin-top: 1;
        margin-bottom: 0;
    }
    FilePickerModal #fp-recent-list {
        height: auto;
        max-height: 6;
        border: solid $panel;
        margin-bottom: 1;
    }
    FilePickerModal BibDirectoryTree {
        height: 1fr;
        border: solid $panel;
        margin-bottom: 1;
    }
    FilePickerModal #fp-hint {
        color: $text-muted;
        height: 1;
        margin-bottom: 1;
    }
    """

    def __init__(self, recent_files: list[str], **kwargs):
        super().__init__(**kwargs)
        self._recent = [r for r in recent_files if Path(r).exists()]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]Open BibTeX File[/bold]", classes="modal-title")
            if self._recent:
                yield Label("Recent files", id="fp-recent-label")
                yield ListView(id="fp-recent-list")
            yield Label("Browse", id="fp-browse-label")
            yield BibDirectoryTree(Path.home(), id="fp-bib-tree")
            yield Static("[dim]Select a .bib file to open it[/dim]", id="fp-hint")
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        if self._recent:
            lv = self.query_one("#fp-recent-list", ListView)
            for path_str in self._recent:
                p = Path(path_str)
                lv.append(ListItem(Label(f"{p.name}  [dim]{p.parent}[/dim]")))

    @on(ListView.Selected, "#fp-recent-list")
    def on_recent_selected(self, event: ListView.Selected) -> None:
        idx = self.query_one("#fp-recent-list", ListView).index
        if idx is not None and idx < len(self._recent):
            self.dismiss(self._recent[idx])

    @on(DirectoryTree.FileSelected, "#fp-bib-tree")
    def on_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        self.dismiss(str(event.path))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ImportBibPickerModal(_FileBrowseMixin, _BaseModal["str | None"]):
    """Pick a single .bib file to import, filtered by name.

    Shares :class:`AddPDFModal`'s browsing model via :class:`_FileBrowseMixin`
    — list a download directory, filter by typing, ``Space`` previews the
    highlighted row, ``Enter``/``x`` choose it, submitting an existing
    directory path in the filter re-points the listing at that folder — the
    .bib counterpart of "choosing a single PDF".
    """

    _ID_PREFIX = "ibp"
    _GLOB = "*.bib"
    _NOUN = ".bib file"

    BINDINGS = [
        Binding(SAVE, "choose", "Choose", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    ImportBibPickerModal > Vertical {
        width: 80;
        height: 30;
    }
    ImportBibPickerModal Input {
        margin-bottom: 1;
    }
    ImportBibPickerModal ListView {
        height: 1fr;
        border: solid $panel;
        margin-bottom: 1;
    }
    ImportBibPickerModal #ibp-hint {
        color: $text-muted;
        margin-bottom: 1;
    }
    ImportBibPickerModal #ibp-nav-hint {
        color: $text-muted;
        height: auto;
        margin-bottom: 1;
    }
    ImportBibPickerModal #ibp-error {
        color: $error;
    }
    """

    def __init__(self, download_dir: str = "", **kwargs):
        super().__init__(**kwargs)
        self._download_dir = download_dir or str(Path.home() / "Downloads")
        self._all_files: list[Path] = []
        self._filtered: list[Path] = []

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]Import .bib File[/bold]", classes="modal-title")
            yield Static("", id="ibp-hint")
            yield Input(
                placeholder="type to filter, or paste a file/folder path…",
                id="ibp-filter",
            )
            yield ListView(id="ibp-list")
            yield Static(
                "[dim]↓/↑ navigate · Space preview · Enter/x choose · s search[/dim]",
                id="ibp-nav-hint",
            )
            yield Static("", id="ibp-error")
            with Horizontal(classes="modal-buttons"):
                yield Button("Choose", variant="primary", id="btn-choose")
                yield Button("Cancel", id="btn-cancel")

    @on(Input.Changed, "#ibp-filter")
    def _on_filter(self, event: Input.Changed) -> None:
        self._filter_changed(event)

    @on(Input.Submitted, "#ibp-filter")
    def _on_filter_submitted(self, event: Input.Submitted) -> None:
        self._filter_submitted(event)

    @on(ListView.Selected)
    def _on_list_selected(self, event: ListView.Selected) -> None:
        self._list_selected(event)

    def _choose_path(self, path: Path) -> None:
        error = self.query_one("#ibp-error", Static)
        if not path.is_file():
            error.update(f"File not found: {path}")
            return
        if path.suffix.lower() != ".bib":
            error.update(f"Not a .bib file: {path.name}")
            return
        self.dismiss(str(path))

    def action_choose(self) -> None:
        self._confirm()
