"""Tests for add_pdf() in bibtui.pdf.fetcher."""

from pathlib import Path

import pytest

from bibtui.bib.models import BibEntry
from bibtui.pdf.fetcher import FetchError, add_pdf, find_duplicate_pdf, pdf_filename

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def entry() -> BibEntry:
    return BibEntry(
        key="Smith2023",
        entry_type="article",
        title="Glacial Dynamics in the 21st Century",
    )


@pytest.fixture()
def src_pdf(tmp_path: Path) -> Path:
    """A minimal (empty) PDF file at a temporary source path."""
    p = tmp_path / "source" / "paper.pdf"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"%PDF-1.4 fake")
    return p


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_add_renames_to_canonical_name(
    entry: BibEntry, src_pdf: Path, tmp_path: Path
) -> None:
    dest_dir = tmp_path / "library"
    dest_dir.mkdir()
    dest = add_pdf(src_pdf, entry, str(dest_dir))

    expected_name = pdf_filename(entry)
    assert dest.name == expected_name
    assert dest.exists()
    assert dest.read_bytes() == b"%PDF-1.4 fake"


def test_source_is_removed_after_move(
    entry: BibEntry, src_pdf: Path, tmp_path: Path
) -> None:
    dest_dir = tmp_path / "library"
    dest_dir.mkdir()
    add_pdf(src_pdf, entry, str(dest_dir))
    assert not src_pdf.exists()


def test_dest_dir_created_if_missing(
    entry: BibEntry, src_pdf: Path, tmp_path: Path
) -> None:
    dest_dir = tmp_path / "library" / "nested"
    # Do NOT pre-create dest_dir — add_pdf should mkdir -p it
    dest = add_pdf(src_pdf, entry, str(dest_dir))
    assert dest.exists()


def test_tilde_expansion(entry: BibEntry, tmp_path: Path, monkeypatch) -> None:
    """~ in the source path should be expanded to the home directory."""
    # Redirect HOME so we can place a fake file there
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    src = fake_home / "paper.pdf"
    src.write_bytes(b"%PDF")
    monkeypatch.setenv("HOME", str(fake_home))

    dest_dir = tmp_path / "library"
    dest_dir.mkdir()
    dest = add_pdf(Path("~/paper.pdf"), entry, str(dest_dir))
    assert dest.exists()


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_empty_base_dir_raises(entry: BibEntry, src_pdf: Path) -> None:
    with pytest.raises(FetchError, match="base directory"):
        add_pdf(src_pdf, entry, "")


def test_missing_source_raises(entry: BibEntry, tmp_path: Path) -> None:
    dest_dir = tmp_path / "library"
    dest_dir.mkdir()
    with pytest.raises(FetchError, match="File not found"):
        add_pdf(tmp_path / "nonexistent.pdf", entry, str(dest_dir))


def test_non_pdf_source_raises(entry: BibEntry, tmp_path: Path) -> None:
    src = tmp_path / "paper.docx"
    src.write_bytes(b"not a pdf")
    dest_dir = tmp_path / "library"
    dest_dir.mkdir()
    with pytest.raises(FetchError, match="Not a PDF"):
        add_pdf(src, entry, str(dest_dir))


def test_destination_collision_raises(
    entry: BibEntry, src_pdf: Path, tmp_path: Path
) -> None:
    dest_dir = tmp_path / "library"
    dest_dir.mkdir()
    # Pre-create the canonical destination file
    canonical = dest_dir / pdf_filename(entry)
    canonical.write_bytes(b"%PDF existing")

    with pytest.raises(FetchError, match="Destination already exists"):
        add_pdf(src_pdf, entry, str(dest_dir))


# ---------------------------------------------------------------------------
# Content-based duplicate detection
# ---------------------------------------------------------------------------


def test_reuses_identical_pdf_already_in_base_dir_under_a_different_name(
    entry: BibEntry, src_pdf: Path, tmp_path: Path
) -> None:
    dest_dir = tmp_path / "library"
    dest_dir.mkdir()
    existing = dest_dir / "Old2019 - Some Other Title.pdf"
    existing.write_bytes(src_pdf.read_bytes())  # identical content, unrelated name

    result = add_pdf(src_pdf, entry, str(dest_dir))

    assert result == existing
    assert src_pdf.exists()  # left untouched, not moved
    assert not (dest_dir / pdf_filename(entry)).exists()  # no duplicate copy made


def test_same_size_different_content_is_not_treated_as_duplicate(
    entry: BibEntry, src_pdf: Path, tmp_path: Path
) -> None:
    dest_dir = tmp_path / "library"
    dest_dir.mkdir()
    same_size_different_content = dest_dir / "Unrelated2020 - Different Paper.pdf"
    # Same byte length as src_pdf's "%PDF-1.4 fake" but different content.
    same_size_different_content.write_bytes(b"%PDF-1.4 nope")

    dest = add_pdf(src_pdf, entry, str(dest_dir))

    assert dest.name == pdf_filename(entry)
    assert dest.read_bytes() == b"%PDF-1.4 fake"


def test_source_already_inside_base_dir_is_reused_in_place(
    entry: BibEntry, tmp_path: Path
) -> None:
    dest_dir = tmp_path / "library"
    dest_dir.mkdir()
    already_there = dest_dir / "renamed-by-user.pdf"
    already_there.write_bytes(b"%PDF already here")

    result = add_pdf(already_there, entry, str(dest_dir))

    assert result == already_there
    assert already_there.exists()  # not renamed to the canonical filename
    assert not (dest_dir / pdf_filename(entry)).exists()


def test_find_duplicate_pdf_returns_none_for_missing_base_dir(
    src_pdf: Path, tmp_path: Path
) -> None:
    assert find_duplicate_pdf(src_pdf, str(tmp_path / "does-not-exist")) is None


def test_find_duplicate_pdf_returns_none_when_no_match(
    src_pdf: Path, tmp_path: Path
) -> None:
    dest_dir = tmp_path / "library"
    dest_dir.mkdir()
    (dest_dir / "other.pdf").write_bytes(b"completely different")
    assert find_duplicate_pdf(src_pdf, str(dest_dir)) is None
