"""Layout of the entry viewer: URL lives with the other fields, title has air above."""

import pytest
from rich.text import Text
from textual.css.query import NoMatches
from textual.widgets import Label, Static

from bibtui.app import BibTuiApp
from bibtui.bib.models import BibEntry
from bibtui.widgets.entry_detail import EntryDetail, _render_entry

BIB = "tests/bib_examples/MyCollection.bib"


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    """Never read or write the developer's real ~/.config/bibtui/config.toml —
    the app saves settings such as the split size and recent files."""
    config_file = tmp_path / "config.toml"
    monkeypatch.setattr("bibtui.utils.config.CONFIG_PATH", config_file)
    config_file.write_text("[updates]\ncheck_for_updates = false\n", encoding="utf-8")


_COLORS = {
    "title": "cyan",
    "key": "yellow",
    "required": "green",
    "optional": "blue",
    "warning": "yellow",
    "tag_fg": "white",
    "tag_bg": "green",
}


def _plain_lines(entry: BibEntry) -> list[str]:
    return [
        Text.from_markup(ln).plain for ln in _render_entry(entry, _COLORS).split("\n")
    ]


def _entry(**kwargs) -> BibEntry:
    params = {"key": "Smith2020", "entry_type": "article", "title": "A Title"}
    params.update(kwargs)
    return BibEntry(**params)


def test_url_is_listed_after_doi_with_the_other_fields() -> None:
    lines = _plain_lines(_entry(doi="10.1/x", url="https://example.org/a/long/path"))
    labels = [
        ln.split()[0]
        for ln in lines
        if ln.startswith(("Year", "Journal", "DOI", "URL"))
    ]
    assert labels == ["Year", "Journal", "DOI", "URL"]
    url_line = next(ln for ln in lines if ln.startswith("URL"))
    # Full URL, not shortened like the old status-bar label was.
    assert url_line.endswith("https://example.org/a/long/path")


def test_missing_url_shows_empty_like_other_fields() -> None:
    lines = _plain_lines(_entry())
    assert next(ln for ln in lines if ln.startswith("URL")).endswith("(empty)")


async def test_url_label_is_gone_from_the_status_row() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        detail = app.query_one(EntryDetail)
        try:
            detail.query_one("#detail-url", Label)
        except NoMatches:
            pass
        else:
            raise AssertionError("#detail-url should no longer exist")


async def test_blank_line_between_status_row_and_title() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        detail = app.query_one(EntryDetail)
        detail.show_entry(_entry(url="https://example.org"))
        await pilot.pause()
        meta = detail.query_one("#detail-meta")
        content = detail.query_one("#detail-content", Static)
        gap = content.region.y - (meta.region.y + meta.region.height)
        assert gap == 1


_STATUS_IDS = [
    "#detail-read-state",
    "#detail-priority",
    "#detail-rating",
    "#detail-pdf-status",
]


def test_status_widths_fit_every_possible_value() -> None:
    from bibtui.bib.models import PRIORITIES, READ_STATES
    from bibtui.widgets.entry_detail import (
        _PDF_MARKUP,
        _STATUS_WIDTHS,
        _priority_markup,
        _rating_markup,
        _read_markup,
    )

    def cells(markup: str) -> int:
        return Text.from_markup(markup).cell_len

    for state in READ_STATES:
        assert cells(_read_markup(_entry(read_state=state))) <= _STATUS_WIDTHS["read"]
    for prio in PRIORITIES:
        markup = _priority_markup(_entry(priority=prio))
        assert cells(markup) <= _STATUS_WIDTHS["priority"]
    for rating in range(6):
        markup = _rating_markup(_entry(rating=rating), "white")
        assert cells(markup) <= _STATUS_WIDTHS["rating"]
    for markup in _PDF_MARKUP.values():
        assert cells(markup) <= _STATUS_WIDTHS["pdf"]


