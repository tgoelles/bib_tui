"""Unit tests for bibtui.bib.validate.validate_entry (pure, no Textual)."""

from datetime import datetime

from bibtui.bib.models import BibEntry
from bibtui.bib.validate import validate_entry


def _blocking_fields(result) -> set[str]:
    return {err["field"] for err in result.blocking_errors}


# ---------------------------------------------------------------------------
# Valid entries per type
# ---------------------------------------------------------------------------


def test_valid_article_passes() -> None:
    e = BibEntry(
        key="Smith2020",
        entry_type="article",
        title="T",
        author="Smith",
        journal="Nature",
        year="2020",
    )
    result = validate_entry(e)
    assert result.is_writable
    assert not result.blocking_errors


def test_valid_book_passes() -> None:
    e = BibEntry(
        key="Book2020",
        entry_type="book",
        title="T",
        author="A",
        year="2020",
        raw_fields={"publisher": "ACME"},
    )
    assert validate_entry(e).is_writable


def test_valid_inproceedings_passes() -> None:
    e = BibEntry(
        key="Conf2020",
        entry_type="inproceedings",
        title="T",
        author="A",
        year="2020",
        raw_fields={"booktitle": "Proc"},
    )
    assert validate_entry(e).is_writable


def test_misc_requires_nothing() -> None:
    e = BibEntry(key="Misc1", entry_type="misc", title="T")
    assert validate_entry(e).is_writable


# ---------------------------------------------------------------------------
# Required-field blocking (new mode)
# ---------------------------------------------------------------------------


def test_article_missing_journal_blocks_new() -> None:
    e = BibEntry(
        key="Smith2020", entry_type="article", title="T", author="A", year="2020"
    )
    result = validate_entry(e, mode="new")
    assert not result.is_writable
    assert "journal" in _blocking_fields(result)


def test_each_required_field_blocks_individually() -> None:
    base = dict(title="T", author="A", journal="J", year="2020")
    for missing in ("title", "author", "journal", "year"):
        fields = dict(base)
        fields[missing] = ""
        e = BibEntry(key="K2020", entry_type="article", **fields)
        result = validate_entry(e, mode="new")
        assert missing in _blocking_fields(result), missing


def test_empty_key_blocks() -> None:
    e = BibEntry(
        key="", entry_type="article", title="T", author="A", journal="J", year="2020"
    )
    assert "key" in _blocking_fields(validate_entry(e))


def test_key_with_space_blocks() -> None:
    e = BibEntry(
        key="bad key",
        entry_type="article",
        title="T",
        author="A",
        journal="J",
        year="2020",
    )
    assert "key" in _blocking_fields(validate_entry(e))


# ---------------------------------------------------------------------------
# Edit mode: "can't make it worse"
# ---------------------------------------------------------------------------


def test_edit_preexisting_gap_only_warns() -> None:
    baseline = BibEntry(
        key="Old2000", entry_type="article", title="T", author="A"
    )  # journal + year already empty
    candidate = BibEntry(
        key="Old2000", entry_type="article", title="T2", author="A"
    )
    result = validate_entry(candidate, mode="edit", baseline=baseline)
    assert result.is_writable  # not blocked
    assert result.warnings  # but surfaced


def test_edit_emptying_a_filled_field_blocks() -> None:
    baseline = BibEntry(
        key="Old2000",
        entry_type="article",
        title="T",
        author="A",
        journal="Nature",
        year="2020",
    )
    candidate = BibEntry(
        key="Old2000", entry_type="article", title="T", author="A", year="2020"
    )  # journal cleared this session
    result = validate_entry(candidate, mode="edit", baseline=baseline)
    assert not result.is_writable
    assert "journal" in _blocking_fields(result)


# ---------------------------------------------------------------------------
# Auto-fixes
# ---------------------------------------------------------------------------


def test_pages_range_normalized() -> None:
    e = BibEntry(
        key="K2020",
        entry_type="article",
        title="T",
        author="A",
        journal="J",
        year="2020",
        raw_fields={"pages": "12-23"},
    )
    result = validate_entry(e)
    assert result.entry.get_field("pages") == "12--23"
    assert any("pages" in fix for fix in result.applied_fixes)


def test_complex_pages_left_alone() -> None:
    e = BibEntry(
        key="K2020",
        entry_type="article",
        title="T",
        author="A",
        journal="J",
        year="2020",
        raw_fields={"pages": "S1-S9, 12"},
    )
    result = validate_entry(e)
    assert result.entry.get_field("pages") == "S1-S9, 12"
    assert not result.applied_fixes


def test_doi_url_stripped() -> None:
    e = BibEntry(
        key="K2020",
        entry_type="article",
        title="T",
        author="A",
        journal="J",
        year="2020",
        doi="https://doi.org/10.1000/xyz",
    )
    result = validate_entry(e)
    assert result.entry.doi == "10.1000/xyz"
    assert any("doi" in fix for fix in result.applied_fixes)


def test_bare_special_escaped_but_not_double() -> None:
    e = BibEntry(
        key="K2020",
        entry_type="article",
        title="Cats & Dogs",
        author="A",
        journal="J",
        year="2020",
    )
    result = validate_entry(e)
    assert result.entry.title == r"Cats \& Dogs"

    already = BibEntry(
        key="K2020",
        entry_type="article",
        title=r"Cats \& Dogs",
        author="A",
        journal="J",
        year="2020",
    )
    result2 = validate_entry(already)
    assert result2.entry.title == r"Cats \& Dogs"  # unchanged, not \\&
    assert not any("title" in fix for fix in result2.applied_fixes)


def test_math_and_underscore_left_untouched() -> None:
    for title in (r"Energy $E=mc^2$", "H_2O uptake", "Café société"):
        e = BibEntry(
            key="K2020",
            entry_type="article",
            title=title,
            author="A",
            journal="J",
            year="2020",
        )
        result = validate_entry(e)
        assert result.entry.title == title


def test_validate_does_not_mutate_original() -> None:
    e = BibEntry(
        key="K2020",
        entry_type="article",
        title="Cats & Dogs",
        author="A",
        journal="J",
        year="2020",
        raw_fields={"pages": "12-23"},
    )
    validate_entry(e)
    assert e.title == "Cats & Dogs"
    assert e.raw_fields["pages"] == "12-23"


# ---------------------------------------------------------------------------
# Year plausibility
# ---------------------------------------------------------------------------


def test_implausible_year_warns_not_blocks() -> None:
    e = BibEntry(
        key="K1200",
        entry_type="article",
        title="T",
        author="A",
        journal="J",
        year="1200",
    )
    result = validate_entry(e)
    assert result.is_writable
    assert any("implausible" in w for w in result.warnings)


def test_future_year_warns() -> None:
    future = str(datetime.now().year + 5)
    e = BibEntry(
        key="Kfut",
        entry_type="article",
        title="T",
        author="A",
        journal="J",
        year=future,
    )
    result = validate_entry(e)
    assert result.is_writable
    assert result.warnings


def test_non_numeric_year_blocks_new() -> None:
    e = BibEntry(
        key="Kbad",
        entry_type="article",
        title="T",
        author="A",
        journal="J",
        year="in press",
    )
    result = validate_entry(e, mode="new")
    assert "year" in _blocking_fields(result)
