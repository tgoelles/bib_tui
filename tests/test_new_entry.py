"""Tests for the NewEntryModal (press `n`) and its app wiring."""

from textual.widgets import Input, Select

from bibtui.app import BibTuiApp
from bibtui.bib.models import COMMON_FIELDS, ENTRY_TYPES, BibEntry
from bibtui.widgets.modals import NewEntryModal

BIB = "tests/bib_examples/MyCollection.bib"


async def _open_modal(app, pilot):
    """Push a NewEntryModal and return (modal, result-dict)."""
    result: dict = {}
    modal = NewEntryModal()
    app.push_screen(modal, lambda r: result.__setitem__("entry", r))
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


async def test_remove_custom_field() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot)
        modal._add_custom_field("note")
        await pilot.pause()
        assert modal.query("#field-note")
        modal._remove_custom_field("note")
        await pilot.pause()
        assert not modal.query("#field-note")
        assert "note" not in modal._custom_names


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
        modal._save()
        await pilot.pause()

        entry = result["entry"]
        assert entry.key == "Doe2021"
        assert entry.entry_type == "article"
        assert entry.title == "A Title"
        assert entry.author == "Doe, Jane"
        assert entry.journal == "Nature"


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


async def test_empty_values_not_written() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, result = await _open_modal(app, pilot)
        modal.query_one("#new-key", Input).value = "Bare2020"
        modal._save()
        await pilot.pause()
        entry = result["entry"]
        # no optional/empty fields leaked into raw_fields
        assert entry.raw_fields == {}
        assert entry.title == ""


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


async def test_on_new_entry_done_ignores_none() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        before = len(app._entries)
        app._on_new_entry_done(None)
        await pilot.pause()
        assert len(app._entries) == before
