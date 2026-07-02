"""Tests for the NewEntryModal (press `n`) and its app wiring."""

from textual.widgets import Input, Select

from bibtui.app import BibTuiApp
from bibtui.bib.models import COMMON_FIELDS, ENTRY_TYPES, BibEntry
from bibtui.widgets.modals import EditModal, NewEntryModal

BIB = "tests/bib_examples/MyCollection.bib"


async def _open_modal(app, pilot):
    """Push a NewEntryModal and return (modal, result-dict)."""
    result: dict = {}
    modal = NewEntryModal()
    app.push_screen(modal, lambda r: result.__setitem__("entry", r))
    await pilot.pause()
    return modal, result


async def _open_edit(app, pilot, entry):
    """Push an EditModal and return (modal, result-dict)."""
    result: dict = {}
    modal = EditModal(entry)
    app.push_screen(modal, lambda r: result.__setitem__("entry", r))
    await pilot.pause()
    await pilot.pause()
    return modal, result


# ---------------------------------------------------------------------------
# Field rendering per entry type
# ---------------------------------------------------------------------------


async def test_article_shows_required_fields() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot)
        # article requires author/title/journal/year
        for name in ENTRY_TYPES["article"]["required"]:
            assert modal.query(f"#field-{name}")


async def test_switching_type_reshapes_fields() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot)
        # article has journal, not publisher
        assert modal.query("#field-journal")
        assert not modal.query("#field-publisher")

        modal.query_one("#new-type", Select).value = "book"
        await pilot.pause()

        # book has publisher, not journal
        assert modal.query("#field-publisher")
        assert not modal.query("#field-journal")


async def test_required_hint_updates_with_type() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot)
        modal.query_one("#new-type", Select).value = "misc"
        await pilot.pause()
        # misc has no required fields
        assert modal._current_type == "misc"
        assert ENTRY_TYPES["misc"]["required"] == []


async def test_values_preserved_across_type_switch() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot)
        modal.query_one("#field-author", Input).value = "Smith, John"
        await pilot.pause()

        modal.query_one("#new-type", Select).value = "book"
        await pilot.pause()
        # author survives the switch (present in both types)
        assert modal.query_one("#field-author", Input).value == "Smith, John"


# ---------------------------------------------------------------------------
# Cite-key auto-suggest
# ---------------------------------------------------------------------------


async def test_citekey_autofilled_from_author_year() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot)
        modal.query_one("#field-author", Input).value = "Smith, John"
        modal.query_one("#field-year", Input).value = "2023"
        await pilot.pause()
        assert modal.query_one("#new-key", Input).value == "Smith2023"


async def test_manual_key_edit_stops_autofill() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot)
        modal.query_one("#field-author", Input).value = "Smith, John"
        await pilot.pause()
        # user overrides the key
        modal.query_one("#new-key", Input).value = "MyKey2020"
        await pilot.pause()
        # further author/year edits must not clobber it
        modal.query_one("#field-year", Input).value = "1999"
        await pilot.pause()
        assert modal.query_one("#new-key", Input).value == "MyKey2020"


# ---------------------------------------------------------------------------
# Custom fields
# ---------------------------------------------------------------------------


async def test_add_custom_field_saved_to_raw_fields() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, result = await _open_modal(app, pilot)
        modal.query_one("#new-key", Input).value = "Custom2024"
        modal.query_one("#field-author", Input).value = "A"
        modal.query_one("#field-title", Input).value = "T"
        modal.query_one("#field-journal", Input).value = "J"
        modal.query_one("#field-year", Input).value = "2024"
        modal._add_custom_field("note")
        await pilot.pause()
        assert modal.query("#field-note")
        modal.query_one("#field-note", Input).value = "a personal note"
        modal._save()
        await pilot.pause()

        entry = result["entry"]
        assert entry is not None
        assert entry.raw_fields["note"] == "a personal note"


async def test_custom_field_name_sanitized_and_deduped() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot)
        modal._add_custom_field("Url Date")  # -> urldate
        await pilot.pause()
        assert modal.query("#field-urldate")
        # adding a field that already exists as a type field is a no-op
        before = len(modal._custom_names)
        modal._add_custom_field("journal")  # already an article field
        await pilot.pause()
        assert len(modal._custom_names) == before