async def test_status_row_does_not_shift_between_entries(tmp_path, monkeypatch) -> None:
    from bibtui.bib.models import PRIORITIES, READ_STATES

    (tmp_path / "there.pdf").write_bytes(b"%PDF-1.4")
    variants = [
        _entry(),  # everything unset / unrated / no PDF
        *[_entry(read_state=s) for s in READ_STATES],
        *[_entry(priority=p) for p in PRIORITIES],
        *[_entry(rating=r) for r in range(6)],
        _entry(file=":there.pdf:PDF"),  # linked
        _entry(file=":gone.pdf:PDF"),  # missing
        # Longest of everything at once.
        _entry(read_state="skimmed", priority=2, rating=5, file=":there.pdf:PDF"),
    ]
    app = BibTuiApp(BIB)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        detail = app.query_one(EntryDetail)
        detail.set_pdf_base_dir(str(tmp_path))
        seen: set[tuple[tuple[int, int], ...]] = set()
        for entry in variants:
            detail.show_entry(entry)
            await pilot.pause()
            seen.add(
                tuple(
                    (detail.query_one(i).region.x, detail.query_one(i).region.width)
                    for i in _STATUS_IDS
                )
            )
        assert len(seen) == 1, seen


async def test_status_row_stays_one_line_for_an_oversized_value() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        detail = app.query_one(EntryDetail)
        detail.show_entry(_entry(read_state="reading-it-right-now-honest", rating=9))
        await pilot.pause()
        assert all(detail.query_one(i).region.height == 1 for i in _STATUS_IDS)


@pytest.mark.parametrize("width", [80, 100, 120, 140, 160, 180, 200, 240])
async def test_every_status_label_stays_inside_the_pane(width: int) -> None:
    """The labels are fixed-width, so a narrow pane must stack them rather than
    push the last ones out of sight."""
    app = BibTuiApp(BIB)
    async with app.run_test(size=(width, 40)) as pilot:
        for _ in range(3):  # let the split and the stacking settle
            await pilot.pause()
        detail = app.query_one(EntryDetail)
        detail.show_entry(_entry(read_state="skimmed", priority=2, rating=5))
        await pilot.pause()
        right_edge = detail.region.x + detail.region.width
        for i in _STATUS_IDS:
            region = detail.query_one(i).region
            assert region.x + region.width <= right_edge, f"{i} at width {width}"


async def test_status_row_stacks_only_when_the_pane_is_too_narrow() -> None:
    from bibtui.widgets.entry_detail import _STATUS_ROW_WIDTH

    app = BibTuiApp(BIB)
    async with app.run_test(size=(240, 40)) as pilot:
        for _ in range(3):
            await pilot.pause()
        detail = app.query_one(EntryDetail)
        meta = detail.query_one("#detail-meta")
        assert detail.scrollable_content_region.width >= _STATUS_ROW_WIDTH
        assert not meta.has_class("-stacked")
        assert meta.region.height == 1

        app.query_one(EntryDetail).styles.width = 30
        for _ in range(3):
            await pilot.pause()
        assert meta.has_class("-stacked")
        assert meta.region.height == 2


async def test_status_row_height_is_the_same_for_every_entry() -> None:
    """Stacking may cost a line, but it must not depend on the entry shown."""
    app = BibTuiApp(BIB)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        detail = app.query_one(EntryDetail)
        meta = detail.query_one("#detail-meta")
        heights = set()
        for entry in (_entry(), _entry(read_state="skimmed", priority=2, rating=5)):
            detail.show_entry(entry)
            await pilot.pause()
            heights.add(meta.region.height)
        assert len(heights) == 1, heights


# ── Author block ─────────────────────────────────────────────────────────

_MANY_AUTHORS = " and ".join(f"Surname{i}, Firstname{i}" for i in range(40))


def test_authors_sit_directly_below_the_title_not_in_the_field_list() -> None:
    lines = _plain_lines(_entry(author="Smith, Jane and Doe, John"))
    assert lines[0] == "A Title"
    assert lines[1] == "Smith, Jane / Doe, John"
    assert not any(ln.startswith("Author") for ln in lines)


def test_author_block_is_always_exactly_three_lines() -> None:
    from bibtui.widgets.entry_detail import _AUTHOR_LINES

    for author in ("", "Smith, Jane", "Smith, Jane and Doe, John", _MANY_AUTHORS):
        lines = _plain_lines(_entry(author=author))
        # title, then the reserved author lines, then a blank separator line
        assert lines[1 + _AUTHOR_LINES] == "", author
        assert len(lines[1 : 1 + _AUTHOR_LINES]) == _AUTHOR_LINES


