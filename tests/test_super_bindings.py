"""Integration tests: pressing the Cmd (`super+`) alias fires the same action
as the existing Ctrl binding, for each shortcut wired through
bibtui.utils.keymap.

These exercise the real Textual binding resolver (via `pilot.press`), not
just the key-string constants, so a typo in a BINDINGS call site (e.g.
missing the `super+` alias, or a stale key string) would be caught here even
though bibtui.utils.keymap's own constants are correct.
"""

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
