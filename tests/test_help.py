"""The ``?`` help screen: structure and line layout."""

from pathlib import Path

from rich.text import Text
from textual.widgets import Label, Static

from bibtui.app import BibTuiApp
from bibtui.widgets.modals import (
    _HELP_PARTS,
    _HELP_WRAP_WIDTH,
    HelpModal,
    _InstantScroll,
    _build_help_part,
    _build_help_section,
)


def _sections(part_title: str) -> dict[str, list[tuple]]:
    part = dict(_HELP_PARTS)[part_title]
    return dict(part)


def test_search_and_filters_are_grouped_together() -> None:
    sections = _sections("Search & filters")
    assert list(sections) == [
        "Search — press s",
        "Field prefixes",
        "Year filters",
        "Examples",
        "Saved filters — press f",
    ]


def test_filter_keys_are_not_listed_outside_search_and_filters() -> None:
    for title, sections in _HELP_PARTS:
        if title == "Search & filters":
            continue
        for section_title, _ in sections:
            assert "filter" not in section_title.lower(), section_title


def test_no_rendered_line_exceeds_the_dialog_width() -> None:
    for _, sections in _HELP_PARTS:
        for line in _build_help_part(sections).splitlines():
            assert len(Text.from_markup(line).plain) <= _HELP_WRAP_WIDTH, line


def test_long_descriptions_wrap_under_the_description_column() -> None:
    items = [("k", "word " * 40)]
    lines = _build_help_section("Demo", items)[1:]
    assert len(lines) > 1
    plains = [Text.from_markup(line).plain for line in lines]
    # Description column: 2 indent + 12 key width + 2 gap
    assert plains[0].startswith("  k" + " " * 13 + "word")
    assert all(p.startswith(" " * 16 + "word") for p in plains[1:])


def test_gutter_widens_for_long_keys() -> None:
    lines = _build_help_section("Demo", [("a:smith t:glacier", "Combined")])[1:]
    plain = Text.from_markup(lines[0]).plain
    assert plain == "  a:smith t:glacier  Combined"


async def test_help_modal_renders_one_banner_per_part(tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    monkeypatch.setattr("bibtui.utils.config.CONFIG_PATH", config_file)
    config_file.write_text("[updates]\ncheck_for_updates = false\n", encoding="utf-8")
    bib = Path("tests/bib_examples/MyCollection.bib")
    app = BibTuiApp(str(bib))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpModal)
        banners = [str(w.render()) for w in app.screen.query(".help-part")]
        assert banners == [title for title, _ in _HELP_PARTS]
        assert all(isinstance(w, Label) for w in app.screen.query(".help-part"))
        assert len(app.screen.query(Static)) >= len(_HELP_PARTS) + 1


async def test_arrow_keys_scroll_help_without_animation(tmp_path, monkeypatch) -> None:
    """Held arrow keys must not restart an easing animation on every repeat."""
    config_file = tmp_path / "config.toml"
    monkeypatch.setattr("bibtui.utils.config.CONFIG_PATH", config_file)
    config_file.write_text("[updates]\ncheck_for_updates = false\n", encoding="utf-8")
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        scroll = app.screen.query_one(_InstantScroll)
        assert app.screen.focused is scroll

        animate_args: list[bool] = []
        real_down, real_up = scroll.scroll_down, scroll.scroll_up
        monkeypatch.setattr(
            scroll,
            "scroll_down",
            lambda **kw: (
                animate_args.append(kw.get("animate", True)),
                real_down(**kw),
            ),
        )
        monkeypatch.setattr(
            scroll,
            "scroll_up",
            lambda **kw: (animate_args.append(kw.get("animate", True)), real_up(**kw)),
        )
        await pilot.press("down", "down", "down", "up")
        assert animate_args == [False, False, False, False]
        assert scroll.scroll_y == 2


def test_an_empty_description_does_not_crash_the_help_screen() -> None:
    """``_HELP_PARTS`` is hand-edited; a key left without a description used to
    raise IndexError and take the whole ``?`` screen down."""
    lines = _build_help_section("Demo", [("k", "")])[1:]
    assert Text.from_markup(lines[0]).plain.rstrip() == "  k"