def test_long_author_lists_are_truncated_with_an_ellipsis() -> None:
    lines = _plain_lines(_entry(author=_MANY_AUTHORS))
    authors = lines[1:4]
    assert all(authors)  # all three lines are used
    assert authors[-1].endswith("…")
    assert "Surname39" not in " ".join(authors)  # the tail was cut off


def test_author_lines_respect_the_given_width() -> None:
    text = _render_entry(_entry(author=_MANY_AUTHORS), _COLORS, author_width=40)
    authors = [Text.from_markup(ln).plain for ln in text.split("\n")[1:4]]
    assert max(len(a) for a in authors) <= 40


def test_short_author_lists_are_not_truncated() -> None:
    lines = _plain_lines(_entry(author="Smith, Jane and Doe, John"))
    assert "…" not in lines[1]
    assert lines[2] == lines[3] == ""


def test_missing_author_is_marked_and_still_reserves_the_space() -> None:
    lines = _plain_lines(_entry(author=""))
    assert lines[1] == "(no author)"
    assert lines[2] == lines[3] == ""


def test_markup_characters_in_authors_are_shown_literally() -> None:
    lines = _plain_lines(_entry(author="Smith [Jane] and Doe"))
    assert lines[1] == "Smith [Jane] / Doe"


async def test_content_height_does_not_depend_on_author_count() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        detail = app.query_one(EntryDetail)
        content = detail.query_one("#detail-content", Static)
        heights = set()
        for author in ("", "Smith, Jane", "Smith, Jane and Doe, John", _MANY_AUTHORS):
            detail.show_entry(_entry(author=author))
            await pilot.pause()
            heights.add(content.size.height)
        assert len(heights) == 1, heights


async def test_author_block_rewraps_when_the_pane_is_resized() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test(size=(160, 40)) as pilot:
        await pilot.pause()
        detail = app.query_one(EntryDetail)
        detail.show_entry(_entry(author=_MANY_AUTHORS))
        await pilot.pause()
        wide = detail._author_width
        await pilot.press("greater_than_sign", "greater_than_sign", "greater_than_sign")
        await pilot.pause()
        assert detail._author_width < wide


def test_authors_render_jabref_style_on_one_line_when_there_is_room() -> None:
    author = (
        "Schlager, Birgit and Muckenhuber, Stefan and Schmidt, Simon and "
        "Holzer, Hannes and Rott, Relindis and Maier, Franz Michael and "
        "Saad, Kmeid"
    )
    text = _render_entry(_entry(author=author), _COLORS, author_width=200)
    assert Text.from_markup(text.split("\n")[1]).plain == (
        "Schlager, Birgit / Muckenhuber, Stefan / Schmidt, Simon / "
        "Holzer, Hannes / Rott, Relindis / Maier, Franz Michael / Saad, Kmeid"
    )


def test_a_name_is_never_split_across_lines() -> None:
    text = _render_entry(_entry(author=_MANY_AUTHORS), _COLORS, author_width=45)
    lines = [Text.from_markup(ln).plain for ln in text.split("\n")[1:4]]
    for line in lines:
        # Every line holds whole "SurnameN, FirstnameN" names.
        for name in line.removesuffix(" …").rstrip(" /").split(" / "):
            assert name.startswith("Surname") and ", Firstname" in name, line


def test_separator_stays_at_the_end_of_a_line_not_the_start() -> None:
    text = _render_entry(_entry(author=_MANY_AUTHORS), _COLORS, author_width=45)
    lines = [Text.from_markup(ln).plain for ln in text.split("\n")[1:4]]
    assert not any(line.startswith("/") for line in lines)


def test_truncation_reads_as_a_continued_list() -> None:
    lines = _plain_lines(_entry(author=_MANY_AUTHORS))
    assert lines[3].endswith(" / …")


def test_latex_in_author_names_is_decoded() -> None:
    lines = _plain_lines(
        _entry(author='Sch{\\"o}ner, Wolfgang and Mo{\\v{c}}nik, Gri{\\v{s}}a')
    )
    assert lines[1] == "Schöner, Wolfgang / Močnik, Griša"
