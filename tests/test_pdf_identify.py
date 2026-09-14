"""Tests for the offline extraction cascade in bibtui.pdf.identify.

No network access — fixtures are minimal hand-built PDFs (a handful of
text-showing operators on one page, written directly as PDF bytes) so the
tests don't need a binary fixture file or an extra dependency.
"""

from pathlib import Path

import pytest

from bibtui.pdf.identify import extract_identifier

# ---------------------------------------------------------------------------
# Minimal PDF builder
# ---------------------------------------------------------------------------


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _make_pdf(lines: list[str], info: dict[str, str] | None = None) -> bytes:
    """Build a minimal, valid single-page PDF with the given text lines."""
    objs: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 612 792] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    content_lines = []
    y = 712
    for line in lines:
        content_lines.append(f"BT /F1 12 Tf 72 {y} Td ({_escape(line)}) Tj ET".encode())
        y -= 20
    content = b"\n".join(content_lines)
    objs.append(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")

    info_obj = None
    if info:
        parts = " ".join(f"/{k} ({_escape(v)})" for k, v in info.items())
        info_obj = f"<< {parts} >>".encode()
        objs.append(info_obj)

    buf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objs, start=1):
        offsets.append(len(buf))
        buf += f"{i} 0 obj\n".encode()
        buf += obj
        buf += b"\nendobj\n"

    xref_offset = len(buf)
    n = len(objs) + 1
    buf += f"xref\n0 {n}\n".encode()
    buf += b"0000000000 65535 f \n"
    for off in offsets:
        buf += f"{off:010d} 00000 n \n".encode()

    trailer_extra = f" /Info {len(objs)} 0 R" if info_obj else ""
    buf += f"trailer\n<< /Size {n} /Root 1 0 R{trailer_extra} >>\n".encode()
    buf += f"startxref\n{xref_offset}\n%%EOF".encode()
    return bytes(buf)


def _write_pdf(tmp_path: Path, name: str, lines: list[str], info=None) -> str:
    path = tmp_path / name
    path.write_bytes(_make_pdf(lines, info))
    return str(path)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_doi_found_in_body_text(tmp_path: Path) -> None:
    path = _write_pdf(
        tmp_path, "body.pdf", ["A Paper About Ice", "doi: 10.1234/abcd.5678"]
    )
    result = extract_identifier(path)
    assert result.doi == "10.1234/abcd.5678"
    assert not result.ambiguous
    assert not result.no_text


def test_metadata_doi_wins_over_body_text_doi(tmp_path: Path) -> None:
    path = _write_pdf(
        tmp_path,
        "meta.pdf",
        ["References", "See also 10.9999/other-paper"],
        info={"Subject": "doi:10.1111/from-metadata"},
    )
    result = extract_identifier(path)
    assert result.doi == "10.1111/from-metadata"


def test_arxiv_id_found_when_no_doi_present(tmp_path: Path) -> None:
    path = _write_pdf(tmp_path, "arxiv.pdf", ["arXiv:2301.12345", "Some abstract text"])
    result = extract_identifier(path)
    assert result.doi is None
    assert result.arxiv_id == "2301.12345"
    assert not result.ambiguous


def test_multiple_distinct_dois_in_text_are_ambiguous(tmp_path: Path) -> None:
    path = _write_pdf(
        tmp_path,
        "ambiguous.pdf",
        ["10.1111/first-candidate", "10.2222/second-candidate"],
    )
    result = extract_identifier(path)
    assert result.doi is None
    assert result.ambiguous
    assert set(result.candidates) == {"10.1111/first-candidate", "10.2222/second-candidate"}


def test_repeated_doi_in_text_is_not_ambiguous(tmp_path: Path) -> None:
    path = _write_pdf(
        tmp_path,
        "repeated.pdf",
        ["10.3333/same-doi appears here", "and again: 10.3333/same-doi"],
    )
    result = extract_identifier(path)
    assert result.doi == "10.3333/same-doi"
    assert not result.ambiguous


def test_doi_trailing_punctuation_is_stripped(tmp_path: Path) -> None:
    path = _write_pdf(tmp_path, "punct.pdf", ["See (10.4444/paren-wrapped)."])
    result = extract_identifier(path)
    assert result.doi == "10.4444/paren-wrapped"


def test_page_with_no_text_reports_no_text(tmp_path: Path) -> None:
    path = _write_pdf(tmp_path, "blank.pdf", [])
    result = extract_identifier(path)
    assert result.doi is None
    assert result.arxiv_id is None
    assert result.no_text


def test_text_present_but_no_identifier_is_not_no_text(tmp_path: Path) -> None:
    path = _write_pdf(tmp_path, "no_id.pdf", ["Just an abstract with no identifiers."])
    result = extract_identifier(path)
    assert result.doi is None
    assert result.arxiv_id is None
    assert not result.no_text


def test_corrupt_pdf_does_not_raise(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.pdf"
    path.write_bytes(b"not actually a pdf")
    result = extract_identifier(str(path))
    assert result.doi is None
    assert result.no_text


def test_missing_file_does_not_raise(tmp_path: Path) -> None:
    result = extract_identifier(str(tmp_path / "does-not-exist.pdf"))
    assert result.doi is None
    assert result.no_text


@pytest.mark.parametrize(
    "value",
    [
        "10.1234/abcd.5678",
        "10.1000/xyz123",
    ],
)
def test_various_valid_dois_are_matched(tmp_path: Path, value: str) -> None:
    path = _write_pdf(tmp_path, "valid.pdf", [f"identifier {value} end"])
    result = extract_identifier(path)
    assert result.doi == value
