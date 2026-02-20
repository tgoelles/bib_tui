"""Unit tests for bib_tui.bib.parser."""

from pathlib import Path

import pytest

from bibtui.bib.models import BibEntry
from bibtui.bib.parser import (
    bibtex_str_to_entry,
    entry_to_bibtex_str,
    load,
    save,
)

EX1_BIB = Path(__file__).parent / "bib_examples" / "ex1.bib"
MY_COLLECTION = Path(__file__).parent / "bib_examples" / "MyCollection.bib"


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------


def test_load_ex1_returns_entries() -> None:
    entries = load(str(EX1_BIB))
    assert len(entries) >= 1
    keys = {e.key for e in entries}
    assert "smit54" in keys


def test_load_ex1_fields_parsed() -> None:
    entries = {e.key: e for e in load(str(EX1_BIB))}
    e = entries["smit54"]
    assert "Smith" in e.author
    assert e.year == "1954"
    assert "History" in e.title
    assert e.journal != ""


def test_load_mycollection() -> None:
    entries = load(str(MY_COLLECTION))
    assert len(entries) >= 1


# ---------------------------------------------------------------------------
# entry_to_bibtex_str / bibtex_str_to_entry round-trip
# ---------------------------------------------------------------------------


SIMPLE_BIBTEX = """\
@article{Smith2023,
  title = {Glacial Dynamics},
  author = {Smith, John},
  year = {2023},
  journal = {Nature},
  doi = {10.1000/test},
}
"""


def test_parse_simple_bibtex() -> None:
    e = bibtex_str_to_entry(SIMPLE_BIBTEX)
    assert e.key == "Smith2023"
    assert e.entry_type == "article"
    assert e.title == "Glacial Dynamics"
    assert e.author == "Smith, John"
    assert e.year == "2023"
    assert e.journal == "Nature"
    assert e.doi == "10.1000/test"


def test_round_trip_basic_fields() -> None:
    original = BibEntry(
        key="Jones2020",
        entry_type="article",
        title="Test Title",
        author="Jones, Bob",
        year="2020",
        journal="Science",
        doi="10.1234/test",
    )
    text = entry_to_bibtex_str(original)
    recovered = bibtex_str_to_entry(text)

    assert recovered.key == original.key
    assert recovered.entry_type == original.entry_type
    assert recovered.title == original.title
    assert recovered.author == original.author
    assert recovered.year == original.year
    assert recovered.journal == original.journal
    assert recovered.doi == original.doi


def test_round_trip_rating() -> None:
    original = BibEntry(key="k", entry_type="article", title="T", rating=4)
    recovered = bibtex_str_to_entry(entry_to_bibtex_str(original))
    assert recovered.rating == 4


def test_round_trip_read_state() -> None:
    original = BibEntry(key="k", entry_type="article", title="T", read_state="read")
    recovered = bibtex_str_to_entry(entry_to_bibtex_str(original))
    assert recovered.read_state == "read"


def test_round_trip_priority() -> None:
    original = BibEntry(key="k", entry_type="article", title="T", priority=2)
    recovered = bibtex_str_to_entry(entry_to_bibtex_str(original))
    assert recovered.priority == 2


def test_round_trip_keywords() -> None:
    original = BibEntry(
        key="k", entry_type="article", title="T", keywords="ice, snow, water"
    )
    recovered = bibtex_str_to_entry(entry_to_bibtex_str(original))
    assert recovered.keywords_list == ["ice", "snow", "water"]


def test_round_trip_raw_fields() -> None:
    original = BibEntry(
        key="k", entry_type="article", title="T", raw_fields={"volume": "12"}
    )
    recovered = bibtex_str_to_entry(entry_to_bibtex_str(original))
    assert recovered.raw_fields.get("volume") == "12"


def test_round_trip_url_and_file() -> None:
    original = BibEntry(
        key="k",
        entry_type="article",
        title="T",
        url="https://example.com",
        file=":paper.pdf:PDF",
    )
    recovered = bibtex_str_to_entry(entry_to_bibtex_str(original))
    assert recovered.url == "https://example.com"
    assert recovered.file == ":paper.pdf:PDF"


def test_invalid_bibtex_raises() -> None:
    with pytest.raises(Exception):
        bibtex_str_to_entry("this is not bibtex at all")


def test_bibtex_no_entry_raises() -> None:
    with pytest.raises(ValueError, match="No valid BibTeX entry"):
        bibtex_str_to_entry("% just a comment\n")


# ---------------------------------------------------------------------------
# save / load round-trip
# ---------------------------------------------------------------------------


def test_save_load_roundtrip(tmp_path) -> None:
    entries = [
        BibEntry(key="A2020", entry_type="article", title="Alpha", year="2020"),
        BibEntry(key="B2021", entry_type="book", title="Beta", year="2021"),
    ]
    path = str(tmp_path / "test.bib")
    save(entries, path)
    loaded = load(path)
    keys = {e.key for e in loaded}
    assert "A2020" in keys
    assert "B2021" in keys


def test_save_load_preserves_all_fields(tmp_path) -> None:
    original = BibEntry(
        key="Full2023",
        entry_type="article",
        title="Full Entry",
        author="Doe, Jane",
        year="2023",
        journal="PLOS ONE",
        doi="10.1371/test",
        url="https://example.com",
        keywords="a, b, c",
        rating=3,
        read_state="skimmed",
        priority=1,
        file=":Full2023.pdf:PDF",
    )
    path = str(tmp_path / "full.bib")
    save([original], path)
    recovered = load(path)[0]

    assert recovered.title == original.title
    assert recovered.author == original.author
    assert recovered.doi == original.doi
    assert recovered.rating == original.rating
    assert recovered.read_state == original.read_state
    assert recovered.priority == original.priority
    assert recovered.file == original.file
    assert recovered.keywords_list == original.keywords_list
