"""Sort order is persisted in config.toml and restored on the next start."""

from pathlib import Path

from textual.widgets import DataTable

from bibtui.app import BibTuiApp
from bibtui.utils.config import Config, load_config, save_config
from bibtui.widgets.entry_list import EntryList

_BIB = """\
@article{Mid2020,
  author = {Mid, A.},
  title = {Middle},
  year = {2020},
  date-added = {2024-06-01T10:00:00},
}

@article{Old2021,
  author = {Old, B.},
  title = {Oldest},
  year = {2021},
  date-added = {2023-01-01T10:00:00},
}

@article{New2019,
  author = {New, C.},
  title = {Newest},
  year = {2019},
  date-added = {2025-03-01T10:00:00},
}
"""


def _setup(tmp_path: Path, monkeypatch, ui: str = "") -> Path:
    """Isolate config.toml and write a small bib; returns the bib path."""
    config_file = tmp_path / "config.toml"
    monkeypatch.setattr("bibtui.utils.config.CONFIG_PATH", config_file)
    config_file.write_text(
        "[updates]\ncheck_for_updates = false\n" + ui, encoding="utf-8"
    )
    bib = tmp_path / "lib.bib"
    bib.write_text(_BIB, encoding="utf-8")
    return bib


def _keys(app: BibTuiApp) -> list[str]:
    return [e.key for e in app.query_one(EntryList).filtered_entries]


# ── Config round-trip ────────────────────────────────────────────────────


def test_config_defaults_to_added_newest_first() -> None:
    cfg = Config()
    assert cfg.sort_column == "added"
    assert cfg.sort_reverse is True


def test_config_sort_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("bibtui.utils.config.CONFIG_PATH", tmp_path / "config.toml")
    save_config(Config(sort_column="year", sort_reverse=False))
    loaded = load_config()
    assert loaded.sort_column == "year"
    assert loaded.sort_reverse is False


def test_config_without_sort_keys_gets_defaults(tmp_path: Path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    monkeypatch.setattr("bibtui.utils.config.CONFIG_PATH", config_file)
    config_file.write_text("[ui]\ntheme = 'nord'\n", encoding="utf-8")
    loaded = load_config()
    assert loaded.sort_column == "added"
    assert loaded.sort_reverse is True


def test_config_ignores_wrongly_typed_sort_values(tmp_path: Path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    monkeypatch.setattr("bibtui.utils.config.CONFIG_PATH", config_file)
    config_file.write_text(
        "[ui]\nsort_column = 3\nsort_reverse = 'yes'\n", encoding="utf-8"
    )
    loaded = load_config()
    assert loaded.sort_column == "added"
    assert loaded.sort_reverse is True


# ── App behaviour ────────────────────────────────────────────────────────


async def test_default_sort_is_added_newest_first(tmp_path, monkeypatch) -> None:
    bib = _setup(tmp_path, monkeypatch)
    app = BibTuiApp(str(bib))
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        assert _keys(app) == ["New2019", "Mid2020", "Old2021"]
        labels = [str(c.label) for c in app.query_one(DataTable).columns.values()]
        assert "Added ▼" in labels


async def test_saved_sort_is_restored_on_startup(tmp_path, monkeypatch) -> None:
    bib = _setup(
        tmp_path, monkeypatch, '[ui]\nsort_column = "year"\nsort_reverse = false\n'
    )
    app = BibTuiApp(str(bib))
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        assert _keys(app) == ["New2019", "Mid2020", "Old2021"]  # year ascending
        labels = [str(c.label) for c in app.query_one(DataTable).columns.values()]
        assert "Year ▲" in labels


async def test_empty_sort_column_keeps_file_order(tmp_path, monkeypatch) -> None:
    bib = _setup(tmp_path, monkeypatch, '[ui]\nsort_column = ""\n')
    app = BibTuiApp(str(bib))
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        assert _keys(app) == ["Mid2020", "Old2021", "New2019"]


async def test_header_click_persists_sort(tmp_path, monkeypatch) -> None:
    bib = _setup(tmp_path, monkeypatch)
    app = BibTuiApp(str(bib))
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        entry_list = app.query_one(EntryList)
        year_key = entry_list._col_keys_by_key["year"]
        table = app.query_one(DataTable)

        table.post_message(DataTable.HeaderSelected(table, year_key, 0, label=None))
        await pilot.pause()
        assert _keys(app) == ["New2019", "Mid2020", "Old2021"]
        saved = load_config()
        assert (saved.sort_column, saved.sort_reverse) == ("year", False)

        # Clicking the same header again reverses and persists that too.
        table.post_message(DataTable.HeaderSelected(table, year_key, 0, label=None))
        await pilot.pause()
        assert _keys(app) == ["Old2021", "Mid2020", "New2019"]
        saved = load_config()
        assert (saved.sort_column, saved.sort_reverse) == ("year", True)


async def test_sort_survives_hiding_its_column(tmp_path, monkeypatch) -> None:
    bib = _setup(tmp_path, monkeypatch)
    app = BibTuiApp(str(bib))
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        entry_list = app.query_one(EntryList)
        entry_list.set_columns(["title", "year"])  # no "added" column
        await pilot.pause()
        assert _keys(app) == ["New2019", "Mid2020", "Old2021"]  # still newest first
