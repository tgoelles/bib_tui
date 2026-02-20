"""Unit tests for bib_tui.bib.models.BibEntry."""

import pytest

from bib_tui.bib.models import (
    PRIORITIES,
    PRIORITY_ICONS,
    PRIORITY_LABELS,
    READ_STATE_ICONS,
    READ_STATES,
    BibEntry,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def entry() -> BibEntry:
    return BibEntry(
        key="Smith2023",
        entry_type="article",
        title="Glacial Dynamics in the 21st Century",
        author="Smith, John and Jones, Mary and Brown, Alice",
        year="2023",
        journal="Nature",
        keywords="glacier, ice, climate",
    )


# ---------------------------------------------------------------------------
# authors_short
# ---------------------------------------------------------------------------


def test_authors_short_surname_first(entry: BibEntry) -> None:
    assert entry.authors_short == "Smith"


def test_authors_short_given_first() -> None:
    e = BibEntry(key="k", entry_type="article", author="John Smith")
    assert e.authors_short == "Smith"


def test_authors_short_single_word() -> None:
    e = BibEntry(key="k", entry_type="article", author="Plato")
    assert e.authors_short == "Plato"


def test_authors_short_unknown_when_empty() -> None:
    e = BibEntry(key="k", entry_type="article")
    assert e.authors_short == "Unknown"


# ---------------------------------------------------------------------------
# title_short
# ---------------------------------------------------------------------------


def test_title_short_no_truncation(entry: BibEntry) -> None:
    assert entry.title_short == entry.title


def test_title_short_truncates_long_title() -> None:
    long = "A" * 80
    e = BibEntry(key="k", entry_type="article", title=long)
    assert e.title_short.endswith("...")
    assert len(e.title_short) == 60


# ---------------------------------------------------------------------------
# url_icon
# ---------------------------------------------------------------------------


def test_url_icon_with_url() -> None:
    e = BibEntry(key="k", entry_type="article", url="https://example.com")
    assert e.url_icon == "🔗"


def test_url_icon_without_url() -> None:
    e = BibEntry(key="k", entry_type="article")
    assert e.url_icon == "  "


# ---------------------------------------------------------------------------
# read_state / cycle_read_state
# ---------------------------------------------------------------------------


def test_read_state_icon_default() -> None:
    e = BibEntry(key="k", entry_type="article")
    assert e.read_state_icon == READ_STATE_ICONS[""]


def test_cycle_read_state_full_cycle() -> None:
    e = BibEntry(key="k", entry_type="article")
    visited = []
    for _ in range(len(READ_STATES) + 1):
        visited.append(e.read_state)
        e.cycle_read_state()
    # After a full cycle we're back to the start
    assert visited[-1] == visited[0]
    assert set(visited[:-1]) == set(READ_STATES)


def test_cycle_read_state_wraps() -> None:
    e = BibEntry(key="k", entry_type="article", read_state="read")
    e.cycle_read_state()
    assert e.read_state == READ_STATES[0]


# ---------------------------------------------------------------------------
# priority / cycle_priority
# ---------------------------------------------------------------------------


def test_priority_icon_default() -> None:
    e = BibEntry(key="k", entry_type="article")
    assert e.priority_icon == PRIORITY_ICONS[0]


def test_priority_label_default() -> None:
    e = BibEntry(key="k", entry_type="article")
    assert e.priority_label == "unset"


def test_cycle_priority_wraps() -> None:
    e = BibEntry(key="k", entry_type="article")
    visited = []
    for _ in range(len(PRIORITIES) + 1):
        visited.append(e.priority)
        e.cycle_priority()
    assert visited[-1] == visited[0]
    assert set(visited[:-1]) == set(PRIORITIES)


# ---------------------------------------------------------------------------
# keywords_list
# ---------------------------------------------------------------------------


def test_keywords_list_parsed(entry: BibEntry) -> None:
    assert entry.keywords_list == ["glacier", "ice", "climate"]


def test_keywords_list_empty() -> None:
    e = BibEntry(key="k", entry_type="article")
    assert e.keywords_list == []


def test_keywords_list_strips_whitespace() -> None:
    e = BibEntry(key="k", entry_type="article", keywords="  ice ,  snow , water  ")
    assert e.keywords_list == ["ice", "snow", "water"]


# ---------------------------------------------------------------------------
# rating_stars
# ---------------------------------------------------------------------------


def test_rating_stars_zero() -> None:
    e = BibEntry(key="k", entry_type="article", rating=0)
    assert e.rating_stars == ""


def test_rating_stars_three() -> None:
    e = BibEntry(key="k", entry_type="article", rating=3)
    assert e.rating_stars == "★★★"


def test_rating_stars_max() -> None:
    e = BibEntry(key="k", entry_type="article", rating=5)
    assert e.rating_stars == "★★★★★"


# ---------------------------------------------------------------------------
# get_field / set_field
# ---------------------------------------------------------------------------


def test_get_field_known(entry: BibEntry) -> None:
    assert entry.get_field("title") == entry.title
    assert entry.get_field("author") == entry.author
    assert entry.get_field("year") == entry.year
    assert entry.get_field("journal") == entry.journal


def test_get_field_rating_as_string(entry: BibEntry) -> None:
    entry.rating = 4
    assert entry.get_field("rating") == "4"


def test_get_field_raw_fallback() -> None:
    e = BibEntry(key="k", entry_type="article", raw_fields={"volume": "12"})
    assert e.get_field("volume") == "12"


def test_get_field_missing_returns_empty() -> None:
    e = BibEntry(key="k", entry_type="article")
    assert e.get_field("nonexistent") == ""


def test_set_field_known() -> None:
    e = BibEntry(key="k", entry_type="article")
    e.set_field("title", "New Title")
    assert e.title == "New Title"


def test_set_field_rating_clamped() -> None:
    e = BibEntry(key="k", entry_type="article")
    e.set_field("rating", "99")
    assert e.rating == 5
    e.set_field("rating", "-5")
    assert e.rating == 0


def test_set_field_rating_invalid_ignored() -> None:
    e = BibEntry(key="k", entry_type="article", rating=3)
    e.set_field("rating", "notanumber")
    assert e.rating == 3  # unchanged


def test_set_field_unknown_goes_to_raw() -> None:
    e = BibEntry(key="k", entry_type="article")
    e.set_field("volume", "7")
    assert e.raw_fields["volume"] == "7"
