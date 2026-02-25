"""Unit tests for bib_tui.utils.config."""

from pathlib import Path

import pytest

from bibtui.utils.config import (
    Config,
    find_pdf_for_entry,
    format_jabref_path,
    load_config,
    parse_jabref_path,
    save_config,
)

# ---------------------------------------------------------------------------
# parse_jabref_path
# ---------------------------------------------------------------------------


def test_parse_jabref_colon_format_with_base() -> None:
    result = parse_jabref_path(":Smith2023.pdf:PDF", base_dir="/papers")
    assert result == "/papers/Smith2023.pdf"


def test_parse_jabref_colon_format_no_base() -> None:
    result = parse_jabref_path(":Smith2023.pdf:PDF")
    assert result == "Smith2023.pdf"


def test_parse_jabref_plain_path() -> None:
    result = parse_jabref_path("Smith2023.pdf", base_dir="/papers")
    assert result == "/papers/Smith2023.pdf"


def test_parse_jabref_absolute_path_unchanged() -> None:
    result = parse_jabref_path("/absolute/path/paper.pdf", base_dir="/papers")
    assert result == "/absolute/path/paper.pdf"


def test_parse_jabref_desc_colon_path_colon_type() -> None:
    result = parse_jabref_path("My Paper:Smith2023.pdf:PDF", base_dir="/papers")
    assert result == "/papers/Smith2023.pdf"


# ---------------------------------------------------------------------------
# format_jabref_path
# ---------------------------------------------------------------------------


def test_format_jabref_relative_when_inside_base() -> None:
    result = format_jabref_path("/papers/Smith2023.pdf", base_dir="/papers")
    assert result == ":Smith2023.pdf:PDF"


def test_format_jabref_keeps_absolute_when_outside_base() -> None:
    result = format_jabref_path("/elsewhere/Smith2023.pdf", base_dir="/papers")
    # Outside base_dir — falls back to basename
    assert "Smith2023.pdf" in result
    assert result.endswith(":PDF")


def test_format_jabref_no_base() -> None:
    # Without a base_dir, format_jabref_path stores whatever path it's given
    # (basename extraction only triggers when there's no path separator)
    result = format_jabref_path("paper.pdf")
    assert result == ":paper.pdf:PDF"


# ---------------------------------------------------------------------------
# save_config / load_config round-trip
# ---------------------------------------------------------------------------


def test_save_and_load_roundtrip(tmp_path: Path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    monkeypatch.setattr("bibtui.utils.config.CONFIG_PATH", config_file)
    cfg = Config(
        pdf_base_dir="/papers",
        unpaywall_email="user@example.com",
        pdf_download_dir="/home/user/Downloads",
    )
    save_config(cfg)
    assert config_file.exists()

    loaded = load_config()
    assert loaded.pdf_base_dir == "/papers"
    assert loaded.unpaywall_email == "user@example.com"
    assert loaded.pdf_download_dir == "/home/user/Downloads"


def test_load_config_returns_defaults_when_missing(tmp_path: Path, monkeypatch) -> None:
    config_file = tmp_path / "nonexistent.toml"
    monkeypatch.setattr("bibtui.utils.config.CONFIG_PATH", config_file)
    monkeypatch.setattr("bibtui.utils.config._git_email", lambda: "")
    cfg = load_config()
    home = Path.home()
    assert cfg.pdf_base_dir == str(home / "Documents" / "papers")
    assert cfg.unpaywall_email == ""
    assert cfg.pdf_download_dir == str(home / "Downloads")


def test_save_config_creates_parent_dirs(tmp_path: Path, monkeypatch) -> None:
    config_file = tmp_path / "a" / "b" / "c" / "config.toml"
    monkeypatch.setattr("bibtui.utils.config.CONFIG_PATH", config_file)
    save_config(Config())
    assert config_file.exists()


# ---------------------------------------------------------------------------
# find_pdf_for_entry — regression tests for filename-mismatch bug
# ---------------------------------------------------------------------------


def test_find_pdf_exact_stored_path(tmp_path: Path) -> None:
    """Returns the stored path when it exists on disk."""
    pdf = tmp_path / "Smith2023 - Ice.pdf"
    pdf.write_bytes(b"%PDF")
    result = find_pdf_for_entry(f":{pdf.name}:PDF", "Smith2023", str(tmp_path))
    assert result == str(pdf)


def test_find_pdf_fallback_glob_when_stored_name_differs(tmp_path: Path) -> None:
    """Falls back to key glob when the stored filename doesn't match the file on disk.

    Regression for: JabRef-style names stored in .bib not matching bibtui-generated
    filenames (e.g. Volery2025 stored as 'The Sub Seasonal...' but file on disk is
    'The sub-seasonal...').
    """
    # File on disk uses bibtui naming convention
    actual = tmp_path / "Volery2025 - The sub-seasonal variability.pdf"
    actual.write_bytes(b"%PDF")

    # .bib entry points to a JabRef-style name that doesn't exist
    jabref_name = "Volery2025 - The Sub Seasonal Variability of Abramov Glacier.pdf"
    result = find_pdf_for_entry(f":{jabref_name}:PDF", "Volery2025", str(tmp_path))
    assert result == str(actual)


def test_find_pdf_returns_none_when_nothing_found(tmp_path: Path) -> None:
    """Returns None when neither the stored path nor a key glob finds anything."""
    result = find_pdf_for_entry(":Missing2099.pdf:PDF", "Missing2099", str(tmp_path))
    assert result is None


def test_find_pdf_no_file_field_no_match(tmp_path: Path) -> None:
    """Returns None when file_field is empty (no PDF linked)."""
    result = find_pdf_for_entry("", "Smith2023", str(tmp_path))
    assert result is None


def test_find_pdf_glob_does_not_match_wrong_key(tmp_path: Path) -> None:
    """Glob fallback is scoped to the entry key — doesn't pick up other entries' PDFs."""
    (tmp_path / "Jones2020 - Some Paper.pdf").write_bytes(b"%PDF")
    result = find_pdf_for_entry(":Smith2023.pdf:PDF", "Smith2023", str(tmp_path))
    assert result is None
