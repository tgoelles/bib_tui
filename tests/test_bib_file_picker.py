"""Tests for ImportBibPickerModal (the `n` → `b` "Import .bib File" picker).

Mirrors AddPDFModal's browse/filter model (single choice, not a checklist)
plus PdfImportPickerModal's directory-repoint convenience — the .bib
counterpart of "choosing a single PDF".
"""

from pathlib import Path

from textual.widgets import Button, Input, ListView, Static

from bibtui.app import BibTuiApp
from bibtui.widgets.modals import ImportBibPickerModal

BIB = "tests/bib_examples/MyCollection.bib"


async def _open_modal(app, pilot, download_dir):
    result: dict = {}
    modal = ImportBibPickerModal(download_dir)
    app.push_screen(modal, lambda r: result.__setitem__("path", r))
    await pilot.pause()
    return modal, result


async def test_scan_lists_bib_files_in_download_dir(tmp_path) -> None:
    (tmp_path / "a.bib").write_text("@article{a}")
    (tmp_path / "b.bib").write_text("@article{b}")
    (tmp_path / "not_a_bib.txt").write_text("x")

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot, str(tmp_path))

        assert len(modal.query_one(ListView).children) == 2


async def test_default_focus_is_list_first_item(tmp_path) -> None:
    (tmp_path / "a.bib").write_text("@article{a}")
    (tmp_path / "b.bib").write_text("@article{b}")

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot, str(tmp_path))

        lv = modal.query_one(ListView)
        assert modal.focused is lv
        assert lv.index == 0


async def test_default_focus_falls_back_to_filter_when_list_empty(tmp_path) -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot, str(tmp_path))  # empty dir

        inp = modal.query_one("#ibp-filter", Input)
        assert modal.focused is inp


async def test_s_jumps_from_list_to_filter(tmp_path) -> None:
    (tmp_path / "a.bib").write_text("@article{a}")

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot, str(tmp_path))

        lv = modal.query_one(ListView)
        assert modal.focused is lv  # default focus

        await pilot.press("s")
        await pilot.pause()

        inp = modal.query_one("#ibp-filter", Input)
        assert modal.focused is inp


async def test_confirm_with_nothing_selected_shows_error(tmp_path) -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, result = await _open_modal(app, pilot, str(tmp_path))

        modal._confirm()
        await pilot.pause()

        assert "path" not in result
        assert isinstance(app.screen, ImportBibPickerModal)
        assert "Select a file" in str(modal.query_one("#ibp-error", Static).render())


async def test_enter_chooses_highlighted_file(tmp_path) -> None:
    (tmp_path / "a.bib").write_text("@article{a}")

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, result = await _open_modal(app, pilot, str(tmp_path))

        lv = modal.query_one(ListView)
        lv.focus()
        lv.index = 0
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        assert result["path"] == str(modal._filtered[0])


async def test_x_also_chooses_highlighted_file(tmp_path) -> None:
    (tmp_path / "a.bib").write_text("@article{a}")

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, result = await _open_modal(app, pilot, str(tmp_path))

        lv = modal.query_one(ListView)
        lv.focus()
        lv.index = 0
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()

        assert result["path"] == str(modal._filtered[0])


async def test_space_previews_instead_of_choosing(tmp_path, monkeypatch) -> None:
    (tmp_path / "a.bib").write_text("@article{a}")

    previewed: list[str] = []
    monkeypatch.setattr(
        "bibtui.widgets.modals.open_with_default_app",
        lambda path: previewed.append(path),
    )

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, result = await _open_modal(app, pilot, str(tmp_path))

        lv = modal.query_one(ListView)
        lv.focus()
        lv.index = 0
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()

        assert previewed == [str(modal._filtered[0])]
        assert "path" not in result  # Space did not dismiss the modal


async def test_submitting_directory_path_switches_listing(tmp_path) -> None:
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "one.bib").write_text("@article{one}")
    (dir_b / "two.bib").write_text("@article{two}")
    (dir_b / "three.bib").write_text("@article{three}")

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, _ = await _open_modal(app, pilot, str(dir_a))

        assert len(modal.query_one(ListView).children) == 1

        inp = modal.query_one("#ibp-filter", Input)
        inp.value = str(dir_b)
        modal._on_filter_submitted(Input.Submitted(inp, str(dir_b)))
        await pilot.pause()

        assert modal._download_dir == str(dir_b)
        assert len(modal.query_one(ListView).children) == 2
        assert inp.value == ""


async def test_submitting_explicit_file_path_chooses_it(tmp_path) -> None:
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    other_bib = elsewhere / "other.bib"
    other_bib.write_text("@article{other}")

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, result = await _open_modal(app, pilot, str(download_dir))

        inp = modal.query_one("#ibp-filter", Input)
        inp.value = str(other_bib)
        modal._on_filter_submitted(Input.Submitted(inp, str(other_bib)))
        await pilot.pause()

        assert result["path"] == str(other_bib)


async def test_choosing_a_non_bib_file_is_rejected(tmp_path) -> None:
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    not_bib = tmp_path / "notes.txt"
    not_bib.write_text("hello")

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, result = await _open_modal(app, pilot, str(download_dir))

        inp = modal.query_one("#ibp-filter", Input)
        inp.value = str(not_bib)
        modal._on_filter_submitted(Input.Submitted(inp, str(not_bib)))
        await pilot.pause()

        assert "path" not in result
        assert "Not a .bib file" in str(modal.query_one("#ibp-error", Static).render())


async def test_choose_button_and_cancel_button(tmp_path) -> None:
    (tmp_path / "a.bib").write_text("@article{a}")

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, result = await _open_modal(app, pilot, str(tmp_path))

        lv = modal.query_one(ListView)
        lv.index = 0
        await pilot.pause()

        modal.query_one("#btn-choose", Button).press()
        await pilot.pause()

        assert result["path"] == str(Path(tmp_path) / "a.bib")


async def test_cancel_button_dismisses_none(tmp_path) -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal, result = await _open_modal(app, pilot, str(tmp_path))

        modal.query_one("#btn-cancel", Button).press()
        await pilot.pause()

        assert result["path"] is None
