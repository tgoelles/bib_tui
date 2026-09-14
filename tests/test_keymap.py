"""Tests for bibtui.utils.keymap — the central Ctrl/Cmd key-string constants.

Every constant must keep its Ctrl variant (works everywhere) and add the
matching Cmd (`super+`) variant (works only in terminals that forward Cmd as
a distinct key, e.g. Kitty, WezTerm, Ghostty, iTerm2 with the Kitty keyboard
protocol). This pins the additive contract: Ctrl is never removed, Cmd is
never the only way to trigger a shortcut.
"""

from bibtui.utils.keymap import COMMAND_PALETTE, COPY_ENTRY, COPY_KEY, SAVE


def _keys(binding_str: str) -> list[str]:
    # Textual itself strips whitespace around each comma-separated key (see
    # Binding.make_bindings), so mirror that here rather than asserting on
    # exact formatting — a constant written as "ctrl+c, super+c" is just as
    # valid as "ctrl+c,super+c".
    return [key.strip() for key in binding_str.split(",")]


def test_copy_key_has_ctrl_and_super() -> None:
    keys = _keys(COPY_KEY)
    assert "ctrl+c" in keys
    assert "super+c" in keys


def test_copy_entry_has_ctrl_and_super() -> None:
    keys = _keys(COPY_ENTRY)
    assert "ctrl+shift+c" in keys
    assert "super+shift+c" in keys


def test_save_has_ctrl_and_super() -> None:
    keys = _keys(SAVE)
    assert "ctrl+s" in keys
    assert "super+s" in keys


def test_command_palette_has_ctrl_and_super() -> None:
    keys = _keys(COMMAND_PALETTE)
    assert "ctrl+p" in keys
    assert "super+p" in keys
