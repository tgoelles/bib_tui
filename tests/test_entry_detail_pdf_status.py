"""Regression tests for the entry-detail PDF status label and the PDF
actions menu's row filtering agreeing with the table's file-status column.

Bug report (original): on macOS, after fetching a PDF the table's
file-status column showed the PDF as linked (filled square), and the file
could be opened, but the detail panel's PDF Actions still only offered
Fetch/Add — Open/Copy/Delete stayed disabled as if no PDF existed.

Root cause: the table's status column and the app's fetch/autolink logic all
resolved "is there a local PDF?" through ``find_pdf_for_entry()``, which
falls back to a glob-by-entry-key search when the exact stored path doesn't
resolve. The detail pane used to have its own separate copy of that
classification with no such fallback — so any situation where the literal
path in the .bib file's file field didn't hit but the file was actually in
the PDF library dir (stale filename, or a macOS filename-normalization
mismatch) left the two widgets disagreeing.

Fix (now): both the table (``columns._file_icon``) and the detail
pane/PDF-actions-menu (``EntryDetail._refresh_content``,
``PdfActionsModal.__init__``) derive their state from one shared function,
``pdf.paths.pdf_link_state`` — these tests pin that every consumer of it
agrees, for every case ``find_pdf_for_entry`` was already designed to
handle.
"""

import unicodedata

from bibtui.app import BibTuiApp
from bibtui.bib.models import BibEntry
from bibtui.pdf.paths import pdf_link_state
from bibtui.widgets.columns import _file_icon as table_file_icon
from bibtui.widgets.entry_detail import EntryDetail
from bibtui.widgets.modals import PdfActionsModal

BIB = "tests/bib_examples/MyCollection.bib"


async def _show_and_get_status_text(app, pilot, tmp_path, entry) -> str:
    detail = app.query_one(EntryDetail)
    detail.set_pdf_base_dir(str(tmp_path))
    detail.show_entry(entry)
    await pilot.pause()
    label = detail.query_one("#detail-pdf-status")
    return str(label.render())


async def test_detail_matches_table_when_only_key_glob_matches(tmp_path) -> None:
    """Stored file field is stale; only the entry-key glob finds the PDF.

    This is exactly the shape of the reported bug: the table already shows a
    filled square (it uses the glob fallback), so the detail panel and the
    PDF actions menu must also treat the PDF as present.
    """
    entry = BibEntry(
        key="Smith2023",
        entry_type="article",
        file=":Smith2023 - Old Title.pdf:PDF",
    )
    (tmp_path / "Smith2023 - Renamed Title.pdf").write_bytes(b"%PDF-1.4")

    assert table_file_icon(entry, str(tmp_path)) == "■"
    assert pdf_link_state(entry.file, entry.key, str(tmp_path)) == "found"

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        status_text = await _show_and_get_status_text(app, pilot, tmp_path, entry)

    assert "■" in status_text

    modal = PdfActionsModal(entry, str(tmp_path))
    keys = modal._available
    assert keys == {"open", "copy_file", "copy_path", "delete"}


async def test_detail_matches_table_on_nfc_nfd_filename_mismatch(tmp_path) -> None:
    """macOS-flavoured case: the PDF on disk and the .bib file field encode
    the same accented filename using different Unicode normal forms."""
    nfc_name = unicodedata.normalize("NFC", "Müller2023 - Title.pdf")
    nfd_name = unicodedata.normalize("NFD", nfc_name)
    assert nfc_name != nfd_name
    (tmp_path / nfd_name).write_bytes(b"%PDF-1.4")

    entry = BibEntry(key="Mueller2023", entry_type="article", file=f":{nfc_name}:PDF")

    assert table_file_icon(entry, str(tmp_path)) == "■"
    assert pdf_link_state(entry.file, entry.key, str(tmp_path)) == "found"

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        status_text = await _show_and_get_status_text(app, pilot, tmp_path, entry)

    assert "■" in status_text


async def test_detail_shows_missing_when_no_match_at_all(tmp_path) -> None:
    entry = BibEntry(key="Nobody2023", entry_type="article", file=":Nobody2023.pdf:PDF")

    assert table_file_icon(entry, str(tmp_path)) == "□"
    assert pdf_link_state(entry.file, entry.key, str(tmp_path)) == "missing"

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        status_text = await _show_and_get_status_text(app, pilot, tmp_path, entry)

    assert "□" in status_text

    modal = PdfActionsModal(entry, str(tmp_path))
    keys = modal._available
    assert keys == {"fetch", "add", "delete"}


async def test_detail_shows_none_when_no_file_field() -> None:
    entry = BibEntry(key="Fresh2023", entry_type="article")

    assert pdf_link_state(entry.file, entry.key, "") == "none"

    modal = PdfActionsModal(entry, "")
    keys = modal._available
    assert keys == {"fetch", "add"}
