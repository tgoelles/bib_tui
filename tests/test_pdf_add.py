"""Tests for add_pdf() in bib_tui.bib.pdf_fetcher."""

from pathlib import Path

import pytest

from bib_tui.bib.models import BibEntry
from bib_tui.bib.pdf_fetcher import FetchError, add_pdf, pdf_filename


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
