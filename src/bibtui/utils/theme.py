"""Detect the active Omarchy 4 theme and turn it into a Textual theme.

Omarchy 4 keeps the live theme under ``~/.local/state/omarchy/current``:

* ``theme.name``    - the active theme's slug
* ``theme/colors.toml`` - ``mode = "light"|"dark"`` plus a named palette
  (``accent``, ``selection``, ``muted``, ``background`` and its
  ``dark``/``darker``/``lighter`` variants, ``foreground`` variants, and the
  ANSI colors ``red``/``green``/``yellow``/... with ``bright_*`` companions).

Every bundled Omarchy 4 theme ships ``colors.toml``, so the palette is built
straight from it - there is no name-to-builtin mapping.  Omarchy 3
(``~/.config/omarchy``, ``color0..15`` palette, ``light.mode`` marker) is not
supported.
"""

import tomllib
from pathlib import Path

from textual.theme import Theme

_OMARCHY_CURRENT = Path(".local") / "state" / "omarchy" / "current"


def _current_dir() -> Path:
    return Path.home() / _OMARCHY_CURRENT


def _theme_name() -> str | None:
    """Return the active Omarchy theme slug, or None when Omarchy 4 is absent."""
    try:
        return (_current_dir() / "theme.name").read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _read_colors() -> dict | None:
    try:
        with open(_current_dir() / "theme" / "colors.toml", "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return None


def _build_theme(name: str, colors: dict) -> Theme:
    light = str(colors.get("mode", "dark")).strip().lower() == "light"
    bg = colors.get("background", "#eff1f5" if light else "#1e1e2e")
    accent = colors.get("accent", "#1e66f5" if light else "#89b4fa")
    # Chrome surfaces: a light theme layers darker, a dark theme layers lighter.
    surface = colors.get("dark_background" if light else "lighter_background", bg)
    panel = colors.get("selection" if light else "muted", surface)
    selection = colors.get("selection", accent)
    return Theme(
        name=f"omarchy-{name}",
        primary=accent,
        accent=accent,
        background=bg,
        surface=surface,
        panel=panel,
        foreground=colors.get("foreground", "#4c4f69" if light else "#cdd6f4"),
        error=colors.get("red", "#d20f39" if light else "#f38ba8"),
        success=colors.get("green", "#40a02b" if light else "#a6e3a1"),
        warning=colors.get("yellow", "#df8e1d" if light else "#f9e2af"),
        dark=not light,
        variables={"input-selection-background": f"{selection} 35%"},
    )


def get_omarchy_theme() -> Theme | None:
    """Return a Textual ``Theme`` for the active Omarchy 4 theme, or None.

    None means Omarchy 4 is not present (or its ``colors.toml`` is unreadable);
    callers should fall back to their default theme.  A returned theme must be
    registered with ``App.register_theme`` before ``App.theme`` is set to its
    name.
    """
    name = _theme_name()
    if name is None:
        return None
    colors = _read_colors()
    if colors is None:
        return None
    return _build_theme(name, colors)
