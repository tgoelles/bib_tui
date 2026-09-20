"""ColumnConfigModal: a checklist toggled with Enter/x, like the keyword picker."""

from pathlib import Path

from textual.widgets import SelectionList

from bibtui.app import BibTuiApp
from bibtui.widgets.columns import DEFAULT_TABLE_COLUMNS, available_columns
from bibtui.widgets.modals import ColumnConfigModal


async def _open(app: BibTuiApp, pilot, active: list[str]) -> list:
    """Push the modal onto *app*; the returned list receives its dismiss result."""
    results: list = []
    app.push_screen(ColumnConfigModal(available_columns([]), active), results.append)
    await pilot.pause()
    assert isinstance(app.screen, ColumnConfigModal)
    return results


def _app(tmp_path: Path, monkeypatch) -> BibTuiApp:
    config_file = tmp_path / "config.toml"
    monkeypatch.setattr("bibtui.utils.config.CONFIG_PATH", config_file)
    config_file.write_text("[updates]\ncheck_for_updates = false\n", encoding="utf-8")
    return BibTuiApp("tests/bib_examples/MyCollection.bib")


def _checked(app: BibTuiApp) -> list[str]:
    return list(app.screen.query_one("#col-list", SelectionList).selected)


async def test_uses_checkbox_list_with_defaults_checked(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await _open(app, pilot, list(DEFAULT_TABLE_COLUMNS))
        assert sorted(_checked(app)) == sorted(DEFAULT_TABLE_COLUMNS)


async def test_x_and_enter_toggle_the_highlighted_column(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await _open(app, pilot, list(DEFAULT_TABLE_COLUMNS))
        await pilot.press("x")  # row 0 = state
        assert "state" not in _checked(app)
        await pilot.press("x")
        assert "state" in _checked(app)
        await pilot.press("enter")
        assert "state" not in _checked(app)


async def test_space_does_not_toggle(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await _open(app, pilot, list(DEFAULT_TABLE_COLUMNS))
        await pilot.press("space")
        assert "state" in _checked(app)


async def test_move_keeps_toggled_state_and_save_returns_order(
    tmp_path, monkeypatch
) -> None:
    app = _app(tmp_path, monkeypatch)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        results = await _open(app, pilot, list(DEFAULT_TABLE_COLUMNS))
        await pilot.press("x")  # hide "state" (row 0)
        await pilot.press("shift+down")  # state now sits below "priority"
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert results == [DEFAULT_TABLE_COLUMNS[1:]]


async def test_moving_a_column_reorders_the_result(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        results = await _open(app, pilot, list(DEFAULT_TABLE_COLUMNS))
        await pilot.press("shift+down")  # state <-> priority
        await pilot.press("ctrl+s")
        await pilot.pause()
        expected = list(DEFAULT_TABLE_COLUMNS)
        expected[0], expected[1] = expected[1], expected[0]
        assert results == [expected]


async def test_reset_restores_defaults(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        results = await _open(app, pilot, ["title", "year"])
        await pilot.click("#btn-reset")
        await pilot.pause()
        await pilot.click("#btn-save")
        await pilot.pause()
        assert results == [DEFAULT_TABLE_COLUMNS]


async def test_saving_with_nothing_checked_is_refused(tmp_path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        results = await _open(app, pilot, ["title"])
        await pilot.press("x")  # row 0 is the only checked column: uncheck it
        assert _checked(app) == []
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert results == []
        assert isinstance(app.screen, ColumnConfigModal)
