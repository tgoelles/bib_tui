"""Tests for PdfActionsModal (the `p` PDF actions chooser) — modeled on and
tested the same way as test_new_entry_chooser.py's NewEntryChooserModal
tests, with one difference: unlike the New Entry chooser (every option
always valid), PdfActionsModal always lists all six rows in the same fixed
order and grays out the ones not valid for the entry's current PDF-link
state — matching how the old button panel always showed all six buttons and
just disabled the inapplicable ones. Selecting a grayed-out row (by letter
or by Enter/ListView.Selected) is a silent no-op.
"""

import pytest
from textual.widgets import Button, ListView

from bibtui.app import BibTuiApp
from bibtui.bib.models import BibEntry
from bibtui.widgets.modals import PdfActionsModal

BIB = "tests/bib_examples/MyCollection.bib"

_ALL_KEYS = ["open", "fetch", "add", "copy_file", "copy_path", "delete"]


def _entry(file: str = "") -> BibEntry:
    return BibEntry(key="Smith2023", entry_type="article", file=file)


# ---------------------------------------------------------------------------
# Row set is always all six, in the same order; availability varies by state
# ---------------------------------------------------------------------------


def test_all_six_rows_always_listed_regardless_of_state() -> None:
    for modal in (
        PdfActionsModal(_entry(), ""),
        PdfActionsModal(_entry(":Smith2023.pdf:PDF"), "/does/not/exist"),
    ):
        assert [opt[0] for opt in modal._ALL_ACTIONS] == _ALL_KEYS


def test_no_file_only_fetch_and_add_available() -> None:
    modal = PdfActionsModal(_entry(), "")
    assert modal._available == {"fetch", "add"}


def test_missing_file_fetch_add_delete_available(tmp_path) -> None:
    modal = PdfActionsModal(_entry(":Smith2023.pdf:PDF"), str(tmp_path))
    assert modal._available == {"fetch", "add", "delete"}


def test_found_file_open_copy_copy_delete_available(tmp_path) -> None:
    (tmp_path / "Smith2023.pdf").write_bytes(b"%PDF-1.4")
    modal = PdfActionsModal(_entry(":Smith2023.pdf:PDF"), str(tmp_path))
    assert modal._available == {"open", "copy_file", "copy_path", "delete"}


async def test_list_always_has_six_items_even_when_most_are_unavailable() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal = PdfActionsModal(_entry(), "")  # only fetch/add available
        app.push_screen(modal)
        await pilot.pause()

        lv = modal.query_one(ListView)
        assert len(lv.children) == 6


# ---------------------------------------------------------------------------
# In-modal keybindings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key, expected", [("f", "fetch"), ("a", "add")])
async def test_letter_dismisses_with_expected_choice_when_available(key, expected) -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        result: dict = {}
        app.push_screen(
            PdfActionsModal(_entry(), ""), lambda r: result.__setitem__("v", r)
        )
        await pilot.pause()

        await pilot.press(key)
        await pilot.pause()

        assert result["v"] == expected


async def test_letter_for_unavailable_action_is_a_noop() -> None:
    """`o` (Open) isn't available when there's no PDF — pressing it must not
    dismiss the modal, matching how a disabled button today does nothing."""
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        result: dict = {"v": "unset"}
        app.push_screen(
            PdfActionsModal(_entry(), ""), lambda r: result.__setitem__("v", r)
        )
        await pilot.pause()

        await pilot.press("o")
        await pilot.pause()

        assert result["v"] == "unset"
        assert isinstance(app.screen, PdfActionsModal)


async def test_enter_on_unavailable_row_is_a_noop() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        result: dict = {"v": "unset"}
        modal = PdfActionsModal(_entry(), "")  # open (index 0) unavailable
        app.push_screen(modal, lambda r: result.__setitem__("v", r))
        await pilot.pause()

        lv = modal.query_one(ListView)
        lv.index = 0  # "open" — grayed out, not in modal._available
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        assert result["v"] == "unset"
        assert isinstance(app.screen, PdfActionsModal)


async def test_escape_cancels() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        result: dict = {"v": "unset"}
        app.push_screen(
            PdfActionsModal(_entry(), ""), lambda r: result.__setitem__("v", r)
        )
        await pilot.pause()

        await pilot.press("escape")
        await pilot.pause()

        assert result["v"] is None


async def test_cancel_button_dismisses_none() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        result: dict = {"v": "unset"}
        modal = PdfActionsModal(_entry(), "")
        app.push_screen(modal, lambda r: result.__setitem__("v", r))
        await pilot.pause()

        modal.query_one("#btn-cancel", Button).press()
        await pilot.pause()

        assert result["v"] is None


async def test_list_selected_dismisses_with_highlighted_available_row() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        result: dict = {}
        modal = PdfActionsModal(_entry(), "")
        app.push_screen(modal, lambda r: result.__setitem__("v", r))
        await pilot.pause()

        lv = modal.query_one(ListView)
        lv.index = 2  # "add" — the fixed row order is open/fetch/add/...
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        assert result["v"] == "add"
