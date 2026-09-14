"""Unit tests for Omarchy 4 theme detection."""

from pathlib import Path
from textwrap import dedent

import pytest

from bibtui.utils import theme

# Named-palette colors.toml, as shipped by every bundled Omarchy 4 theme.
_DARK_COLORS = dedent(
    """
    mode = "dark"
    accent = "#7aa2f7"
    selection = "#292e42"
    muted = "#414868"
    background = "#1a1b26"
    dark_background = "#13141c"
    darker_background = "#0e0e14"
    lighter_background = "#24283b"
    foreground = "#a9b1d6"
    red = "#f7768e"
    yellow = "#e0af68"
    green = "#9ece6a"
    blue = "#7aa2f7"
    magenta = "#ad8ee6"
    bright_red = "#ff7a93"
    """
).strip()

_LIGHT_COLORS = dedent(
    """
    mode = "light"
    accent = "#1e66f5"
    selection = "#ccd0da"
    muted = "#acb0be"
    background = "#eff1f5"
    dark_background = "#e3e4e8"
    darker_background = "#d7d8dc"
    lighter_background = "#dce0e8"
    foreground = "#4c4f69"
    red = "#d20f39"
    yellow = "#df8e1d"
    green = "#40a02b"
    blue = "#1e66f5"
    """
).strip()


def _make_omarchy(
    home: Path,
    theme_name: str,
    *,
    colors: str | None = None,
) -> Path:
    """Create a fake Omarchy 4 tree under ``home`` and return its ``current`` dir."""
    current = home / ".local" / "state" / "omarchy" / "current"
    theme_dir = current / "theme"
    theme_dir.mkdir(parents=True)
    (current / "theme.name").write_text(theme_name + "\n", encoding="utf-8")
    if colors is not None:
        (theme_dir / "colors.toml").write_text(colors + "\n", encoding="utf-8")
    return current


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


# ---------------------------------------------------------------------------
# Absent / unreadable Omarchy
# ---------------------------------------------------------------------------


def test_no_omarchy_returns_none(home: Path) -> None:
    assert theme.get_omarchy_theme() is None


def test_omarchy_3_layout_is_ignored(home: Path) -> None:
    # ~/.config/omarchy is the Omarchy 3 location and no longer supported.
    old = home / ".config" / "omarchy" / "current" / "theme"
    old.mkdir(parents=True)
    (old.parent / "theme.name").write_text("tokyo-night\n", encoding="utf-8")
    (old / "colors.toml").write_text(_DARK_COLORS + "\n", encoding="utf-8")
    assert theme.get_omarchy_theme() is None


def test_theme_name_without_colors_toml_returns_none(home: Path) -> None:
    _make_omarchy(home, "bare-theme")
    assert theme.get_omarchy_theme() is None


def test_malformed_colors_toml_returns_none(home: Path) -> None:
    _make_omarchy(home, "broken", colors="mode = \nnot valid [[")
    assert theme.get_omarchy_theme() is None


# ---------------------------------------------------------------------------
# Dark theme
# ---------------------------------------------------------------------------


def test_dark_theme_built_from_palette(home: Path) -> None:
    _make_omarchy(home, "tokyo-night", colors=_DARK_COLORS)
    result = theme.get_omarchy_theme()
    assert result is not None
    assert result.name == "omarchy-tokyo-night"
    assert result.dark is True
    assert result.background == "#1a1b26"
    assert result.primary == "#7aa2f7"
    assert result.accent == "#7aa2f7"
    assert result.foreground == "#a9b1d6"
    assert result.error == "#f7768e"
    assert result.success == "#9ece6a"
    assert result.warning == "#e0af68"
    # dark -> surface layers lighter, panel from muted
    assert result.surface == "#24283b"
    assert result.panel == "#414868"
    assert result.variables["input-selection-background"] == "#292e42 35%"


# ---------------------------------------------------------------------------
# Light theme
# ---------------------------------------------------------------------------


def test_light_theme_uses_mode_key_and_darker_surfaces(home: Path) -> None:
    _make_omarchy(home, "catppuccin-latte", colors=_LIGHT_COLORS)
    result = theme.get_omarchy_theme()
    assert result is not None
    assert result.dark is False  # from mode = "light"
    assert result.background == "#eff1f5"
    # light -> surface layers darker, panel from selection
    assert result.surface == "#e3e4e8"
    assert result.panel == "#ccd0da"


# ---------------------------------------------------------------------------
# Sparse palette -> defaults
# ---------------------------------------------------------------------------


def test_sparse_palette_falls_back_to_defaults(home: Path) -> None:
    _make_omarchy(home, "minimal", colors='mode = "dark"\naccent = "#abcdef"')
    result = theme.get_omarchy_theme()
    assert result is not None
    assert result.accent == "#abcdef"
    assert result.background == "#1e1e2e"  # dark default
    assert result.error == "#f38ba8"
    # surface/panel fall back to background when the *_background keys are absent
    assert result.surface == "#1e1e2e"
    assert result.panel == "#1e1e2e"
