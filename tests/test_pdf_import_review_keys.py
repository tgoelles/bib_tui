"""Tests for PdfImportReviewModal's report screen: every scanned file is
listed with a success/failure mark, Space previews the highlighted row's
source PDF, and "Import" commits every matched/link-existing row at once —
no per-file toggle. Scanning itself (the background CrossRef work) is
bypassed by feeding `_on_scan_done` synthetic rows directly, the same way
test_library_fetch.py drives BatchFetchPDFModal's completion callback.
"""

from textual.widgets import OptionList

from bibtui.app import BibTuiApp
from bibtui.bib.models import BibEntry
from bibtui.pdf.import_scan import ImportRow, ImportStatus
from bibtui.widgets.modals import PdfImportReviewModal

BIB = "tests/bib_examples/MyCollection.bib"


async def _open_with_rows(app, pilot, rows, monkeypatch, base_dir="/tmp/pdfs"):
    # The real background scan (`_scan`, a @work(thread=True) method) would
    # race with the synthetic `_on_scan_done` call below — it's a real OS
    # thread that would eventually try to extract/fetch metadata for a fake
    # PDF and overwrite these rows. Stub it out so `on_mount`'s call to it
    # is a no-op, and drive the completion callback directly instead —
    # the same technique test_library_fetch.py uses for BatchFetchPDFModal.
    monkeypatch.setattr(PdfImportReviewModal, "_scan", lambda self: None)

    paths = [row.path for row in rows]
    modal = PdfImportReviewModal(paths, {}, base_dir)
    app.push_screen(modal)
    await pilot.pause()

    modal._on_scan_done(rows)
    await pilot.pause()
    return modal


def _matched_row(path: str, key: str = "Doe2024") -> ImportRow:
    return ImportRow(
        path=path,
        filename="paper.pdf",
        status=ImportStatus.MATCHED,
        entry=BibEntry(key=key, entry_type="article", title="A Paper", doi="10.1/x"),
    )


def _failed_row(path: str) -> ImportRow:
    return ImportRow(
        path=path,
        filename="ambiguous.pdf",
        status=ImportStatus.AMBIGUOUS,
        message="Multiple possible DOIs found in the text.",
        candidates=["10.1/a", "10.2/b"],
    )


async def test_all_rows_are_listed_with_no_selection_state(tmp_path, monkeypatch) -> None:
    pdf1 = tmp_path / "matched.pdf"
    pdf1.write_bytes(b"fake")
    pdf2 = tmp_path / "ambiguous.pdf"
    pdf2.write_bytes(b"fake")
    rows = [_matched_row(str(pdf1)), _failed_row(str(pdf2))]

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal = await _open_with_rows(app, pilot, rows, monkeypatch)

        ol = modal.query_one(OptionList)
        assert ol.option_count == 2  # both success and failure rows shown

        btn = modal.query_one("#btn-import")
        assert btn.disabled is False
        assert "1" in str(btn.label)  # only the matched row counts


async def test_import_button_disabled_when_nothing_matched(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "ambiguous.pdf"
    pdf.write_bytes(b"fake")
    rows = [_failed_row(str(pdf))]

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal = await _open_with_rows(app, pilot, rows, monkeypatch)

        assert modal.query_one("#btn-import").disabled is True


async def test_space_previews_the_highlighted_row_regardless_of_status(
    tmp_path, monkeypatch
) -> None:
    pdf1 = tmp_path / "matched.pdf"
    pdf1.write_bytes(b"fake")
    pdf2 = tmp_path / "ambiguous.pdf"
    pdf2.write_bytes(b"fake")
    rows = [_matched_row(str(pdf1)), _failed_row(str(pdf2))]

    previewed: list[str] = []
    monkeypatch.setattr(
        "bibtui.widgets.modals.open_with_default_app",
        lambda path: previewed.append(path),
    )

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal = await _open_with_rows(app, pilot, rows, monkeypatch)

        ol = modal.query_one(OptionList)
        ol.focus()
        ol.highlighted = 1  # the failed/ambiguous row
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()

        assert previewed == [str(pdf2)]


async def test_confirm_imports_every_matched_row_with_no_selection_step(
    tmp_path, monkeypatch
) -> None:
    pdf1 = tmp_path / "a.pdf"
    pdf1.write_bytes(b"fake")
    pdf2 = tmp_path / "b.pdf"
    pdf2.write_bytes(b"fake")
    pdf3 = tmp_path / "c.pdf"
    pdf3.write_bytes(b"fake")
    rows = [
        _matched_row(str(pdf1), key="One2024"),
        _matched_row(str(pdf2), key="Two2024"),
        _failed_row(str(pdf3)),
    ]

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal = await _open_with_rows(app, pilot, rows, monkeypatch, base_dir="")

        result: dict = {}
        monkeypatch.setattr(modal, "dismiss", lambda r=None: result.__setitem__("r", r))

        modal._confirm()

        assert {e.key for e in result["r"]["new"]} == {"One2024", "Two2024"}
        assert result["r"]["relinked"] == []


async def test_confirm_with_nothing_importable_dismisses_none(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "ambiguous.pdf"
    pdf.write_bytes(b"fake")
    rows = [_failed_row(str(pdf))]

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal = await _open_with_rows(app, pilot, rows, monkeypatch)

        result: dict = {"r": "unset"}
        monkeypatch.setattr(modal, "dismiss", lambda r=None: result.__setitem__("r", r))

        modal._confirm()

        assert result["r"] is None
