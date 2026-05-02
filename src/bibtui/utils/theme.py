"""Detect the OS / Omarchy theme and map it to a Textual theme name."""

import tomllib
from pathlib import Path

from textual.theme import Theme

# Omarchy theme name → Textual built-in theme name.
# Only exact or canonical aliases are listed here; everything else falls
# through to the colors.toml path so the actual palette is used.
_THEME_MAP: dict[str, str] = {
    "catppuccin": "catppuccin-mocha",  # catppuccin without suffix == mocha
    "catppuccin-frappe": "catppuccin-frappe",
    "catppuccin-latte": "catppuccin-latte",
    "catppuccin-macchiato": "catppuccin-macchiato",
    "catppuccin-mocha": "catppuccin-mocha",
    "dracula": "dracula",
    "flexoki": "flexoki",
    "gruvbox": "gruvbox",
    "monokai": "monokai",
    "nord": "nord",
    "rose-pine": "rose-pine",
    "rose-pine-dawn": "rose-pine-dawn",
    "rose-pine-moon": "rose-pine-moon",
    "tokyo-night": "tokyo-night",
}

_OMARCHY_THEME_NAME = Path.home() / ".config" / "omarchy" / "current" / "theme.name"
_OMARCHY_THEME_DIR = Path.home() / ".config" / "omarchy" / "current" / "theme"
_OMARCHY_COLORS_TOML = _OMARCHY_THEME_DIR / "colors.toml"


def _omarchy_theme_name() -> str | None:
    """Return the active Omarchy theme name by reading theme.name, or None."""
    try:
        return _OMARCHY_THEME_NAME.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _omarchy_is_light() -> bool:
    """True if the current Omarchy theme ships a light.mode marker file."""
    return (_OMARCHY_THEME_DIR / "light.mode").exists()


def _read_colors() -> dict | None:
    try:
        with open(_OMARCHY_COLORS_TOML, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return None


def _is_dark(hex_color: str) -> bool:
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255 < 0.5


def _build_theme(omarchy_name: str, colors: dict) -> Theme:
    bg = colors.get("background", "#1e1e2e")
    accent = colors.get("accent", colors.get("color4", "#89b4fa"))
    return Theme(
        name=f"omarchy-{omarchy_name}",
        primary=accent,
        accent=accent,
        background=bg,
        foreground=colors.get("foreground", "#cdd6f4"),
        error=colors.get("color1", "#f38ba8"),
        success=colors.get("color2", "#a6e3a1"),
        warning=colors.get("color3", "#f9e2af"),
        dark=_is_dark(bg),
        variables={},
    )


def get_omarchy_theme() -> tuple[str, Theme | None]:
    """Return (textual_theme_name, custom_Theme_or_None) for the active Omarchy theme.

    The second element is non-None only when no built-in Textual theme covers
    the active Omarchy theme and colors.toml is readable.  Callers must register
    it with the app before setting self.theme.
    """
    name = _omarchy_theme_name()
    if name is None:
        return "textual-dark", None
    if name in _THEME_MAP:
        return _THEME_MAP[name], None
    colors = _read_colors()
    if colors:
        theme = _build_theme(name, colors)
        return theme.name, theme
    # No colors.toml — fall back to light/dark.
    return ("textual-light" if _omarchy_is_light() else "textual-dark"), None