async def test_common_field_select_adds_and_resets() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot)
        sel = modal.query_one("#add-common", Select)
        sel.value = "isbn"  # not an article field, not promoted
        await pilot.pause()
        await pilot.pause()
        # field added, no phantom entry from the reset, dropdown cleared
        assert modal._custom_names == ["isbn"]
        assert modal.query("#field-isbn")
        assert not isinstance(sel.value, str)


async def test_common_dropdown_excludes_present_fields() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test(size=(100, 45)) as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot)

        def options():
            sel = modal.query_one("#add-common", Select)
            return {value for _, value in sel._options}

        # doi/note are shown as fields already, so they aren't offered
        opts = options()
        assert "doi" not in opts
        assert "note" not in opts
        assert "isbn" in opts

        # adding a field removes it from the dropdown…
        modal._add_custom_field("isbn")
        await pilot.pause()
        assert "isbn" not in options()

        # …and removing it puts it back
        modal._remove_custom_field("isbn")
        await pilot.pause()
        assert "isbn" in options()

        # switching type re-filters: publisher becomes a book field
        modal.query_one("#new-type", Select).value = "book"
        await pilot.pause()
        assert "publisher" not in options()


async def test_all_type_fields_are_visible_height() -> None:
    # Regression: nested Vertical containers defaulted to height 1fr and clipped
    # the field inputs; they must be height:auto so every input renders.
    app = BibTuiApp(BIB)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot)
        inputs = list(modal.query("#type-fields Input"))
        assert inputs
        assert all(w.region.height > 0 for w in inputs)


async def test_remove_custom_field() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot)
        modal._add_custom_field("isbn")
        await pilot.pause()
        assert modal.query("#field-isbn")
        modal._remove_custom_field("isbn")
        await pilot.pause()
        assert not modal.query("#field-isbn")
        assert "isbn" not in modal._custom_names


def test_common_fields_are_lowercase_unique() -> None:
    assert COMMON_FIELDS == [f.lower() for f in COMMON_FIELDS]
    assert len(COMMON_FIELDS) == len(set(COMMON_FIELDS))


# ---------------------------------------------------------------------------
# Save / validation
# ---------------------------------------------------------------------------


async def test_save_builds_entry_with_type_and_fields() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, result = await _open_modal(app, pilot)
        modal.query_one("#new-key", Input).value = "Doe2021"
        modal.query_one("#field-title", Input).value = "A Title"
        modal.query_one("#field-author", Input).value = "Doe, Jane"
        modal.query_one("#field-journal", Input).value = "Nature"
        modal.query_one("#field-year", Input).value = "2021"
        modal._save()
        await pilot.pause()

        entry = result["entry"]
        assert entry.key == "Doe2021"
        assert entry.entry_type == "article"
        assert entry.title == "A Title"
        assert entry.author == "Doe, Jane"
        assert entry.journal == "Nature"


async def test_cursor_starts_in_first_field_not_key() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test(size=(100, 45)) as pilot:
        await pilot.pause()
        modal = NewEntryModal()
        app.push_screen(modal)
        await pilot.pause()
        await pilot.pause()
        focused = app.focused
        assert focused is not None
        assert focused.id != "new-key"
        assert focused.id == "field-author"


async def test_key_with_spaces_blocked() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, result = await _open_modal(app, pilot)
        modal.query_one("#new-key", Input).value = "bad key with spaces"
        modal._save()
        await pilot.pause()
        assert "entry" not in result
        assert isinstance(app.screen, NewEntryModal)


async def test_invalid_bibtex_key_blocked() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, result = await _open_modal(app, pilot)
        # A brace in the key does not round-trip through bibtexparser.
        modal.query_one("#new-key", Input).value = "bad{key"
        modal._save()
        await pilot.pause()
        assert "entry" not in result


async def test_new_entry_gets_date_added() -> None:
    from bibtui.utils.dates import extract_date_added

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        entry = BibEntry(key="Fresh2099", entry_type="article", title="X")
        app._on_new_entry_done(entry)
        await pilot.pause()
        added = next(e for e in app._entries if e.key == "Fresh2099")
        assert extract_date_added(added.raw_fields)


async def test_existing_date_added_not_overwritten() -> None:
    from bibtui.utils.dates import extract_date_added

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        entry = BibEntry(
            key="Old2000",
            entry_type="article",
            raw_fields={"date-added": "2000-01-01T00:00:00"},
        )
        app._on_new_entry_done(entry)
        await pilot.pause()
        added = next(e for e in app._entries if e.key == "Old2000")
        assert extract_date_added(added.raw_fields) == "2000-01-01T00:00:00"


