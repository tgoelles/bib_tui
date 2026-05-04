"""Unit tests for bib_tui.bib.parser."""

from pathlib import Path

import pytest

import bibtui.bib.parser as parser_mod
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


def test_save_noop_preserves_mycollection_bytes(tmp_path) -> None:
    dst = tmp_path / "mycollection_copy.bib"
    original_text = MY_COLLECTION.read_text(encoding="utf-8")
    dst.write_text(original_text, encoding="utf-8")

    entries = load(str(dst))
    save(entries, str(dst))

    assert dst.read_text(encoding="utf-8") == original_text


def test_save_noop_preserves_ex1_bytes(tmp_path) -> None:
    src = EX1_BIB
    dst = tmp_path / "ex1_copy.bib"
    original_text = src.read_text(encoding="utf-8")
    dst.write_text(original_text, encoding="utf-8")

    entries = load(str(dst))
    save(entries, str(dst))

    assert dst.read_text(encoding="utf-8") == original_text


def test_save_rewrites_only_changed_entry_block(tmp_path) -> None:
    source = """% keep this header exactly
@ARTICLE{KeyA,
    AUTHOR = {Doe, Jane},
    TITLE = {Old Title},
    YEAR = {2020},
}

% keep this separator exactly
@ARTICLE{KeyB,
    AUTHOR = {Roe, John},
    TITLE = {Second Title},
    YEAR = {2021},
}
"""
    path = tmp_path / "minimal_patch.bib"
    path.write_text(source, encoding="utf-8")

    entries = load(str(path))
    for e in entries:
        if e.key == "KeyA":
            e.title = "New Title"

    save(entries, str(path))
    out = path.read_text(encoding="utf-8")

    # Header and untouched second entry remain byte-identical.
    assert "% keep this header exactly\n" in out
    untouched_block = """@ARTICLE{KeyB,
    AUTHOR = {Roe, John},
    TITLE = {Second Title},
    YEAR = {2021},
}
"""
    assert untouched_block in out

    # Changed entry gets rewritten with new content.
    assert "New Title" in out
    assert "Old Title" not in out


def test_save_appends_new_entry_without_touching_existing_text(tmp_path) -> None:
    source = """% preserve this whole prefix
@ARTICLE{KeyA,
  AUTHOR = {Doe, Jane},
  TITLE = {Only Title},
  YEAR = {2020},
}
"""
    path = tmp_path / "append_only.bib"
    path.write_text(source, encoding="utf-8")

    entries = load(str(path))
    entries.append(
        BibEntry(
            key="KeyC",
            entry_type="article",
            title="Appended",
            author="New, Author",
            year="2022",
        )
    )

    save(entries, str(path))
    out = path.read_text(encoding="utf-8")

    assert out.startswith(source)
    assert "@article{KeyC," in out


def test_save_patches_only_changed_field(tmp_path) -> None:
    """Changing one field on one entry must leave every other line untouched."""
    source = """\
@article{Alpha2001,
  title = {Ice Cores},
  author = {Smith, A},
  year = {2001},
}

@article{Beta2002,
  title = {Snow Dynamics},
  author = {Jones, B},
  year = {2002},
  journal = {Nature},
}
"""
    path = tmp_path / "patch_field.bib"
    path.write_text(source, encoding="utf-8")

    entries = load(str(path))
    by_key = {e.key: e for e in entries}

    # Change only the read_state on Alpha2001.
    modified = by_key["Alpha2001"]
    modified = BibEntry(
        key=modified.key,
        entry_type=modified.entry_type,
        title=modified.title,
        author=modified.author,
        year=modified.year,
        read_state="read",
    )
    save([modified, by_key["Beta2002"]], str(path))

    result = path.read_text(encoding="utf-8")
    result_lines = result.splitlines()
    source_lines = source.splitlines()

    # Beta2002 block must be byte-identical.
    beta_src_lines = [
        l
        for l in source_lines
        if "Beta2002" in l
        or "Snow" in l
        or "Jones" in l
        or "2002" in l
        or "Nature" in l
    ]
    for line in beta_src_lines:
        assert line in result_lines, f"Beta2002 line lost: {line!r}"

    # Alpha2001 must have a readstatus line.
    assert any("readstatus" in l for l in result_lines), "readstatus not patched in"

    # All Alpha2001 lines that were NOT added must be preserved verbatim.
    alpha_src_lines = [
        l
        for l in source_lines
        if "@article{Alpha2001" in l
        or "Ice Cores" in l
        or "Smith" in l
        or "{2001}" in l
    ]
    for line in alpha_src_lines:
        assert line in result_lines, f"Alpha2001 original line lost: {line!r}"


