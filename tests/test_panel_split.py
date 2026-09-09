"""Tests for the adjustable list/detail split (`<` / `>` keybindings)."""

from pathlib import Path

from bibtui.app import BibTuiApp
from bibtui.utils.config import load_config

BIB = "tests/bib_examples/MyCollection.bib"


def _isolate_config(tmp_path: Path, monkeypatch, percent: int | None = None) -> None:
    """Point the config module at a throwaway file so tests never touch ~/.config."""
    config_file = tmp_path / "config.toml"
    monkeypatch.setattr("bibtui.utils.config.CONFIG_PATH", config_file)
    lines = ["[updates]", "check_for_updates = false"]
    if percent is not None:
        lines += ["[ui]", f"detail_panel_percent = {percent}"]
    config_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def test_configured_percent_applied_on_startup(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch, percent=40)
    app = BibTuiApp(BIB)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert app.query_one("#entry-detail").outer_size.width == 40
        assert app.query_one("#entry-list").outer_size.width == 60


async def test_greater_than_shrinks_detail_pane(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch)
    app = BibTuiApp(BIB)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert app.query_one("#entry-detail").outer_size.width == 50
        await pilot.press("greater_than_sign")
        await pilot.pause()
        assert app.query_one("#entry-detail").outer_size.width == 45
        assert app.query_one("#entry-list").outer_size.width == 55


async def test_less_than_grows_detail_pane(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch)
    app = BibTuiApp(BIB)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        await pilot.press("less_than_sign")
        await pilot.pause()
        assert app.query_one("#entry-detail").outer_size.width == 55
        assert app.query_one("#entry-list").outer_size.width == 45


async def test_split_is_clamped(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch, percent=25)
    app = BibTuiApp(BIB)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        await pilot.press("greater_than_sign")  # 25 -> 20
        await pilot.press("greater_than_sign")  # stays at 20
        await pilot.pause()
        assert app.query_one("#entry-detail").outer_size.width == 20


async def test_adjusted_split_is_persisted(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch)
    app = BibTuiApp(BIB)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        await pilot.press("greater_than_sign")
        await pilot.pause()
    assert load_config().detail_panel_percent == 45


async def test_maximized_table_fills_width_despite_custom_split(
    tmp_path, monkeypatch
) -> None:
    _isolate_config(tmp_path, monkeypatch)
    app = BibTuiApp(BIB)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        await pilot.press("greater_than_sign")  # list 55% / detail 45%
        await pilot.press("m")
        await pilot.pause()
        entry_list = app.query_one("#entry-list")
        assert app.screen.maximized is entry_list
        assert entry_list.outer_size.width == 100
        await pilot.press("m")
        await pilot.pause()
        assert entry_list.outer_size.width == 55


async def test_vertical_layout_keeps_full_width_panes(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch, percent=30)
    app = BibTuiApp(BIB)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert app.query_one("#entry-detail").outer_size.width == 30
        # Narrow terminal switches #main-content to the vertical layout;
        # both panes must then span the full width despite the custom split.
        await pilot.resize_terminal(40, 40)
        await pilot.pause()
        assert app.query_one("#main-content").has_class("vertical")
        assert app.query_one("#entry-detail").outer_size.width == 40
        assert app.query_one("#entry-list").outer_size.width == 40
