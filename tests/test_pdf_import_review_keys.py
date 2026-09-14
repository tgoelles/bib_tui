"""Keybinding tests for PdfImportReviewModal's checklist: Space previews the
highlighted row, Enter/x toggle it — same convention as PdfImportPickerModal
and AddPDFModal. Scanning itself (the background CrossRef work) is bypassed
by feeding `_on_scan_done` a synthetic row directly, the same way
test_library_fetch.py drives BatchFetchPDFModal's completion callback.
"""

from textual.widgets import SelectionList

from bibtui.app import BibTuiApp
from bibtui.bib.models import BibEntry
from bibtui.pdf.import_scan import ImportRow, ImportStatus
from bibtui.widgets.modals import PdfImportReviewModal

BIB = "tests/bib_examples/MyCollection.bib"


async def _open_with_one_matched_row(app, pilot, path, monkeypatch):
    # The real background scan (`_scan`, a @work(thread=True) method) would
    # race with the synthetic `_on_scan_done` call below — it's a real OS
    # thread that would eventually try to extract/fetch metadata for a fake
    # PDF and overwrite these rows. Stub it out so `on_mount`'s call to it
    # is a no-op, and drive the completion callback directly instead —
    # the same technique test_library_fetch.py uses for BatchFetchPDFModal.
    monkeypatch.setattr(PdfImportReviewModal, "_scan", lambda self: None)

    modal = PdfImportReviewModal([path], {}, "/tmp/pdfs")
    app.push_screen(modal)
    await pilot.pause()

    row = ImportRow(
        path=path,
        filename="paper.pdf",
        status=ImportStatus.MATCHED,
        entry=BibEntry(key="Doe2024", entry_type="article", title="A Paper", doi="10.1/x"),
    )
    modal._on_scan_done([row])
    await pilot.pause()
    return modal


async def test_space_previews_instead_of_toggling(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"fake")

    previewed: list[str] = []
    monkeypatch.setattr(
        "bibtui.widgets.modals.open_with_default_app",
        lambda path: previewed.append(path),
    )

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal = await _open_with_one_matched_row(app, pilot, str(pdf), monkeypatch)

        sl = modal.query_one(SelectionList)
        sl.focus()
        sl.highlighted = 0
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()

        assert previewed == [str(pdf)]
        assert list(sl.selected) == [0]  # row started pre-checked; Space must not uncheck it


async def test_x_toggles_the_highlighted_row(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"fake")

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal = await _open_with_one_matched_row(app, pilot, str(pdf), monkeypatch)

        sl = modal.query_one(SelectionList)
        sl.focus()
        sl.highlighted = 0
        await pilot.pause()

        assert list(sl.selected) == [0]  # pre-checked on scan completion
        await pilot.press("x")
        await pilot.pause()
        assert list(sl.selected) == []  # toggled off


async def test_enter_also_toggles_the_highlighted_row(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"fake")

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal = await _open_with_one_matched_row(app, pilot, str(pdf), monkeypatch)

        sl = modal.query_one(SelectionList)
        sl.focus()
        sl.highlighted = 0
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()
        assert list(sl.selected) == []  # toggled off
