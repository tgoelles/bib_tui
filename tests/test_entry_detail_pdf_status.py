"""Regression tests for the entry-detail PDF status icon and action buttons.

Bug report: on macOS, after fetching a PDF the table's file-status column
shows the PDF as linked (filled square), and the file can be opened, but the
detail panel's PDF Actions still only offer Fetch/Add — Open/Copy/Delete stay
disabled as if no PDF exists.

Root cause: the table's status column and the app's fetch/autolink logic all
resolve "is there a local PDF?" through ``find_pdf_for_entry()``, which falls
back to a glob-by-entry-key search when the exact stored path doesn't
resolve. ``EntryDetail._file_icon`` (which also drives whether the action
buttons are enabled) used to call ``os.path.exists()`` on the exact stored
path only, with no such fallback — so any situation where the literal path
in the .bib file's file field doesn't hit but the file is actually in the PDF
library dir (stale filename, or a macOS filename-normalization mismatch) left
the two widgets disagreeing.

These tests pin the fix: the detail panel must agree with the table in every
case ``find_pdf_for_entry`` was already designed to handle.
"""

import unicodedata


from bibtui.app import BibTuiApp
from bibtui.bib.models import BibEntry
from bibtui.widgets.columns import _file_icon as table_file_icon
from bibtui.widgets.entry_detail import EntryDetail

BIB = "tests/bib_examples/MyCollection.bib"


async def _show_and_get_states(app, pilot, tmp_path, entry, monkeypatch=None):
    detail = app.query_one(EntryDetail)
    detail.set_pdf_base_dir(str(tmp_path))
    detail.show_entry(entry)
    await pilot.pause()

    icon = detail._file_icon(entry)
    fetch_disabled = detail.query_one("#detail-pdf-fetch").disabled
    add_disabled = detail.query_one("#detail-pdf-add").disabled
    open_disabled = detail.query_one("#detail-pdf-open").disabled
    delete_disabled = detail.query_one("#detail-pdf-delete").disabled
    return icon, fetch_disabled, add_disabled, open_disabled, delete_disabled


async def test_detail_matches_table_when_only_key_glob_matches(tmp_path) -> None:
    """Stored file field is stale; only the entry-key glob finds the PDF.

    This is exactly the shape of the reported bug: the table already shows a
    filled square (it uses the glob fallback), so the detail panel's actions
    must also treat the PDF as present.
    """
    entry = BibEntry(
        key="Smith2023",
        entry_type="article",
        file=":Smith2023 - Old Title.pdf:PDF",
    )
    (tmp_path / "Smith2023 - Renamed Title.pdf").write_bytes(b"%PDF-1.4")

    assert table_file_icon(entry, str(tmp_path)) == "■"

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        icon, fetch_dis, add_dis, open_dis, delete_dis = await _show_and_get_states(
            app, pilot, tmp_path, entry
        )

    assert icon == "■"
    assert open_dis is False
    assert delete_dis is False
    assert fetch_dis is True
    assert add_dis is True


async def test_detail_matches_table_on_nfc_nfd_filename_mismatch(tmp_path) -> None:
    """macOS-flavoured case: the PDF on disk and the .bib file field encode
    the same accented filename using different Unicode normal forms."""
    nfc_name = unicodedata.normalize("NFC", "Müller2023 - Title.pdf")
    nfd_name = unicodedata.normalize("NFD", nfc_name)
    assert nfc_name != nfd_name
    (tmp_path / nfd_name).write_bytes(b"%PDF-1.4")

    entry = BibEntry(key="Mueller2023", entry_type="article", file=f":{nfc_name}:PDF")

    assert table_file_icon(entry, str(tmp_path)) == "■"

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        icon, fetch_dis, add_dis, open_dis, delete_dis = await _show_and_get_states(
            app, pilot, tmp_path, entry
        )

    assert icon == "■"
    assert open_dis is False
    assert fetch_dis is True
    assert add_dis is True


async def test_detail_shows_missing_when_no_match_at_all(tmp_path) -> None:
    entry = BibEntry(key="Nobody2023", entry_type="article", file=":Nobody2023.pdf:PDF")

    assert table_file_icon(entry, str(tmp_path)) == "□"

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        icon, fetch_dis, add_dis, open_dis, delete_dis = await _show_and_get_states(
            app, pilot, tmp_path, entry
        )

    assert icon == "□"
    assert open_dis is True
    assert fetch_dis is False
    assert add_dis is False
