"""Offline extraction of a DOI/arXiv identifier from a PDF file.

No network calls here — this module only looks inside the PDF itself.
Validating a found candidate against CrossRef happens in
:mod:`bibtui.pdf.import_scan`, which reuses the existing DOI-import
pipeline (:func:`bibtui.bib.doi.fetch_by_doi`).

Extraction cascade, cheapest/most-authoritative signal first:

1. Embedded document metadata (``/Info`` dictionary values).
2. Text on the first two pages.
3. Regex-match a DOI pattern, falling back to an arXiv id pattern.

A DOI found in metadata always wins over anything found in the body text,
even if the body text also contains DOI-looking strings (e.g. a reference
list starting on page 1) — see ``IdentifyResult``. Multiple distinct DOI
candidates in the body text with none in metadata are reported as
ambiguous rather than guessed at.
"""

import re
from dataclasses import dataclass, field

from pypdf import PdfReader
from pypdf.errors import PdfReadError

# 10.<4-9 digit registrant>/<suffix>, suffix stops at whitespace or a quote/
# angle-bracket (as commonly delimits a DOI in running text or a URL).
_DOI_RE = re.compile(r'10\.\d{4,9}/[^\s"<>]+')

# Trailing characters that are almost always punctuation from the
# surrounding sentence/citation rather than part of the DOI itself.
_DOI_TRAILING_RE = re.compile(r'[).,;:\]}\'"]+$')

_ARXIV_RE = re.compile(
    r"arxiv[:\s]\s*(\d{4}\.\d{4,5})(?:v\d+)?|arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})",
    re.IGNORECASE,
)

_PAGES_TO_SCAN = 2


@dataclass
class IdentifyResult:
    """Result of scanning one PDF for an identifier."""

    doi: str | None = None
    arxiv_id: str | None = None
    ambiguous: bool = False
    candidates: list[str] = field(default_factory=list)
    no_text: bool = False


def _clean_doi(raw: str) -> str:
    return _DOI_TRAILING_RE.sub("", raw)


def _find_dois(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for m in _DOI_RE.finditer(text):
        doi = _clean_doi(m.group(0))
        if doi:
            seen.setdefault(doi, None)
    return list(seen)


def _find_arxiv_id(text: str) -> str | None:
    m = _ARXIV_RE.search(text)
    if not m:
        return None
    return m.group(1) or m.group(2)


def extract_identifier(pdf_path: str) -> IdentifyResult:
    """Look inside *pdf_path* for a DOI or arXiv id.

    Never raises — a corrupt, encrypted, or otherwise unreadable PDF comes
    back as a result with ``no_text=True`` instead of propagating an
    exception, so a single bad file never crashes a batch.
    """
    try:
        reader = PdfReader(pdf_path)
    except (PdfReadError, OSError, ValueError):
        return IdentifyResult(no_text=True)

    # 1. Metadata
    metadata_text = ""
    try:
        if reader.metadata:
            metadata_text = " ".join(
                str(v) for v in reader.metadata.values() if v
            )
    except Exception:  # noqa: BLE001 — malformed /Info dict, keep going
        metadata_text = ""

    metadata_dois = _find_dois(metadata_text)
    if len(metadata_dois) == 1:
        return IdentifyResult(doi=metadata_dois[0])
    if len(metadata_dois) > 1:
        return IdentifyResult(ambiguous=True, candidates=metadata_dois)

    # 2. Body text (first couple of pages)
    body_text = ""
    try:
        pages = reader.pages[:_PAGES_TO_SCAN]
        chunks = []
        for page in pages:
            try:
                chunks.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001 — a single unparsable page
                continue
        body_text = "\n".join(chunks)
    except Exception:  # noqa: BLE001
        body_text = ""

    combined = f"{metadata_text}\n{body_text}"
    if not combined.strip():
        return IdentifyResult(no_text=True)

    body_dois = _find_dois(body_text)
    if len(body_dois) == 1:
        return IdentifyResult(doi=body_dois[0])
    if len(body_dois) > 1:
        return IdentifyResult(ambiguous=True, candidates=body_dois)

    # 3. arXiv id fallback (only reached when no DOI was found anywhere)
    arxiv_id = _find_arxiv_id(combined)
    if arxiv_id:
        return IdentifyResult(arxiv_id=arxiv_id)

    # We got here with non-empty combined text (checked above) but no
    # identifier in it — a real "not found", not a missing-text case.
    return IdentifyResult()
