"""Unit tests for saved filter presets (bibtui.utils.filters)."""

from pathlib import Path

from bibtui.utils.filters import (
    FilterPreset,
    FilterStore,
    load_filters,
    save_filters,
)

# ---------------------------------------------------------------------------
# FilterStore helpers
# ---------------------------------------------------------------------------


def test_find_is_case_insensitive() -> None:
    store = FilterStore(presets=[FilterPreset(name="Project X", query="k:sepp")])
    assert store.find("project x") is not None
    assert store.find("PROJECT X").query == "k:sepp"
    assert store.find("nope") is None


def test_upsert_adds_new_preset() -> None:
    store = FilterStore()
    store.upsert(FilterPreset(name="Project X", query="k:sepp"))
    assert len(store.presets) == 1
    assert store.presets[0].name == "Project X"


def test_upsert_replaces_existing_by_name_case_insensitively() -> None:
    store = FilterStore(presets=[FilterPreset(name="Project X", query="k:sepp")])
    store.upsert(FilterPreset(name="project x", query="k:sepp y:2010-"))
    assert len(store.presets) == 1
    assert store.presets[0].name == "project x"
    assert store.presets[0].query == "k:sepp y:2010-"


def test_remove_deletes_preset() -> None:
    store = FilterStore(presets=[FilterPreset(name="Project X", query="k:sepp")])
    store.remove("Project X")
    assert store.presets == []


def test_remove_clears_active_when_it_matches() -> None:
    store = FilterStore(
        presets=[FilterPreset(name="Project X", query="k:sepp")], active="Project X"
    )
    store.remove("project x")
    assert store.active == ""


def test_remove_leaves_active_untouched_when_different() -> None:
    store = FilterStore(
        presets=[
            FilterPreset(name="Project X", query="k:sepp"),
            FilterPreset(name="To read", query="r:to-read"),
        ],
        active="To read",
    )
    store.remove("Project X")
    assert store.active == "To read"


# ---------------------------------------------------------------------------
# load_filters / save_filters
# ---------------------------------------------------------------------------


def test_save_and_load_roundtrip(tmp_path: Path, monkeypatch) -> None:
    filters_file = tmp_path / "filters.toml"
    monkeypatch.setattr("bibtui.utils.filters.FILTERS_PATH", filters_file)
    store = FilterStore(
        presets=[
            FilterPreset(name="Project X", query="k:sepp y:2010-"),
            FilterPreset(name="To read", query="r:to-read"),
        ],
        active="Project X",
    )
    save_filters(store)
    assert filters_file.exists()

    loaded = load_filters()
    assert loaded.active == "Project X"
    assert len(loaded.presets) == 2
    assert loaded.presets[0] == FilterPreset(name="Project X", query="k:sepp y:2010-")
    assert loaded.presets[1] == FilterPreset(name="To read", query="r:to-read")


def test_load_filters_returns_empty_store_when_missing(tmp_path: Path, monkeypatch) -> None:
    filters_file = tmp_path / "nonexistent.toml"
    monkeypatch.setattr("bibtui.utils.filters.FILTERS_PATH", filters_file)
    store = load_filters()
    assert store.presets == []
    assert store.active == ""


def test_save_filters_creates_parent_dirs(tmp_path: Path, monkeypatch) -> None:
    filters_file = tmp_path / "a" / "b" / "c" / "filters.toml"
    monkeypatch.setattr("bibtui.utils.filters.FILTERS_PATH", filters_file)
    save_filters(FilterStore())
    assert filters_file.exists()


def test_corrupt_file_is_backed_up_and_defaults_returned(tmp_path: Path, monkeypatch) -> None:
    filters_file = tmp_path / "filters.toml"
    filters_file.write_text("not [ valid toml", encoding="utf-8")
    monkeypatch.setattr("bibtui.utils.filters.FILTERS_PATH", filters_file)

    store = load_filters()
    assert store.presets == []
    backup = filters_file.with_suffix(".toml.corrupt")
    assert backup.exists()
    assert not filters_file.exists()


def test_malformed_rows_are_skipped(tmp_path: Path, monkeypatch) -> None:
    filters_file = tmp_path / "filters.toml"
    filters_file.write_text(
        """
active = "Project X"
[[filter]]
name = "Project X"
query = "k:sepp"

[[filter]]
name = ""
query = "y:2010"

[[filter]]
name = "No query"

[[filter]]
query = "no name"
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("bibtui.utils.filters.FILTERS_PATH", filters_file)

    store = load_filters()
    assert len(store.presets) == 1
    assert store.presets[0] == FilterPreset(name="Project X", query="k:sepp")
    assert store.active == "Project X"
