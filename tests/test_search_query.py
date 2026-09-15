"""Unit tests for the search/filter query syntax (bibtui.widgets.entry_list)."""

from bibtui.bib.models import BibEntry
from bibtui.widgets.entry_list import matches_query


def _entry(**kwargs) -> BibEntry:
    kwargs.setdefault("entry_type", "article")
    kwargs.setdefault("key", "Test2020")
    return BibEntry(**kwargs)


# ---------------------------------------------------------------------------
# Existing prefixes still work (regression guard)
# ---------------------------------------------------------------------------


def test_plain_words_match_across_title_author_keywords_key() -> None:
    e = _entry(title="Glacier melt", author="Smith", keywords="ice", key="Smith2020")
    assert matches_query(e, "glacier")
    assert matches_query(e, "smith")
    assert not matches_query(e, "nonexistent")


def test_field_prefix_author() -> None:
    e = _entry(author="Jones, A.")
    assert matches_query(e, "a:jones")
    assert not matches_query(e, "a:smith")


def test_closed_year_range_still_works() -> None:
    e = _entry(year="2015")
    assert matches_query(e, "y:2010-2020")
    assert not matches_query(e, "y:2021-2030")


def test_multiple_terms_are_anded() -> None:
    e = _entry(author="Smith", journal="Nature", year="2025")
    assert matches_query(e, "a:smith j:nature y:2025")
    assert not matches_query(e, "a:smith j:nature y:2020")


def test_and_keyword_is_ignored() -> None:
    e = _entry(journal="Nature", year="2025")
    assert matches_query(e, "j:nature AND y:2025")


# ---------------------------------------------------------------------------
# New: open year ranges and comparisons
# ---------------------------------------------------------------------------


def test_open_lower_bound_year_range() -> None:
    assert matches_query(_entry(year="2010"), "y:2010-")
    assert matches_query(_entry(year="2015"), "y:2010-")
    assert not matches_query(_entry(year="2005"), "y:2010-")


def test_open_upper_bound_year_range() -> None:
    assert matches_query(_entry(year="2010"), "y:-2010")
    assert matches_query(_entry(year="2005"), "y:-2010")
    assert not matches_query(_entry(year="2015"), "y:-2010")


def test_year_greater_than() -> None:
    assert matches_query(_entry(year="2015"), "y:>2010")
    assert not matches_query(_entry(year="2010"), "y:>2010")


def test_year_greater_than_or_equal() -> None:
    assert matches_query(_entry(year="2010"), "y:>=2010")
    assert not matches_query(_entry(year="2009"), "y:>=2010")


def test_year_less_than() -> None:
    assert matches_query(_entry(year="2005"), "y:<2010")
    assert not matches_query(_entry(year="2010"), "y:<2010")


def test_year_less_than_or_equal() -> None:
    assert matches_query(_entry(year="2010"), "y:<=2010")
    assert not matches_query(_entry(year="2011"), "y:<=2010")


def test_entry_without_year_never_matches_a_range_or_comparison() -> None:
    e = _entry(year="")
    assert not matches_query(e, "y:2010-")
    assert not matches_query(e, "y:-2010")
    assert not matches_query(e, "y:>2010")
    assert not matches_query(e, "y:<2010")


# ---------------------------------------------------------------------------
# New: quoted values
# ---------------------------------------------------------------------------


def test_quoted_keyword_value_keeps_the_space() -> None:
    e = _entry(keywords="sea ice, climate")
    assert matches_query(e, 'k:"sea ice"')
    assert not matches_query(e, 'k:"lake ice"')


def test_unbalanced_quote_falls_back_instead_of_raising() -> None:
    e = _entry(keywords="sea ice")
    # Must not raise, even mid-typing with an open quote.
    matches_query(e, 'k:"sea ice')


# ---------------------------------------------------------------------------
# New: read state and priority/urgency prefixes
# ---------------------------------------------------------------------------


def test_read_state_prefix_exact_match() -> None:
    e = _entry(read_state="to-read")
    assert matches_query(e, "r:to-read")
    assert not matches_query(e, "r:read")  # not a substring match


def test_read_state_long_form_prefixes() -> None:
    e = _entry(read_state="skimmed")
    assert matches_query(e, "state:skimmed")
    assert matches_query(e, "read:skimmed")


def test_priority_prefix_matches_label() -> None:
    e = _entry(priority=1)  # "high"
    assert matches_query(e, "pr:high")
    assert matches_query(e, "priority:high")
    assert matches_query(e, "urgency:high")
    assert not matches_query(e, "pr:low")


def test_priority_unset_label() -> None:
    e = _entry(priority=0)
    assert matches_query(e, "pr:unset")
