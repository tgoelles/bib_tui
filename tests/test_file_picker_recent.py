"""The startup file picker opens with the most recently used file selected."""

from pathlib import Path

from textual.widgets import ListView

from bibtui.app import BibTuiApp
from bibtui.widgets.modals import FilePickerModal


def _setup(tmp_path: Path, monkeypatch, recent: list[str]) -> None:
    config_file = tmp_path / "config.toml"
    monkeypatch.setattr("bibtui.utils.config.CONFIG_PATH", config_file)
    listing = ", ".join(f'"{r}"' for r in recent)
    config_file.write_text(
        f"[updates]\ncheck_for_updates = false\n[files]\nrecent = [{listing}]\n",
        encoding="utf-8",
    )


def _bib(tmp_path: Path, name: str) -> str:
    path = tmp_path / name
    path.write_text("@article{K1, title={T}}\n", encoding="utf-8")
    return str(path)


async def test_most_recent_file_is_preselected_and_focused(
    tmp_path, monkeypatch
) -> None:
    latest, older = _bib(tmp_path, "latest.bib"), _bib(tmp_path, "older.bib")
    _setup(tmp_path, monkeypatch, [latest, older])
    app = BibTuiApp(None)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, FilePickerModal)
        recent = app.screen.query_one("#fp-recent-list", ListView)
        assert recent.index == 0
        assert app.screen.focused is recent


async def test_enter_reopens_the_last_used_file(tmp_path, monkeypatch) -> None:
    latest, older = _bib(tmp_path, "latest.bib"), _bib(tmp_path, "older.bib")
    _setup(tmp_path, monkeypatch, [latest, older])
    app = BibTuiApp(None)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app._bib_path == latest


async def test_missing_recent_files_are_skipped_when_preselecting(
    tmp_path, monkeypatch
) -> None:
    older = _bib(tmp_path, "older.bib")
    _setup(tmp_path, monkeypatch, [str(tmp_path / "deleted.bib"), older])
    app = BibTuiApp(None)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app._bib_path == older


async def test_no_recent_files_still_opens_the_picker(tmp_path, monkeypatch) -> None:
    _setup(tmp_path, monkeypatch, [])
    app = BibTuiApp(None)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, FilePickerModal)
        assert not app.screen.query("#fp-recent-list")
