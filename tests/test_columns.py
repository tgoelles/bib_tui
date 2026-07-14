"""Unit tests for the table column registry (pure functions, no running app)."""

from typing import Any

from bibtui.bib.models import BibEntry
from bibtui.widgets.columns import (
    BUILTIN_COLUMNS,
    DEFAULT_TABLE_COLUMNS,
    available_columns,
    discover_field_names,
    field_column_spec,
    resolve_columns,
)


def _entry(**kwargs: Any) -> BibEntry:
    params: dict[str, Any] = {"key": "Smith2020", "entry_type": "article"}
    params.update(kwargs)
    return BibEntry(**params)


def test_default_columns_all_resolve_to_builtins() -> None:
    specs = resolve_columns(DEFAULT_TABLE_COLUMNS)
    assert [s.key for s in specs] == DEFAULT_TABLE_COLUMNS
    assert all(s.key in BUILTIN_COLUMNS for s in specs)


def test_resolve_empty_falls_back_to_default() -> None:
    assert [s.key for s in resolve_columns([])] == DEFAULT_TABLE_COLUMNS
    assert [s.key for s in resolve_columns(None)] == DEFAULT_TABLE_COLUMNS


def test_resolve_unknown_key_becomes_field_column() -> None:
    specs = resolve_columns(["title", "volume"])
    assert [s.key for s in specs] == ["title", "volume"]
    # "volume" isn't a built-in, so it's a generic field column.
    assert "volume" not in BUILTIN_COLUMNS


def test_discover_field_names_excludes_builtins_and_metadata() -> None:
    entries = [
        _entry(
            title="A",
            author="X",
            year="2020",
            journal="Nature",
            url="http://x",
            doi="10.1/x",
            keywords="ice",
            raw_fields={
                "volume": "3",
                "publisher": "ACME",
                "date-added": "2020-01-01",
                "readstatus": "read",
            },
        ),
    ]
    names = discover_field_names(entries)
    # Discovered content/raw fields not already covered by a built-in column…
    assert "doi" in names
    assert "keywords" in names
    assert "volume" in names
    assert "publisher" in names
    # …but never fields that a built-in already represents…
    for covered in ("title", "author", "year", "journal", "url", "file"):
        assert covered not in names
    # …nor app-metadata surfaced through icon columns.
    for meta in ("date-added", "readstatus", "ranking", "priority"):
        assert meta not in names
    # Sorted for stable ordering in the panel.
    assert names == sorted(names)


def test_available_columns_is_builtins_then_fields() -> None:
    entries = [_entry(raw_fields={"volume": "3"})]
    specs = available_columns(entries)
    keys = [s.key for s in specs]
    n_builtin = len(BUILTIN_COLUMNS)
    # All built-ins come first (incl. the optional cite-key column)…
    assert set(keys[:n_builtin]) == set(BUILTIN_COLUMNS)
    assert "citekey" in keys[:n_builtin]
    # …every default column is offered…
    assert all(k in keys for k in DEFAULT_TABLE_COLUMNS)
    # …then the discovered field columns.
    assert "volume" in keys[n_builtin:]


def test_citekey_available_but_not_default() -> None:
    # The cite-key column is a built-in offered in the panel…
    assert "citekey" in BUILTIN_COLUMNS
    # …but off by default so existing layouts are unchanged.
    assert "citekey" not in DEFAULT_TABLE_COLUMNS
    spec = BUILTIN_COLUMNS["citekey"]
    assert spec.render(_entry(key="Volery2025"), "") == "Volery2025"
    assert spec.sort_key(_entry(key="ABC")) == "abc"


def test_field_column_render_truncates_and_sorts() -> None:
    spec = field_column_spec("publisher")
    long = _entry(raw_fields={"publisher": "A Very Long Publisher Name Indeed"})
    rendered = spec.render(long, "")
    assert rendered.endswith("…")
    assert len(rendered) <= spec.width
    # Sort key is the lowercased field value.
    assert spec.sort_key(_entry(raw_fields={"publisher": "Zed"})) == "zed"


def test_builtin_names_are_readable() -> None:
    # Symbol/emoji headers get a readable name for the config panel.
    assert BUILTIN_COLUMNS["url"].name == "URL"
    assert BUILTIN_COLUMNS["state"].name == "Read state"
    assert BUILTIN_COLUMNS["file"].name == "PDF"
    assert BUILTIN_COLUMNS["rating"].name == "Rating"


def test_builtin_dynamic_flags() -> None:
    # Icon columns update in place; text columns do not.
    assert BUILTIN_COLUMNS["state"].dynamic is True
    assert BUILTIN_COLUMNS["rating"].dynamic is True
    assert BUILTIN_COLUMNS["title"].dynamic is False
    # Only Title flexes to fill width.
    assert BUILTIN_COLUMNS["title"].flex is True
    assert BUILTIN_COLUMNS["author"].flex is False


def test_file_column_render_uses_base_dir(tmp_path) -> None:
    pdf = tmp_path / "Smith2020.pdf"
    pdf.write_bytes(b"%PDF")
    spec = BUILTIN_COLUMNS["file"]
    linked = _entry(file=f":{pdf.name}:PDF")
    assert spec.render(linked, str(tmp_path)) == "■"  # found on disk
    # Linked but absent: a key that can't glob-match any file on disk.
    missing = _entry(key="Missing2099", file=":nope.pdf:PDF")
    assert spec.render(missing, str(tmp_path)) == "□"  # linked but absent
    assert spec.render(_entry(file=""), str(tmp_path)) == " "  # no link
