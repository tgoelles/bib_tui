"""Tests for bibtui.pdf.paths — PDF lookup/formatting helpers.

These pin down the "is there a local PDF for this entry?" contract that the
table's file-status column, the entry-detail panel's PDF actions, and the
app's batch-fetch/autolink logic all rely on. They must all agree, or the UI
ends up in the state reported on macOS: the table shows a PDF is linked
(square filled) while the detail panel's action buttons still only offer
Fetch/Add, because that one call site did its own bare `os.path.exists()`
check without the same fallbacks.
"""

import unicodedata
from pathlib import Path

from bibtui.pdf.paths import find_pdf_for_entry, format_jabref_path, parse_jabref_path


def test_parse_jabref_path_joins_relative_to_base_dir() -> None:
    assert parse_jabref_path(":paper.pdf:PDF", "/library") == "/library/paper.pdf"


def test_parse_jabref_path_keeps_absolute_path_untouched() -> None:
    assert parse_jabref_path(":/abs/paper.pdf:PDF", "/library") == "/abs/paper.pdf"


def test_find_pdf_for_entry_returns_none_when_nothing_matches(tmp_path: Path) -> None:
    assert find_pdf_for_entry(":missing.pdf:PDF", "Smith2023", str(tmp_path)) is None


def test_find_pdf_for_entry_uses_exact_stored_path_when_present(
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "Smith2023 - Title.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    found = find_pdf_for_entry(":Smith2023 - Title.pdf:PDF", "Smith2023", str(tmp_path))

    assert found == str(pdf)


def test_find_pdf_for_entry_falls_back_to_entry_key_glob(tmp_path: Path) -> None:
    """The stored file field can go stale (renamed/regenerated PDF) while a
    same-entry-key PDF still exists in the base dir; the lookup should still
    find it, exactly as the table's status column relies on."""
    actual = tmp_path / "Smith2023 - Renamed Title.pdf"
    actual.write_bytes(b"%PDF-1.4")

    found = find_pdf_for_entry(
        ":Smith2023 - Old Title.pdf:PDF", "Smith2023", str(tmp_path)
    )

    assert found == str(actual)


def test_find_pdf_for_entry_tolerates_nfc_nfd_filename_mismatch(
    tmp_path: Path,
) -> None:
    """Regression test for the macOS-only bug report: a PDF whose filename
    contains combining/accented characters can be written to disk in one
    Unicode normal form while the value stored in the .bib file's file field
    is in the other. A byte-exact ``os.path.exists`` check misses the file
    even though it is right there and the table already shows it as linked.
    """
    nfc_name = unicodedata.normalize("NFC", "Müller2023 - Title.pdf")  # ü composed
    nfd_name = unicodedata.normalize("NFD", nfc_name)  # u + combining diaeresis
    assert nfc_name != nfd_name  # sanity: the two byte strings really differ

    # The file is actually saved on disk using the NFD form (as e.g. some
    # macOS sync/cloud-drive clients do)...
    on_disk = tmp_path / nfd_name
    on_disk.write_bytes(b"%PDF-1.4")

    # ...but the .bib file's file field holds the NFC form that bibtui wrote
    # at fetch time (the common form for text parsed out of a UTF-8 .bib).
    found = find_pdf_for_entry(f":{nfc_name}:PDF", "Mueller2023", str(tmp_path))

    assert found is not None
    assert Path(found).read_bytes() == b"%PDF-1.4"


def test_find_pdf_for_entry_nfc_nfd_mismatch_without_matching_entry_key(
    tmp_path: Path,
) -> None:
    """Same as above, but with an entry key that would NOT match the glob
    fallback (e.g. the file field points outside the configured base dir) —
    proving the normalization tolerance itself finds the file, not the
    glob fallback masking it."""
    nfd_name = unicodedata.normalize("NFD", "Müller2023 - Title.pdf")
    nfc_name = unicodedata.normalize("NFC", nfd_name)
    on_disk = tmp_path / nfd_name
    on_disk.write_bytes(b"%PDF-1.4")

    found = find_pdf_for_entry(f":{nfc_name}:PDF", "SomeOtherKey", str(tmp_path))

    assert found is not None


def test_format_jabref_path_stores_relative_filename_inside_base_dir(
    tmp_path: Path,
) -> None:
    dest = tmp_path / "Smith2023 - Title.pdf"
    assert format_jabref_path(str(dest), str(tmp_path)) == ":Smith2023 - Title.pdf:PDF"


def test_format_jabref_path_keeps_absolute_path_outside_base_dir(
    tmp_path: Path,
) -> None:
    other_dir = tmp_path / "elsewhere"
    other_dir.mkdir()
    dest = other_dir / "paper.pdf"
    base_dir = tmp_path / "library"
    result = format_jabref_path(str(dest), str(base_dir))
    assert result == f":{dest}:PDF"
