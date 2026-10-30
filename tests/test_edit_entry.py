"""Tests for editing an entry through the app (form and raw BibTeX) and writing it."""

import dataclasses

from conftest import DummyList, wire_dummies
from textual.widgets import DataTable, Input, Static, TextArea

from bibtui.app import BibTuiApp
from bibtui.bib import parser
from bibtui.bib.models import BibEntry
from bibtui.widgets.entry_detail import EntryDetail
from bibtui.widgets.entry_list import EntryList
from bibtui.widgets.modals import EditModal, RawEditModal

BIB = "tests/bib_examples/MyCollection.bib"

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
    """Renaming onto another entry's key used to overwrite that entry (#77).

    The editor must stay open with an error and the user's text intact, so a
    typo in the key doesn't throw away the rest of the edit."""
    path = _write_bib(tmp_path)
    app = BibTuiApp(str(path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await _raw_edit(app, pilot, "Old2020", "{Old2020,", "{Other2021,")

        modal = app.screen
        assert isinstance(modal, RawEditModal)
        assert "{Other2021," in modal.query_one("#raw-edit-area", TextArea).text
        error = str(modal.query_one("#raw-edit-error", Static).render())
        assert "Other2021" in error and "already used" in error

        assert [(e.key, e.title) for e in app._entries] == [
            ("Old2020", "First"),
            ("Other2021", "Second"),
        ]
        assert not app._dirty


async def test_form_edit_updates_entry_and_writes(tmp_path) -> None:
    path = _write_bib(tmp_path)
    app = BibTuiApp(str(path))
    async with app.run_test(size=(100, 45)) as pilot:
        await pilot.pause()
        await _select(app, pilot, "Other2021")
        app.action_edit_entry()
        await pilot.pause()
        await pilot.pause()
        modal = app.screen
        assert isinstance(modal, EditModal)
        modal.query_one("#field-title", Input).value = "Second edited"
        modal.action_save()
        await pilot.pause()
        app.action_save()
        await pilot.pause()

    assert path.read_text(encoding="utf-8") == SOURCE.replace(
        "{Second}", "{Second edited}"
    )


# ---------------------------------------------------------------------------
# _on_edit_done after a rename (no running app)
# ---------------------------------------------------------------------------


class _FilteringList(DummyList):
    """An entry list whose active filter hides every entry."""

    active_preset = ("Unread", None)

    def refresh_entries(self, entries) -> None:
        super().refresh_entries(entries)
        self._filtered = []


def _rename(entry: BibEntry, new_key: str) -> BibEntry:
    return dataclasses.replace(entry, key=new_key)


def test_rename_hidden_by_filter_says_renamed(monkeypatch) -> None:
    app = BibTuiApp(BIB)
    entry = BibEntry(key="Old2020", entry_type="article", title="T")
    app._entries = [entry]
    _list, _detail, notes = wire_dummies(app, monkeypatch, dummy_list=_FilteringList())

    app._on_edit_done(_rename(entry, "New2020"), entry)

    messages = [m for m, _ in notes]
    assert "Renamed to 'New2020' — hidden by filter 'Unread'" in messages
    assert not any(m.startswith("Added") for m in messages)


def test_rename_warns_when_pdf_was_found_by_old_key(tmp_path, monkeypatch) -> None:
    (tmp_path / "Old2020 - Title.pdf").write_bytes(b"%PDF")
    app = BibTuiApp(BIB)
    app._config.pdf_base_dir = str(tmp_path)
    entry = BibEntry(key="Old2020", entry_type="article", title="T")
    app._entries = [entry]
    _list, _detail, notes = wire_dummies(app, monkeypatch)

    app._on_edit_done(_rename(entry, "New2020"), entry)

    warnings = [m for m, severity in notes if severity == "warning"]
    assert len(warnings) == 1
    assert "Old2020 - Title.pdf" in warnings[0]


def test_rename_keeps_quiet_when_file_field_links_the_pdf(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / "Old2020 - Title.pdf").write_bytes(b"%PDF")
    app = BibTuiApp(BIB)
    app._config.pdf_base_dir = str(tmp_path)
    entry = BibEntry(
        key="Old2020", entry_type="article", file=":Old2020 - Title.pdf:PDF"
    )
    app._entries = [entry]
    _list, _detail, notes = wire_dummies(app, monkeypatch)

    app._on_edit_done(_rename(entry, "New2020"), entry)

    assert [m for m, severity in notes if severity == "warning"] == []
