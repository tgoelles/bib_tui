"""Layout of the entry viewer: URL lives with the other fields, title has air above."""

from rich.text import Text
from textual.css.query import NoMatches
from textual.widgets import Label, Static

from bibtui.app import BibTuiApp
from bibtui.bib.models import BibEntry
from bibtui.widgets.entry_detail import EntryDetail, _render_entry

BIB = "tests/bib_examples/MyCollection.bib"
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
        if ln.startswith(("Author", "Year", "Journal", "DOI", "URL"))
    ]
    assert labels == ["Author", "Year", "Journal", "DOI", "URL"]
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
