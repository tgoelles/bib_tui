"""Smoke tests for the BibTuiApp.

These tests launch the full Textual app in headless mode against a real .bib
file and verify that the most important UI interactions work end-to-end.
"""

from pathlib import Path

import pytest

from bibtui.app import BibTuiApp
from bibtui.widgets.entry_list import EntryList

MY_COLLECTION = Path(__file__).parent / "bib_examples" / "MyCollection.bib"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _app() -> BibTuiApp:
    return BibTuiApp(str(MY_COLLECTION))


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_app_mounts() -> None:
    """App starts without exceptions and the DataTable is visible."""
    async with _app().run_test() as pilot:
        await pilot.pause()
        # EntryList widget must be present
        entry_list = pilot.app.query_one(EntryList)
        assert entry_list is not None


@pytest.mark.asyncio
async def test_entries_loaded() -> None:
    """Entries from the .bib file are loaded into the list."""
    async with _app().run_test() as pilot:
        await pilot.pause()
        entry_list = pilot.app.query_one(EntryList)
        assert len(entry_list._all_entries) > 0


@pytest.mark.asyncio
async def test_title_contains_filename() -> None:
    """App title shows the bib filename."""
    async with _app().run_test() as pilot:
        await pilot.pause()
        assert "MyCollection" in pilot.app.title


# ---------------------------------------------------------------------------
# Key bindings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_help_modal_opens_and_closes() -> None:
    """action_show_help pushes HelpModal; Escape dismisses it."""
    from bibtui.widgets.modals import HelpModal

    async with _app().run_test() as pilot:
        await pilot.pause()
        # ModalScreens are separate screens — use screen_stack, not query()
        pilot.app.action_show_help()
        await pilot.pause()
        assert any(isinstance(s, HelpModal) for s in pilot.app.screen_stack), (
            "HelpModal should be on screen stack"
        )
        await pilot.press("escape")
        await pilot.pause()
        assert not any(isinstance(s, HelpModal) for s in pilot.app.screen_stack), (
            "HelpModal should be dismissed"
        )


@pytest.mark.asyncio
async def test_search_filters_entries() -> None:
    """Pressing 's' focuses the search box; typing filters the list."""
    async with _app().run_test() as pilot:
        await pilot.pause()
        entry_list = pilot.app.query_one(EntryList)
        total = len(entry_list._filtered)
        assert total > 0

        await pilot.press("s")
        await pilot.pause()
        # Type a query that is unlikely to match anything
        await pilot.press(*"zzzzunlikelymatch")
        await pilot.pause()
        assert len(entry_list._filtered) < total


@pytest.mark.asyncio
async def test_escape_clears_search() -> None:
    """Escape clears an active search and restores full entry list."""
    async with _app().run_test() as pilot:
        await pilot.pause()
        entry_list = pilot.app.query_one(EntryList)
        total = len(entry_list._filtered)

        await pilot.press("s")
        await pilot.pause()
        await pilot.press(*"zzzz")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert len(entry_list._filtered) == total


@pytest.mark.asyncio
async def test_quit_without_changes() -> None:
    """Press 'q' exits cleanly when there are no unsaved changes."""
    async with _app().run_test() as pilot:
        await pilot.pause()
        assert not pilot.app._dirty
        await pilot.press("q")
        # If the app raised during quit, the context manager would propagate it.
        # Reaching here means a clean exit.
