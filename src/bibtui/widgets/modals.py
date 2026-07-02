import re
from collections.abc import Iterable
from pathlib import Path
from typing import TypeVar

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
    Select,
    SelectionList,
    Static,
    Switch,
    TextArea,
)
from textual.widgets._selection_list import Selection

from bibtui.bib.citation_preview import available_csl_styles, default_csl_style_key
from bibtui.bib.citekeys import author_year_base
from bibtui.bib.models import COMMON_FIELDS, ENTRY_TYPES, BibEntry
from bibtui.bib.parser import (
    bibtex_str_to_entry,
    entry_to_bibtex_str,
    is_serializable_entry,
)
from bibtui.utils.config import Config
from bibtui.utils.dates import DATE_ADDED_KEYS

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
    import time

    age = time.time() - mtime
    if age < 60:
        return "just now"
    if age < 3600:
        return f"{int(age / 60)} min ago"
    if age < 86400:
        return f"{int(age / 3600)} hr ago"
    return f"{int(age / 86400)} days ago"


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


# Fields the New/Edit entry form never shows as editable inputs: keywords are
# managed separately through the Keywords modal (press `k`).
_FORM_EXCLUDED_FIELDS: set[str] = {"keywords"}

# Optional fields promoted to the top of the optional section (in this order)
# because they are the ones most people want to fill in right away.
_FORM_PROMOTED_FIELDS: list[str] = ["doi", "note"]

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
    ``doi`` and ``note`` are surfaced near the top; ``keywords`` is deliberately
    excluded — it is managed through the Keywords modal.
    """

    BINDINGS = [
        Binding("ctrl+s", "save", "Write", show=True),
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
    """

    # Only New auto-suggests a cite key; Edit keeps the existing key.
    _autofill_enabled: bool = False

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

    # -- compose -----------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._form_title(), classes="modal-title")
            with VerticalScroll(id="new-fields"):
                with Horizontal(classes="type-row"):
                    yield Label("Type")
                    yield Select(
                        [(t, t) for t in ENTRY_TYPES],
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

        Required fields first, then ``doi``/``note``, then the type's remaining
        optional fields. Keywords and already-added custom fields are omitted.
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

    def _save(self) -> None:
        entry = self._make_entry()
        if entry is None:
            return
        # Validate with bibtexparser before it can reach the .bib file.
        if not is_serializable_entry(entry):
            self.query_one("#new-error", Static).update(
                "Not valid BibTeX — check the cite key and field values "
                "for unbalanced { } braces."
            )
            return
        self.dismiss(entry)

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

    def _initial_type(self) -> str:
        return self._entry.entry_type

    def _form_title(self) -> str:
        return f"[bold]Edit Entry[/bold]  [dim]{self._entry.key}[/dim]"

    def _focus_after_mount(self) -> None:
        inputs = list(self.query("#type-fields Input"))
        if inputs:
            self.call_after_refresh(inputs[0].focus)

    def _make_entry(self) -> BibEntry | None:
        entry = self._entry
        entry.entry_type = self._current_type
        # Clear the content fields this form owns, then rewrite them from the
        # inputs. Keywords and metadata (rating/read_state/priority) are left
        # untouched on the entry.
        for name in _FORM_CONTENT_FIELDS:
            if name not in _FORM_EXCLUDED_FIELDS:
                entry.set_field(name, "")
        # Keep hidden auto-managed raw fields (e.g. date-added); rebuild the
        # rest from the form inputs.
        entry.raw_fields = {
            k: v
            for k, v in entry.raw_fields.items()
            if k in _FORM_HIDDEN_RAW_FIELDS
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
        key = self.query_one("#new-key", Input).value.strip()
        error = self.query_one("#new-error", Static)
        if not key:
            error.update("Cite key is required.")
            return None
        # bibtexparser tolerates a space in the key, but LaTeX \cite would break.
        if any(ch.isspace() for ch in key):
            error.update("Cite key cannot contain spaces.")
            return None
        entry = BibEntry(key=key, entry_type=self._current_type)
        self._collect_into(entry)
        return entry


class KeywordsModal(_BaseModal["tuple[str, set[str]] | None"]):
    """Keyword picker: select from all bib-wide keywords, add new ones."""

    BINDINGS = [
        Binding("ctrl+s", "save", "Write", show=True),
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
            yield SelectionList(id="kw-list")
            yield Static(
                "[dim]Esc close · Enter add new  |  ↓/↑ navigate · Space toggle · ⌫ delete everywhere[/dim]",
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
        Binding("ctrl+s", "save", "Write", show=True),
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
                "[dim]PDFs listed when you press [bold]a[/bold] to add an existing PDF. Defaults to ~/Downloads.[/dim]"
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
            ("e", "Edit entry (field form or raw BibTeX)"),
            ("k", "Edit keywords"),
            ("m", "Maximize/restore table pane"),
            (None, "Press m again to restore split view."),
            ("v", "Toggle raw / formatted view"),
        ],
    ),
    (
        "Add new entry",
        [
            ("n", "Create a new entry (pick type, fill fields, add custom)"),
            ("d", "Import entry by DOI (fetches metadata online)"),
            ("ctrl+v", "Paste a raw BibTeX entry from clipboard"),
            (None, "All methods reject duplicate cite keys."),
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
            ("Enter", "Add typed keyword"),
            ("Space", "Toggle selected keyword on/off"),
            ("⌫", "Delete highlighted keyword from all entries"),
            ("↓ / ↑", "Move between filter and list"),
        ],
    ),
    (
        "Entry state",
        [
            ("r", "Cycle read state"),
            ("p", "Cycle priority"),
            ("␣", "Show PDF"),
            ("b", "Open URL in browser (validates http/https)"),
            ("Shift+b", "Search OpenAlex (title first, then DOI)"),
            ("f", "Fetch PDF and link it to the entry"),
            ("a", "Add an existing PDF to the library and link it"),
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
            ("ctrl+p", "Open command palette"),
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
            ("ctrl+c", "Copy selected text (or cite key if none focused)"),
            (None, "Default copy variant for entries: cite key"),
            ("Shift+c", "Copy formatted citation (current citation style)"),
            (None, "Alternative copy variant: rendered citation text"),
            ("ctrl+shift+c", "Copy current BibTeX entry"),
            ("ctrl+y", "Copy current BibTeX entry (terminal-safe fallback)"),
            (None, "Citation styles are loaded from ~/.config/bibtui/csl"),
            (None, "Add more styles: github.com/citation-style-language/styles"),
            ("?", "Show this help"),
            ("ctrl+p", "Command palette (Settings + Library actions)"),
            ("maximize", "(palette) maximize focused pane"),
            ("Esc", "Clear search / close modal"),
            (None, "Clipboard uses OSC 52 — requires a modern terminal"),
            (None, "In all modals: Ctrl+S = Write/Save, Esc = Cancel"),
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
                "Cols: [bold]◉[/bold] state  [bold]![/bold] prio  "
                "[bold]◫[/bold] PDF  [bold]🔗[/bold] URL  Type  Year  "
                "Author  Journal  Title  Added  [bold]★[/bold]",
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
            "[dim]Web:[/dim] https://thomasgoelles.com\n"
            "[dim]Repo:[/dim]   https://github.com/tgoelles/bib_tui"
        )

    _SEARCH = """\
[bold]── Plain text ────────────────────────[/bold]
  Searches title, author, keywords, and key.
  Multiple tokens are ANDed (AND keyword optional).

[bold]── Field prefixes ────────────────────[/bold]
  [bold]a:[/bold] / [bold]author:[/bold]    filter by author
  [bold]t:[/bold] / [bold]title:[/bold]     filter by title
  [bold]j:[/bold] / [bold]journal:[/bold]   filter by journal
  [bold]k:[/bold] / [bold]kw:[/bold]        filter by keyword
  [bold]y:[/bold] / [bold]year:[/bold]      filter by year or range
  [bold]u:[/bold] / [bold]url:[/bold]       filter by URL
  [bold]c:[/bold] / [bold]citekey:[/bold]   filter by cite key

[bold]── Examples ──────────────────────────[/bold]
  [dim]glacier[/dim]                    all fields
  [dim]a:smith t:glacier[/dim]          combined
  [dim]j:nature AND y:2025[/dim]        journal + year
  [dim]y:2015-2023[/dim]                year range
  [dim]k:ice a:jones[/dim]              keyword + author
  [dim]c:smith2020[/dim]                exact cite key search"""

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
        Binding("ctrl+s", "save", "Write", show=True),
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
        Binding("ctrl+s", "do_import", "Import", show=True),
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


class AddPDFModal(_BaseModal["str | None"]):
    """Pick an existing PDF from the download directory, filter by name, and link it."""

    BINDINGS = [
        Binding("ctrl+s", "add", "Add", show=True),
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
        from pathlib import Path

        self._download_dir = download_dir or str(Path.home() / "Downloads")
        self._all_pdfs: list = []
        self._filtered: list = []

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(
                f"[bold]Add PDF[/bold]  [dim]{self._entry.key}[/dim]",
                classes="modal-title",
            )
            yield Static("", id="add-hint")
            yield Input(placeholder="type to filter…", id="add-filter")
            yield ListView(id="add-list")
            yield Static(
                "[dim]↓/↑ navigate · Space preview [/dim]",
                id="add-preview-hint",
            )
            yield Static("", id="add-error")
            with Horizontal(classes="modal-buttons"):
                yield Button("Add", variant="primary", id="btn-add")
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        self._scan()
        self.call_after_refresh(self.query_one("#add-filter", Input).focus)

    def _scan(self) -> None:
        from pathlib import Path

        dl = Path(self._download_dir).expanduser()
        hint = self.query_one("#add-hint", Static)
        if not dl.is_dir():
            hint.update(
                f"[dim]Download dir not found: {dl}  ·  enter a path manually[/dim]"
            )
            self._all_pdfs = []
        else:
            pdfs = sorted(
                dl.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True
            )
            self._all_pdfs = pdfs
            hint.update(
                f"[dim]{dl}  ·  {len(pdfs)} PDF{'s' if len(pdfs) != 1 else ''}[/dim]"
            )
        self._filtered = list(self._all_pdfs)
        self._refresh_list()

    def _refresh_list(self) -> None:
        lv = self.query_one(ListView)
        lv.clear()
        for p in self._filtered:
            stat = p.stat()
            size = stat.st_size
            size_str = (
                f"{size / 1048576:.1f} MB"
                if size >= 1048576
                else f"{size / 1024:.0f} KB"
            )
            age = _format_age(stat.st_mtime)
            lv.append(ListItem(Label(f"{p.name}  [dim]{size_str}  {age}[/dim]")))

    @on(Input.Changed, "#add-filter")
    def _on_filter(self, event: Input.Changed) -> None:
        q = event.value.strip().lower()
        self._filtered = (
            [p for p in self._all_pdfs if q in p.name.lower()]
            if q
            else list(self._all_pdfs)
        )
        self._refresh_list()

    def on_key(self, event: events.Key) -> None:
        """Down in the Input moves focus to the list; Up from the first item returns focus."""
        lv = self.query_one(ListView)
        inp = self.query_one("#add-filter", Input)
        if self.focused is inp and event.key == "down" and self._filtered:
            lv.focus()
            event.stop()
        elif self.focused is lv and event.key == "up" and (lv.index or 0) == 0:
            inp.focus()
            event.stop()
        elif self.focused is lv and event.key == "space":
            self._preview_selected()
            event.stop()

    def _preview_selected(self) -> None:
        import platform
        import subprocess

        lv = self.query_one(ListView)
        idx = lv.index
        if idx is None or idx >= len(self._filtered):
            return
        path = self._filtered[idx]
        try:
            if platform.system() == "Darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:
            self.query_one("#add-error", Static).update(f"Could not open: {e}")

    @on(Input.Submitted, "#add-filter")
    def _on_filter_submitted(self, _: Input.Submitted) -> None:
        self._confirm()

    @on(ListView.Selected)
    def _on_list_selected(self, event: ListView.Selected) -> None:
        idx = self.query_one(ListView).index
        if idx is not None and idx < len(self._filtered):
            self._add_path(self._filtered[idx])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-add":
            self._confirm()

    def _confirm(self) -> None:
        from pathlib import Path

        lv = self.query_one(ListView)
        idx = lv.index
        if self._filtered and idx is not None and idx < len(self._filtered):
            self._add_path(self._filtered[idx])
        else:
            # Fallback: treat the filter text as a custom path
            val = self.query_one("#add-filter", Input).value.strip()
            if val:
                self._add_path(Path(val))
            else:
                self.query_one("#add-error", Static).update(
                    "Select a file or enter a path."
                )

    def _add_path(self, src) -> None:
        from pathlib import Path

        from bibtui.pdf.fetcher import FetchError, add_pdf

        error = self.query_one("#add-error", Static)
        error.update("")
        try:
            dest = add_pdf(Path(src), self._entry, self._base_dir)
            self.dismiss(str(dest))
        except FetchError as exc:
            error.update(str(exc))

    def action_add(self) -> None:
        self._confirm()

    def action_cancel(self) -> None:
        self.dismiss(None)


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
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._entry = entry
        self._dest_dir = dest_dir
        self._email = unpaywall_email
        self._openalex_api_key = openalex_api_key
        self._overwrite = overwrite
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
        title = "Could not fetch PDF for this entry."
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
