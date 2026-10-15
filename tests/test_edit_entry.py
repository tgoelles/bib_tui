"""Tests for editing an entry through the app (form and raw BibTeX) and writing it."""

from textual.widgets import DataTable, TextArea

from bibtui.app import BibTuiApp
from bibtui.bib import parser
from bibtui.widgets.entry_detail import EntryDetail
from bibtui.widgets.entry_list import EntryList
from bibtui.widgets.modals import RawEditModal

SOURCE = """\
@article{Old2020,
  title = {First},
  author = {Doe, J},
  year = {2020},
}

@article{Other2021,
  title = {Second},
  author = {Roe, R},
  year = {2021},
}
"""


def _write_bib(tmp_path):
    path = tmp_path / "lib.bib"
    path.write_text(SOURCE, encoding="utf-8")
    return path


async def _select(app, pilot, key: str) -> None:
    el = app.query_one(EntryList)
    idx = next(i for i, e in enumerate(el._filtered) if e.key == key)
    app.query_one(DataTable).move_cursor(row=idx)
    await pilot.pause()


async def _raw_edit(app, pilot, key: str, old: str, new: str) -> None:
    """Open the raw editor on *key*, replace *old* with *new*, and write."""
    await _select(app, pilot, key)
    app.query_one(EntryDetail).toggle_view()
    app.action_edit_entry()
    await pilot.pause()
    modal = app.screen
    assert isinstance(modal, RawEditModal)
    area = modal.query_one("#raw-edit-area", TextArea)
    assert old in area.text
    area.text = area.text.replace(old, new)
    modal.action_save()
    await pilot.pause()


async def test_raw_edit_updates_entry_and_writes(tmp_path) -> None:
    path = _write_bib(tmp_path)
    app = BibTuiApp(str(path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await _raw_edit(app, pilot, "Old2020", "{First}", "{First edited}")
        app.action_save()
        await pilot.pause()

    by_key = {e.key: e for e in parser.load(str(path))}
    assert by_key["Old2020"].title == "First edited"
    assert by_key["Other2021"].title == "Second"


async def test_raw_edit_renaming_key_replaces_the_opened_entry(tmp_path) -> None:
    """Changing the cite key used to silently discard the edit (#77)."""
    path = _write_bib(tmp_path)
    app = BibTuiApp(str(path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await _raw_edit(app, pilot, "Old2020", "{Old2020,", "{New2020,")
        assert [e.key for e in app._entries] == ["New2020", "Other2021"]
        assert app.query_one(EntryList).selected_entry.key == "New2020"
        app.action_save()
        await pilot.pause()

    # parser.save sees a rename as delete + add, so the entry moves to the end.
    by_key = {e.key: e for e in parser.load(str(path))}
    assert sorted(by_key) == ["New2020", "Other2021"]
    assert by_key["New2020"].title == "First"


async def test_raw_edit_renaming_to_existing_key_is_refused(tmp_path) -> None:
    """Renaming onto another entry's key used to overwrite that entry (#77)."""
    path = _write_bib(tmp_path)
    app = BibTuiApp(str(path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await _raw_edit(app, pilot, "Old2020", "{Old2020,", "{Other2021,")
        assert [(e.key, e.title) for e in app._entries] == [
            ("Old2020", "First"),
            ("Other2021", "Second"),
        ]
        assert not app._dirty