def test_save_add_field_repairs_missing_separator_comma(tmp_path) -> None:
    source = """\
@article{Goelles2020,
    title         = {Fault Detection},
    author        = {Goelles, Thomas},
    year          = {2020},
    doi           = {10.3390/s20133662},
    bdsk-url-1    = {https://doi.org/10.3390/s20133662}
}
"""
    path = tmp_path / "comma_repair.bib"
    path.write_text(source, encoding="utf-8")

    entries = load(str(path))
    entry = entries[0]
    entry.read_state = "to-read"

    save(entries, str(path))
    out = path.read_text(encoding="utf-8")

    assert "bdsk-url-1    = {https://doi.org/10.3390/s20133662}," in out
    assert "readstatus = {to-read}" in out
    assert "readstatus = {to-read},\n}" not in out

    # Ensure the produced BibTeX stays parseable.
    reparsed = load(str(path))
    assert reparsed[0].read_state == "to-read"


def test_save_validates_changed_entry_and_falls_back_on_invalid_patch(
    tmp_path, monkeypatch
) -> None:
    source = """\
@article{KeyA,
  title = {Alpha},
  year = {2020},
}
"""
    path = tmp_path / "validate_changed_entry.bib"
    path.write_text(source, encoding="utf-8")

    entries = load(str(path))
    entries[0].read_state = "read"

    def _bad_patch(_block_text, _bp_entry, _desired):
        return "@article{BROKEN\n"

    monkeypatch.setattr(parser_mod, "_patch_entry_block", _bad_patch)

    save(entries, str(path))
    out = path.read_text(encoding="utf-8")

    assert "BROKEN" not in out
    assert "readstatus" in out
    reparsed = load(str(path))
    assert reparsed[0].key == "KeyA"
    assert reparsed[0].read_state == "read"


def test_save_noop_preserves_entry_with_custom_raw_fields(tmp_path) -> None:
    """A no-op save on an entry with custom/unknown fields must be byte-identical."""
    source = """\
@article{Custom2023,
  title         = {Ice Dynamics},
  author        = {Smith, A},
  year          = {2023},
  my-custom-key = {some custom value},
  another-field = {42},
}
"""
    path = tmp_path / "custom_noop.bib"
    path.write_text(source, encoding="utf-8")

    entries = load(str(path))
    save(entries, str(path))

    assert path.read_text(encoding="utf-8") == source


def test_save_custom_raw_field_not_lost_when_other_field_changes(tmp_path) -> None:
    """Changing one known field must not drop custom raw_fields from the same entry."""
    source = """\
@article{Custom2023,
  title         = {Ice Dynamics},
  author        = {Smith, A},
  year          = {2023},
  my-custom-key = {some custom value},
}
"""
    path = tmp_path / "custom_keep.bib"
    path.write_text(source, encoding="utf-8")

    entries = load(str(path))
    entries[0].read_state = "read"
    save(entries, str(path))

    out = path.read_text(encoding="utf-8")

    # Custom field must still be present verbatim.
    assert "my-custom-key = {some custom value}" in out
    # The new field must have been added.
    assert "readstatus" in out
    # The result must be parseable and round-trippable.
    reparsed = load(str(path))
    assert reparsed[0].read_state == "read"
    assert reparsed[0].raw_fields.get("my-custom-key") == "some custom value"
