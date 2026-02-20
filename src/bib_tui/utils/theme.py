"""Detect the OS / Omarchy theme and map it to a Textual theme name."""

import os
from pathlib import Path

# Omarchy theme name  →  Textual built-in theme name
_THEME_MAP: dict[str, str] = {
    "catppuccin": "catppuccin-mocha",
    "catppuccin-latte": "catppuccin-latte",
    "ethereal": "textual-dark",
    "everforest": "gruvbox",
    "flexoki-light": "flexoki",
    "gruvbox": "gruvbox",
    "hackerman": "monokai",
    "kanagawa": "tokyo-night",
    "matte-black": "textual-dark",
    "nord": "nord",
    "osaka-jade": "tokyo-night",
    "ristretto": "rose-pine",
    "rose-pine": "rose-pine",
    "tokyo-night": "tokyo-night",
}

_OMARCHY_THEME_LINK = Path.home() / ".config" / "omarchy" / "current" / "theme"


def _omarchy_theme_name() -> str | None:
    """Return the active Omarchy theme name by reading the symlink, or None."""
    try:
        target = os.readlink(_OMARCHY_THEME_LINK)
        return Path(target).name
    except OSError:
        return None


def _omarchy_is_light() -> bool:
    """True if the current Omarchy theme ships a light.mode marker file."""
    return (_OMARCHY_THEME_LINK / "light.mode").exists()


def detect_theme() -> str:
    """Return a Textual theme name that matches the current OS/Omarchy theme.

    Falls back to ``textual-dark`` when Omarchy is not installed or the theme
    has no direct mapping.
    """
    name = _omarchy_theme_name()
    if name is None:
        return "textual-dark"
    if name in _THEME_MAP:
        return _THEME_MAP[name]
    # Unknown Omarchy theme — at least honour light vs dark.
    return "textual-light" if _omarchy_is_light() else "textual-dark"
