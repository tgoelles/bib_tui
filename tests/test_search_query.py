"""Unit tests for the search/filter query syntax (bibtui.widgets.entry_list)."""

import re

import pytest

from bibtui.bib.models import BibEntry
from bibtui.bib.search import QueryError, compile_query, matches_query


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


def test_hash_in_query_is_not_treated_as_a_comment() -> None:
    # A citekey or title containing '#' must search in full, not get
    # silently truncated at the '#' as a shell-style comment would be.
    e = _entry(key="rfc-2119#section3")
    assert matches_query(e, "c:rfc-2119#section3")


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


# ---------------------------------------------------------------------------
# Boolean operators (#88)
# ---------------------------------------------------------------------------

SMITH = _entry(
    key="Smith2020",
    author="Smith, John",
    title="Glacier melt",
    keywords="ice",
    journal="Nature",
    year="2020",
    read_state="read",
)
JONES = _entry(
    key="Jones2016",
    author="Jones, Ann",
    title="Ice sheet dynamics",
    keywords="ice, snow",
    journal="Science",
    year="2016",
    read_state="to-read",
)
BROWN = _entry(
    key="Brown2010",
    author="Brown, Bo",
    title="Snow cover",
    keywords="snow",
    journal="Nature",
    year="2010",
)
LIBRARY = [SMITH, JONES, BROWN]


def _keys(query: str) -> list[str]:
    matcher = compile_query(query)
    return [e.key for e in LIBRARY if matcher(e)]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("a:smith OR a:jones", ["Smith2020", "Jones2016"]),
        ("a:smith or a:jones", ["Smith2020", "Jones2016"]),
        ("a:(smith OR jones)", ["Smith2020", "Jones2016"]),
        ("a:(smith OR jones) k:snow", ["Jones2016"]),
        ("k:ice NOT r:read", ["Jones2016"]),
        ("NOT j:nature", ["Jones2016"]),
        ("NOT NOT j:nature", ["Smith2020", "Brown2010"]),
        ("j:(nature OR science) y:2015-", ["Smith2020", "Jones2016"]),
        ('(t:glacier OR t:"ice sheet") y:2015-', ["Smith2020", "Jones2016"]),
        # AND binds tighter than OR, NOT tighter than AND.
        ("k:snow y:2016 OR a:smith", ["Smith2020", "Jones2016"]),
        ("k:snow (y:2016 OR a:smith)", ["Jones2016"]),
        ("k:snow AND NOT y:2016 OR a:smith", ["Smith2020", "Brown2010"]),
        # A prefixed term inside a field group keeps its own field.
        ("a:(smith OR t:snow)", ["Smith2020", "Brown2010"]),
        # Year groups use the range syntax.
        ("y:(2010 OR 2020)", ["Smith2020", "Brown2010"]),
    ],
)
def test_boolean_queries(query: str, expected: list[str]) -> None:
    assert _keys(query) == expected


def test_operators_are_terms_when_quoted_or_prefixed() -> None:
    e = _entry(title="To be or not to be")
    assert matches_query(e, 't:"or"')
    assert matches_query(e, "t:not")
    assert not matches_query(_entry(title="Glacier"), "t:not")


def test_quoted_parentheses_are_literal() -> None:
    e = _entry(title="The (in)stability of ice")
    assert matches_query(e, 't:"(in)stability"')


def test_apostrophe_is_an_ordinary_character() -> None:
    e = _entry(author="O'Brien, Pat")
    assert matches_query(e, "a:o'brien")


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        # Half-typed queries filter as if the missing part weren't there yet.
        ("a:smith OR", ["Smith2020"]),
        ("a:smith OR (", ["Smith2020"]),
        ("a:(smith OR jones", ["Smith2020", "Jones2016"]),
        ("(k:snow", ["Jones2016", "Brown2010"]),
        ("k:ice NOT", ["Smith2020", "Jones2016"]),
        ("a:(", ["Smith2020", "Jones2016", "Brown2010"]),
        ("NOT", ["Smith2020", "Jones2016", "Brown2010"]),
        ('t:"ice sh', ["Jones2016"]),
        # A leading or doubled AND has always been ignored.
        ("AND a:smith", ["Smith2020"]),
        ("a:smith AND AND y:2020", ["Smith2020"]),
    ],
)
def test_incomplete_queries_still_filter(query: str, expected: list[str]) -> None:
    assert _keys(query) == expected


@pytest.mark.parametrize(
    ("query", "message"),
    [
        ("OR a:smith", "OR needs a term on both sides"),
        ("a:smith OR OR a:jones", "OR needs a term on both sides"),
        ("(a:smith OR)", "OR needs a term on both sides"),
        ("a:smith)", "')' without a matching '('"),
        ("()", "empty parentheses"),
        ("a:() k:ice", "empty parentheses"),
        ("NOT OR a:smith", "NOT needs a term after it"),
        ("(NOT)", "NOT needs a term after it"),
    ],
)
def test_invalid_queries_raise(query: str, message: str) -> None:
    with pytest.raises(QueryError, match=re.escape(message)):
        compile_query(query)


def test_empty_query_matches_everything() -> None:
    assert _keys("") == ["Smith2020", "Jones2016", "Brown2010"]
