"""Tests for KeywordsModal's keybindings, matching every other checklist in
the app (PdfImportPickerModal): Space previews (here, a no-op — nothing to
preview for a keyword), Enter/`x` toggle instead of Space toggling, which is
plain SelectionList's own default.
"""

from textual.widgets import Input, SelectionList

from bibtui.app import BibTuiApp
from bibtui.bib.models import BibEntry
from bibtui.widgets.modals import KeywordsModal, PreviewSelectionList

BIB = "tests/bib_examples/MyCollection.bib"


def _entry(keywords: str = "") -> BibEntry:
    return BibEntry(key="Smith2023", entry_type="article", keywords=keywords)


async def _open_modal(app, pilot, entry, all_keywords):
    modal = KeywordsModal(entry, all_keywords, {kw: 1 for kw in all_keywords})
    app.push_screen(modal)
    await pilot.pause()
    return modal


async def test_keyword_list_uses_preview_selection_list() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal = await _open_modal(app, pilot, _entry(), ["ice", "climate"])

        assert isinstance(modal.query_one(SelectionList), PreviewSelectionList)


async def test_space_on_list_does_not_toggle() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal = await _open_modal(app, pilot, _entry(), ["ice", "climate"])

        sl = modal.query_one(SelectionList)
        sl.focus()
        sl.highlighted = 0
        await pilot.pause()
        before = set(sl.selected)

        await pilot.press("space")
        await pilot.pause()

        assert set(sl.selected) == before


async def test_x_toggles_highlighted_keyword() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal = await _open_modal(app, pilot, _entry(), ["ice", "climate"])

        sl = modal.query_one(SelectionList)
        sl.focus()
        sl.highlighted = 0
        await pilot.pause()
        assert "ice" not in sl.selected

        await pilot.press("x")
        await pilot.pause()

        assert "ice" in sl.selected


async def test_enter_toggles_highlighted_keyword_when_list_focused() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal = await _open_modal(app, pilot, _entry(), ["ice", "climate"])

        sl = modal.query_one(SelectionList)
        sl.focus()
        sl.highlighted = 0
        await pilot.pause()
        assert "ice" not in sl.selected

        await pilot.press("enter")
        await pilot.pause()

        assert "ice" in sl.selected


async def test_enter_on_filter_still_adds_new_keyword() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal = await _open_modal(app, pilot, _entry(), ["ice"])

        inp = modal.query_one("#kw-filter", Input)
        inp.focus()
        inp.value = "brand-new"
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        assert "brand-new" in modal._selected
