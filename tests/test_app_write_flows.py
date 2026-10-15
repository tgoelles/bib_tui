"""End-to-end tests for the app actions that change the library, then write it.

Each test drives the real key bindings headlessly, presses `w`, and compares
the whole file on disk against the exact expected text — so an action that
touches more than it should (another entry, another field, formatting) fails.
"""

from pathlib import Path

from textual.widgets import DataTable

from bibtui.app import BibTuiApp
from bibtui.widgets.entry_list import EntryList
from bibtui.widgets.modals import ConfirmModal, KeywordsModal

SOURCE = """\
% Library comment that must survive every write.

@article{Alpha2020,
  title = {First},
  author = {Doe, J},
  year = {2020},
  keywords = {ice, snow},
}

@article{Beta2021,
  title = {Second},
  author = {Roe, R},
  year = {2021},
  keywords = {snow,glacier},
}

@article{Gamma2022,
  title = {Third},
  author = {Poe, P},
  year = {2022},
  keywords = {firn,ice},
  ranking = {rank4},
}
"""


def _write_bib(tmp_path: Path) -> Path:
    path = tmp_path / "lib.bib"
    path.write_text(SOURCE, encoding="utf-8")
    return path


async def _select(app, pilot, key: str) -> None:
    el = app.query_one(EntryList)
    idx = next(i for i, e in enumerate(el._filtered) if e.key == key)
    app.query_one(DataTable).move_cursor(row=idx)
    app.query_one(DataTable).focus()
    await pilot.pause()


async def _write(app, pilot) -> None:
    await pilot.press("w")
    await pilot.pause()
    assert not app._dirty


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# rating / read state / urgency
# ---------------------------------------------------------------------------


async def test_rating_key_adds_ranking_to_selected_entry_only(tmp_path) -> None:
    path = _write_bib(tmp_path)
    app = BibTuiApp(str(path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await _select(app, pilot, "Beta2021")
        await pilot.press("3")
        assert app._dirty
        await _write(app, pilot)

    assert _read(path) == SOURCE.replace(
        "  keywords = {snow,glacier},\n",
        "  keywords = {snow,glacier},\n  ranking = {rank3},\n",
    )


async def test_rating_zero_removes_ranking(tmp_path) -> None:
    path = _write_bib(tmp_path)
    app = BibTuiApp(str(path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await _select(app, pilot, "Gamma2022")
        await pilot.press("0")
        await _write(app, pilot)

    assert _read(path) == SOURCE.replace("  ranking = {rank4},\n", "")


async def test_read_state_and_urgency_keys_are_written(tmp_path) -> None:
    path = _write_bib(tmp_path)
    app = BibTuiApp(str(path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await _select(app, pilot, "Alpha2020")
        await pilot.press("r")  # "" -> to-read
        await pilot.press("u")  # unset -> high
        await _write(app, pilot)

    assert _read(path) == SOURCE.replace(
        "  keywords = {ice, snow},\n",
        "  keywords = {ice, snow},\n  readstatus = {to-read},\n  priority = {prio1},\n",
    )


async def test_rating_change_and_back_writes_nothing(tmp_path) -> None:
    path = _write_bib(tmp_path)
    app = BibTuiApp(str(path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await _select(app, pilot, "Gamma2022")
        await pilot.press("2")
        await pilot.press("4")
        await _write(app, pilot)

    assert _read(path) == SOURCE


# ---------------------------------------------------------------------------
# keywords
# ---------------------------------------------------------------------------


async def _keywords_modal(app, pilot, key: str) -> KeywordsModal:
    await _select(app, pilot, key)
    await pilot.press("k")
    await pilot.pause()
    modal = app.screen
    assert isinstance(modal, KeywordsModal)
    return modal


async def test_keywords_edit_changes_only_that_entry(tmp_path) -> None:
    path = _write_bib(tmp_path)
    app = BibTuiApp(str(path))
    async with app.run_test() as pilot:
        await pilot.pause()
        modal = await _keywords_modal(app, pilot, "Alpha2020")
        modal.dismiss(("ice, snow, sea ice", set()))
        await pilot.pause()
        await _write(app, pilot)

    assert _read(path) == SOURCE.replace(
        "keywords = {ice, snow}", "keywords = {ice, snow, sea ice}"
    )


async def test_delete_keyword_everywhere_touches_only_entries_with_it(
    tmp_path,
) -> None:
    """Gamma2022 has no "snow" and must stay byte-identical."""
    path = _write_bib(tmp_path)
    app = BibTuiApp(str(path))
    async with app.run_test() as pilot:
        await pilot.pause()
        modal = await _keywords_modal(app, pilot, "Alpha2020")
        modal.dismiss(("ice", {"snow"}))
        await pilot.pause()
        await _write(app, pilot)

    assert _read(path) == SOURCE.replace(
        "keywords = {ice, snow}", "keywords = {ice}"
    ).replace("keywords = {snow,glacier}", "keywords = {glacier}")


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


async def test_delete_entry_removes_only_its_block(tmp_path) -> None:
    path = _write_bib(tmp_path)
    app = BibTuiApp(str(path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await _select(app, pilot, "Beta2021")
        await pilot.press("delete")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmModal)
        app.screen.dismiss(True)
        await pilot.pause()
        assert [e.key for e in app._entries] == ["Alpha2020", "Gamma2022"]
        await _write(app, pilot)

    beta = SOURCE[SOURCE.index("@article{Beta2021") : SOURCE.index("@article{Gamma")]
    assert _read(path) == SOURCE.replace(beta, "")


async def test_delete_entry_cancelled_keeps_everything(tmp_path) -> None:
    path = _write_bib(tmp_path)
    app = BibTuiApp(str(path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await _select(app, pilot, "Beta2021")
        await pilot.press("delete")
        await pilot.pause()
        app.screen.dismiss(False)
        await pilot.pause()
        assert len(app._entries) == 3
        assert not app._dirty


# ---------------------------------------------------------------------------
# write / quit
# ---------------------------------------------------------------------------


async def test_no_changes_write_leaves_file_untouched(tmp_path) -> None:
    path = _write_bib(tmp_path)
    mtime = path.stat().st_mtime_ns
    app = BibTuiApp(str(path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await _write(app, pilot)

    assert _read(path) == SOURCE
    assert path.stat().st_mtime_ns == mtime


async def test_quit_with_unwritten_changes_asks_first(tmp_path) -> None:
    path = _write_bib(tmp_path)
    app = BibTuiApp(str(path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await _select(app, pilot, "Alpha2020")
        await pilot.press("5")
        await pilot.press("q")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmModal)
        app.screen.dismiss(False)
        await pilot.pause()
        assert app.return_code is None  # still running

    assert _read(path) == SOURCE  # nothing written without `w`


async def test_quit_after_write_exits_without_asking(tmp_path) -> None:
    path = _write_bib(tmp_path)
    app = BibTuiApp(str(path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await _select(app, pilot, "Alpha2020")
        await pilot.press("5")
        await _write(app, pilot)
        await pilot.press("q")
        await pilot.pause()
        assert app.return_code == 0
