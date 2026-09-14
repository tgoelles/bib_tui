"""Per-file orchestration for PDF → BibTeX import.

Combines the offline extraction cascade in :mod:`bibtui.pdf.identify` with
the existing CrossRef pipeline (:func:`bibtui.bib.doi.fetch_by_doi`) and
duplicate detection against the entries already in the open library.
"""

import os
import time
from dataclasses import dataclass, field
from enum import StrEnum

from bibtui.bib.doi import fetch_by_doi
from bibtui.bib.models import BibEntry
from bibtui.pdf.identify import extract_identifier
from bibtui.utils.doi import normalize_doi

# arXiv has registered a Crossref DOI (10.48550/arXiv.<id>) for every
# submission since 2022, so an arXiv id found in the PDF is looked up
# through the same CrossRef pipeline as a real DOI rather than a second,
# arXiv-specific metadata source. Older preprints without a registered DOI
# will simply fail this lookup and be reported as NO_IDENTIFIER/
# LOOKUP_FAILED — a known v1 limitation.
_ARXIV_DOI_PREFIX = "10.48550/arXiv."

# Brief pause before retrying a failed CrossRef lookup once.
_RETRY_DELAY_SECONDS = 0.3


class ImportStatus(StrEnum):
    MATCHED = "matched"
    LINK_EXISTING = "link_existing"
    ALREADY_PRESENT = "already_present"
    AMBIGUOUS = "ambiguous"
    NO_IDENTIFIER = "no_identifier"
    LOOKUP_FAILED = "lookup_failed"


@dataclass
class ImportRow:
    path: str
    filename: str
    status: ImportStatus
    entry: BibEntry | None = None
    message: str = ""
    candidates: list[str] = field(default_factory=list)


def _candidate_doi(result) -> str | None:
    if result.doi:
        return result.doi
    if result.arxiv_id:
        return f"{_ARXIV_DOI_PREFIX}{result.arxiv_id}"
    return None


def process_pdf(
    path: str,
    existing_by_doi: dict[str, BibEntry],
    seen_in_batch: set[str],
) -> ImportRow:
    """Identify and fetch metadata for the PDF at *path*.

    *existing_by_doi* maps normalized DOI to the matching entry already in
    the open library (same object references — a ``LINK_EXISTING`` result
    hands one of these back to be linked in place, not copied). *seen_in_batch*
    holds normalized DOIs already resolved earlier in this same scan; the
    caller is expected to add a ``MATCHED``/``LINK_EXISTING`` result's
    normalized DOI to it before processing the next file, so duplicate PDFs
    within one selection are also caught.
    """
    filename = os.path.basename(path)

    try:
        result = extract_identifier(path)

        if result.ambiguous:
            return ImportRow(
                path,
                filename,
                ImportStatus.AMBIGUOUS,
                message="Multiple possible DOIs found in the text.",
                candidates=result.candidates,
            )

        doi = _candidate_doi(result)
        if not doi:
            message = (
                "No extractable text (scanned PDF?)"
                if result.no_text
                else "No DOI or arXiv id found."
            )
            return ImportRow(path, filename, ImportStatus.NO_IDENTIFIER, message=message)

        normalized = normalize_doi(doi)
        if normalized in seen_in_batch:
            return ImportRow(
                path,
                filename,
                ImportStatus.ALREADY_PRESENT,
                message=f"Duplicate of another PDF in this import ({doi}).",
            )

        existing_entry = existing_by_doi.get(normalized)
        if existing_entry is not None:
            if (existing_entry.file or "").strip():
                return ImportRow(
                    path,
                    filename,
                    ImportStatus.ALREADY_PRESENT,
                    message=f"Already in library with a PDF linked ({doi}).",
                )
            return ImportRow(
                path,
                filename,
                ImportStatus.LINK_EXISTING,
                entry=existing_entry,
                message=(
                    f"Matches existing entry '{existing_entry.key}' "
                    "(no PDF linked yet)."
                ),
            )

        last_error = ""
        for attempt in range(2):
            if attempt:
                time.sleep(_RETRY_DELAY_SECONDS)
            try:
                entry = fetch_by_doi(doi)
                return ImportRow(path, filename, ImportStatus.MATCHED, entry=entry)
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)

        return ImportRow(
            path,
            filename,
            ImportStatus.LOOKUP_FAILED,
            message=f"CrossRef lookup failed for {doi}: {last_error}",
        )
    except Exception as exc:  # noqa: BLE001 — never let one bad file crash a batch
        return ImportRow(
            path, filename, ImportStatus.LOOKUP_FAILED, message=f"Unexpected error: {exc}"
        )
