"""Tests for PdfImportPickerModal (the `n` → "Import from PDF" file picker).

Mirrors AddPDFModal's browse/filter model but as a checklist so several
files can be picked at once.
"""

from pathlib import Path

from textual.widgets import Input, SelectionList

from bibtui.app import BibTuiApp
from bibtui.widgets.modals import PdfImportPickerModal

BIB = "tests/bib_examples/MyCollection.bib"


async def _open_modal(app, pilot, download_dir):
    result: dict = {}
    modal = PdfImportPickerModal(download_dir)
    app.push_screen(modal, lambda r: result.__setitem__("paths", r))
    await pilot.pause()
    return modal, result


async def test_scan_lists_pdfs_in_download_dir(tmp_path) -> None:
    (tmp_path / "a.pdf").write_bytes(b"fake")
    (tmp_path / "b.pdf").write_bytes(b"fake")
    (tmp_path / "not_a_pdf.txt").write_text("x")

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot, str(tmp_path))

        sl = modal.query_one(SelectionList)
        assert sl.option_count == 2


async def test_default_focus_is_list_first_item(tmp_path) -> None:
    (tmp_path / "a.pdf").write_bytes(b"fake")
    (tmp_path / "b.pdf").write_bytes(b"fake")

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot, str(tmp_path))

        sl = modal.query_one(SelectionList)
        assert modal.focused is sl
        assert sl.highlighted == 0


async def test_default_focus_falls_back_to_filter_when_list_empty(tmp_path) -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot, str(tmp_path))  # empty dir

        inp = modal.query_one("#pip-filter", Input)
        assert modal.focused is inp


async def test_s_jumps_from_list_to_filter(tmp_path) -> None:
    (tmp_path / "a.pdf").write_bytes(b"fake")

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot, str(tmp_path))

        sl = modal.query_one(SelectionList)
        assert modal.focused is sl  # default focus

        await pilot.press("s")
        await pilot.pause()

        inp = modal.query_one("#pip-filter", Input)
        assert modal.focused is inp


async def test_confirm_with_nothing_selected_shows_error(tmp_path) -> None:
    (tmp_path / "a.pdf").write_bytes(b"fake")

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, result = await _open_modal(app, pilot, str(tmp_path))

        modal._confirm()
        await pilot.pause()

        assert "paths" not in result
        assert isinstance(app.screen, PdfImportPickerModal)


async def test_toggling_and_confirming_dismisses_with_selected_paths(tmp_path) -> None:
    pdf1 = tmp_path / "a.pdf"
    pdf2 = tmp_path / "b.pdf"
    pdf1.write_bytes(b"fake")
    pdf2.write_bytes(b"fake")

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, result = await _open_modal(app, pilot, str(tmp_path))

        sl = modal.query_one(SelectionList)
        sl.focus()
        sl.highlighted = 0
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()

        modal._confirm()
        await pilot.pause()

        assert result["paths"] == [str(modal._filtered[0])]


async def test_enter_also_toggles_selection(tmp_path) -> None:
    (tmp_path / "a.pdf").write_bytes(b"fake")

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, result = await _open_modal(app, pilot, str(tmp_path))

        sl = modal.query_one(SelectionList)
        sl.focus()
        sl.highlighted = 0
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        modal._confirm()
        await pilot.pause()

        assert result["paths"] == [str(modal._filtered[0])]


async def test_space_previews_instead_of_toggling(tmp_path, monkeypatch) -> None:
    (tmp_path / "a.pdf").write_bytes(b"fake")

    previewed: list[str] = []
    monkeypatch.setattr(
        "bibtui.widgets.modals.open_with_default_app",
        lambda path: previewed.append(path),
    )

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot, str(tmp_path))

        sl = modal.query_one(SelectionList)
        sl.focus()
        sl.highlighted = 0
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()

        assert previewed == [str(modal._filtered[0])]
        assert not sl.selected  # Space did not toggle the checkbox


async def test_filter_narrows_list_and_preserves_selection(tmp_path) -> None:
    pdf1 = tmp_path / "alpha.pdf"
    pdf2 = tmp_path / "beta.pdf"
    pdf1.write_bytes(b"fake")
    pdf2.write_bytes(b"fake")

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot, str(tmp_path))

        sl = modal.query_one(SelectionList)
        sl.focus()
        sl.highlighted = 0
        await pilot.press("x")
        await pilot.pause()
        selected_path = str(modal._filtered[0])

        # Filter down to just the other file — the selected one drops out of view.
        inp = modal.query_one("#pip-filter", Input)
        inp.focus()
        inp.value = "beta"
        modal._on_filter(Input.Changed(inp, "beta"))
        await pilot.pause()
        assert modal.query_one(SelectionList).option_count == 1

        # Clear the filter — the earlier selection should still be checked.
        inp.value = ""
        modal._on_filter(Input.Changed(inp, ""))
        await pilot.pause()

        modal._confirm()
        assert selected_path in modal._selected


async def test_submitting_directory_path_switches_listing(tmp_path) -> None:
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "one.pdf").write_bytes(b"fake")
    (dir_b / "two.pdf").write_bytes(b"fake")
    (dir_b / "three.pdf").write_bytes(b"fake")

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot, str(dir_a))

        assert modal.query_one(SelectionList).option_count == 1

        inp = modal.query_one("#pip-filter", Input)
        inp.value = str(dir_b)
        modal._on_filter_submitted(Input.Submitted(inp, str(dir_b)))
        await pilot.pause()

        assert modal._download_dir == str(dir_b)
        assert modal.query_one(SelectionList).option_count == 2
        assert inp.value == ""


async def test_submitting_explicit_file_path_adds_and_selects_it(tmp_path) -> None:
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    other_pdf = elsewhere / "other.pdf"
    other_pdf.write_bytes(b"fake")

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot, str(download_dir))

        inp = modal.query_one("#pip-filter", Input)
        inp.value = str(other_pdf)
        modal._on_filter_submitted(Input.Submitted(inp, str(other_pdf)))
        await pilot.pause()

        assert str(other_pdf) in modal._selected
        assert Path(other_pdf) in modal._all_files
        assert inp.value == ""
