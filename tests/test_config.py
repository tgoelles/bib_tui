"""Unit tests for bib_tui.utils.config."""

from pathlib import Path

import pytest

from bibtui.utils.config import (
    Config,
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