async def test_edit_preserves_hidden_date_added() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test(size=(100, 45)) as pilot:
        await pilot.pause()
        entry = BibEntry(
            key="Has2020",
            entry_type="article",
            title="T",
            author="A",
            raw_fields={"date-added": "2020-01-01T00:00:00"},
        )
        modal, result = await _open_edit(app, pilot, entry)
        # date-added is hidden, not shown as an editable field
        assert not modal.query("#field-date-added")
        assert "date-added" not in modal._custom_names
        modal.query_one("#field-title", Input).value = "T2"
        modal._save()
        await pilot.pause()
        assert result["entry"].raw_fields["date-added"] == "2020-01-01T00:00:00"


async def test_empty_key_blocks_save() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, result = await _open_modal(app, pilot)
        modal.query_one("#field-title", Input).value = "No key here"
        modal._save()
        await pilot.pause()
        # modal is not dismissed and stays on screen
        assert "entry" not in result
        assert isinstance(app.screen, NewEntryModal)


async def test_empty_optional_values_not_written() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, result = await _open_modal(app, pilot)
        modal.query_one("#new-key", Input).value = "Bare2020"
        modal.query_one("#field-author", Input).value = "A"
        modal.query_one("#field-title", Input).value = "T"
        modal.query_one("#field-journal", Input).value = "J"
        modal.query_one("#field-year", Input).value = "2020"
        # leave the optional volume/pages/etc. empty
        modal._save()
        await pilot.pause()
        entry = result["entry"]
        # empty optional fields don't leak into raw_fields
        assert "volume" not in entry.raw_fields
        assert "pages" not in entry.raw_fields


# ---------------------------------------------------------------------------
# Submit-time validation in the form
# ---------------------------------------------------------------------------


async def test_missing_required_blocks_and_highlights() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test(size=(100, 45)) as pilot:
        await pilot.pause()
        modal, result = await _open_modal(app, pilot)
        modal.query_one("#new-key", Input).value = "K2020"
        modal.query_one("#field-author", Input).value = "A"
        modal.query_one("#field-title", Input).value = "T"
        # journal + year left empty
        modal._save()
        await pilot.pause()
        assert "entry" not in result
        assert isinstance(app.screen, NewEntryModal)
        assert modal.query_one("#field-journal", Input).has_class("field-error")


async def test_autofix_requires_second_write() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test(size=(100, 45)) as pilot:
        await pilot.pause()
        modal, result = await _open_modal(app, pilot)
        modal.query_one("#new-key", Input).value = "K2021"
        modal.query_one("#field-author", Input).value = "A"
        modal.query_one("#field-title", Input).value = "Cats & Dogs"
        modal.query_one("#field-journal", Input).value = "Nature"
        modal.query_one("#field-year", Input).value = "2021"
        modal.query_one("#field-pages", Input).value = "12-23"

        # first Write applies fixes into the form, does not write
        modal._save()
        await pilot.pause()
        assert "entry" not in result
        assert modal.query_one("#field-title", Input).value == r"Cats \& Dogs"
        assert modal.query_one("#field-pages", Input).value == "12--23"
        assert modal.query_one("#field-title", Input).has_class("field-fixed")

        # second Write goes through with the normalized values
        modal._save()
        await pilot.pause()
        assert result["entry"].title == r"Cats \& Dogs"
        assert result["entry"].get_field("pages") == "12--23"


async def test_edit_missing_required_writes_with_warning() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test(size=(100, 45)) as pilot:
        await pilot.pause()
        # journal + year already empty on the entry being edited
        entry = BibEntry(key="Old2000", entry_type="article", title="T", author="A")
        modal, result = await _open_edit(app, pilot, entry)
        modal.query_one("#field-title", Input).value = "T2"
        modal._save()
        await pilot.pause()
        # not blocked — writes despite the pre-existing gaps
        assert result["entry"] is not None
        assert result["entry"].title == "T2"
        # original entry object left untouched until write
        assert entry.title == "T"


async def test_edit_emptying_required_field_blocks() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test(size=(100, 45)) as pilot:
        await pilot.pause()
        entry = BibEntry(
            key="Full2020",
            entry_type="article",
            title="T",
            author="A",
            journal="Nature",
            year="2020",
        )
        modal, result = await _open_edit(app, pilot, entry)
        modal.query_one("#field-journal", Input).value = ""  # clear a filled field
        modal._save()
        await pilot.pause()
        assert "entry" not in result
        assert modal.query_one("#field-journal", Input).has_class("field-error")


