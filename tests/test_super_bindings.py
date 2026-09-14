"""Integration tests: pressing the Cmd (`super+`) alias fires the same action
as the existing Ctrl binding, for each shortcut wired through
bibtui.utils.keymap.

These exercise the real Textual binding resolver (via `pilot.press`), not
just the key-string constants, so a typo in a BINDINGS call site (e.g.
missing the `super+` alias, or a stale key string) would be caught here even
though bibtui.utils.keymap's own constants are correct.

IMPORTANT LIMITATION, read before adding more `pilot.press("ctrl+shift+...")`
assertions: `pilot.press(key)` injects a synthetic `events.Key(key, ...)`
directly — it never goes through Textual's actual terminal-input parser
(`textual._xterm_parser.XTermParser`), so it cannot catch a real terminal's
key-delivery limits. `Binding("ctrl+shift+c", ...)` resolves correctly in
the binding table (see `test_ctrl_shift_c_resolves_in_binding_table` below),
but in practice `ctrl+shift+c` rarely reaches any app at all, for two
independent reasons neither of which `pilot.press` can see:

1. Most terminal emulators claim Ctrl+Shift+C as their own built-in "copy
   selected text" shortcut and never forward it anywhere — e.g. Kitty's
   default keymap binds `kitty_mod+c` (`kitty_mod` defaults to `ctrl+shift`)
   to `copy_to_clipboard`. This happens at the terminal's own keybinding
   layer, before any protocol negotiation — unrelated to Kitty *keyboard
   protocol* support, and it's why the key can appear to "do nothing".
2. On terminals that don't claim it, most still can't tell Ctrl+Shift+C
   apart from plain Ctrl+C at the byte level (see
   `test_raw_ctrl_c_byte_cannot_be_distinguished_from_shift`), so it falls
   back to "copy cite key" instead.

`ctrl+y` is the alias that's guaranteed to reach the app everywhere; prefer
testing against that for anything claiming to "always work".
"""

from textual._xterm_parser import XTermParser

from bibtui.app import BibTuiApp
from bibtui.utils.config import Config
from bibtui.widgets.modals import SettingsModal

BIB = "tests/bib_examples/MyCollection.bib"


async def test_super_c_triggers_copy_key(monkeypatch) -> None:
    app = BibTuiApp(BIB)
    calls: list[bool] = []
    monkeypatch.setattr(app, "action_copy_key", lambda: calls.append(True))

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("super+c")

    assert calls == [True]


async def test_super_shift_c_triggers_copy_entry(monkeypatch) -> None:
    app = BibTuiApp(BIB)
    calls: list[bool] = []
    monkeypatch.setattr(app, "action_copy_entry", lambda: calls.append(True))

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("super+shift+c")

    assert calls == [True]


async def test_ctrl_c_still_triggers_copy_key(monkeypatch) -> None:
    """Ctrl must keep working unchanged — this is an additive alias, not a swap."""
    app = BibTuiApp(BIB)
    calls: list[bool] = []
    monkeypatch.setattr(app, "action_copy_key", lambda: calls.append(True))

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+c")

    assert calls == [True]


async def test_super_p_opens_command_palette(monkeypatch) -> None:
    app = BibTuiApp(BIB)
    calls: list[bool] = []
    monkeypatch.setattr(app, "action_command_palette", lambda: calls.append(True))

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("super+p")

    assert calls == [True]


async def test_super_s_triggers_save_in_settings_modal(monkeypatch) -> None:
    app = BibTuiApp(BIB)
    calls: list[bool] = []

    async with app.run_test() as pilot:
        await pilot.pause()
        modal = SettingsModal(Config())
        monkeypatch.setattr(modal, "action_save", lambda: calls.append(True))
        app.push_screen(modal)
        await pilot.pause()
        await pilot.press("super+s")

    assert calls == [True]


async def test_ctrl_y_triggers_copy_entry(monkeypatch) -> None:
    """Ctrl+Y is the copy-BibTeX-entry shortcut guaranteed to reach the app
    in every terminal — unlike ctrl+shift+c, see the module docstring."""
    app = BibTuiApp(BIB)
    calls: list[bool] = []
    monkeypatch.setattr(app, "action_copy_entry", lambda: calls.append(True))

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+y")

    assert calls == [True]


async def test_ctrl_shift_c_resolves_in_binding_table(monkeypatch) -> None:
    """The BINDINGS entry itself is wired correctly...

    ...but this only proves the binding *table* maps "ctrl+shift+c" to
    copy_entry. It says nothing about whether a real terminal can ever
    produce that exact key — see the next test.
    """
    app = BibTuiApp(BIB)
    calls: list[bool] = []
    monkeypatch.setattr(app, "action_copy_entry", lambda: calls.append(True))

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+shift+c")

    assert calls == [True]


def test_raw_ctrl_c_byte_cannot_be_distinguished_from_shift() -> None:
    """The terminal-level reason ctrl+shift+c "doesn't work" for most users.

    Feed the actual byte a terminal sends for Ctrl+C (0x03) through
    Textual's real input parser, in legacy (non-Kitty-protocol) mode. It
    resolves to plain "ctrl+c" — there is no byte-level difference for
    whether Shift was also held, so pressing what a user thinks is
    Ctrl+Shift+C silently fires "copy cite key" (ctrl+c's action) instead
    of "copy BibTeX entry" on any terminal that doesn't speak the Kitty
    keyboard protocol. This is exactly the gap `pilot.press` cannot see:
    it injects the key string directly and never runs it through this
    parser.
    """
    parser = XTermParser(False)
    events = list(parser.feed(chr(0x03)))

    assert [e.key for e in events] == ["ctrl+c"]