# ---------------------------------------------------------------------------
# App wiring
# ---------------------------------------------------------------------------


async def test_on_new_entry_done_adds_entry() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        before = len(app._entries)
        new = BibEntry(key="Brandnew2030", entry_type="article", title="Fresh")
        app._on_new_entry_done(new)
        await pilot.pause()
        assert len(app._entries) == before + 1
        assert any(e.key == "Brandnew2030" for e in app._entries)
        assert app._dirty is True


# ---------------------------------------------------------------------------
# Field ordering / keywords exclusion
# ---------------------------------------------------------------------------


async def test_doi_and_note_promoted_keywords_excluded() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test(size=(100, 45)) as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot)
        order = [
            w.id.removeprefix("field-")
            for w in modal.query("#type-fields Input, #type-fields TextArea")
        ]
        assert "keywords" not in order
        assert "note" in order
        # doi sits right after the required fields, ahead of other optionals
        assert order.index("doi") < order.index("volume")
        assert order.index("doi") < order.index("note")


async def test_keywords_never_addable_as_custom() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot)
        modal._add_custom_field("keywords")
        await pilot.pause()
        assert "keywords" not in modal._custom_names
        assert not modal.query("#field-keywords")


async def test_autofilled_key_marked_auto() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot)
        key_input = modal.query_one("#new-key", Input)
        modal.query_one("#field-author", Input).value = "Smith, John"
        await pilot.pause()
        assert key_input.has_class("auto")
        # editing the key by hand drops the auto styling
        key_input.value = "Custom2020"
        await pilot.pause()
        assert not key_input.has_class("auto")


# ---------------------------------------------------------------------------
# EditModal (shared dynamic form)
# ---------------------------------------------------------------------------


def _sample_entry() -> BibEntry:
    return BibEntry(
        key="Smith2020",
        entry_type="article",
        title="Old title",
        author="Smith, John",
        year="2020",
        journal="Nature",
        doi="10.1/x",
        keywords="ice, snow",
        rating=4,
        read_state="read",
        priority=2,
        raw_fields={"volume": "12", "mycustomfield": "keep"},
    )


async def test_edit_shows_real_field_names_no_keywords() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test(size=(100, 45)) as pilot:
        await pilot.pause()
        modal, _ = await _open_edit(app, pilot, _sample_entry())
        assert modal.query("#field-journal")  # real bibtex name, not "Journal / Booktitle"
        assert modal.query("#field-doi")
        assert not modal.query("#field-keywords")
        # a non-standard field it carries is editable as a custom row
        assert "mycustomfield" in modal._custom_names
        assert modal.query("#field-mycustomfield")


async def test_edit_preserves_keywords_and_metadata() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test(size=(100, 45)) as pilot:
        await pilot.pause()
        entry = _sample_entry()
        modal, result = await _open_edit(app, pilot, entry)
        modal.query_one("#field-title", Input).value = "New title"
        modal._save()
        await pilot.pause()
        out = result["entry"]
        assert out.title == "New title"
        # untouched, form-excluded state survives the round-trip
        assert out.keywords == "ice, snow"
        assert out.rating == 4
        assert out.read_state == "read"
        assert out.priority == 2
        assert out.raw_fields["mycustomfield"] == "keep"


async def test_edit_can_change_entry_type() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test(size=(100, 45)) as pilot:
        await pilot.pause()
        entry = _sample_entry()
        modal, result = await _open_edit(app, pilot, entry)
        modal.query_one("#new-type", Select).value = "book"
        await pilot.pause()
        modal._save()
        await pilot.pause()
        assert result["entry"].entry_type == "book"


async def test_edit_clearing_field_removes_it() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test(size=(100, 45)) as pilot:
        await pilot.pause()
        entry = _sample_entry()
        modal, result = await _open_edit(app, pilot, entry)
        modal.query_one("#field-doi", Input).value = ""
        modal._save()
        await pilot.pause()
        assert result["entry"].doi == ""


async def test_on_new_entry_done_ignores_none() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        before = len(app._entries)
        app._on_new_entry_done(None)
        await pilot.pause()
        assert len(app._entries) == before
