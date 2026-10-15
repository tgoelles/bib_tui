"""Per-file orchestration for PDF → BibTeX import.

Combines the offline extraction cascade in :mod:`bibtui.pdf.identify` with
an online metadata lookup — CrossRef for a DOI
(:func:`bibtui.bib.doi.fetch_by_doi`), the arXiv API for an arXiv id
(:func:`bibtui.bib.arxiv.fetch_by_arxiv_id`), Open Library for an ISBN
(:func:`bibtui.bib.isbn.fetch_by_isbn`) — and duplicate detection against
the entries already in the open library.
"""

import os
import time
from dataclasses import dataclass, field
from enum import StrEnum

from collections.abc import Callable

from bibtui.bib.arxiv import ARXIV_DOI_PREFIX, fetch_by_arxiv_id
from bibtui.bib.doi import fetch_by_doi
from bibtui.bib.isbn import fetch_by_isbn
from bibtui.bib.models import BibEntry
from bibtui.pdf.identify import extract_identifier
from bibtui.utils.doi import normalize_doi
from bibtui.utils.isbn import normalize_isbn

# Brief pause before retrying a failed metadata lookup once.
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


def isbn_key(isbn: str) -> str:
    return f"isbn:{isbn}"


def entry_identity_keys(entry: BibEntry) -> list[str]:
    """Keys under which *entry* is found by PDF import's duplicate checks.

    The normalized DOI; for an arXiv preprint stored by ``eprint`` alone,
    the normalized arXiv DOI it would be imported under; and ``isbn:<ISBN-13>``
    for a book. Used both for the library-wide lookup dict and for
    ``seen_in_batch``.
    """
    keys: list[str] = []
    if entry.doi.strip():
        keys.append(normalize_doi(entry.doi))
    eprint = entry.get_field("eprint").strip()
    archive = (
        (entry.get_field("archiveprefix") or entry.get_field("eprinttype"))
        .strip()
        .lower()
    )
    if eprint and archive == "arxiv":
        arxiv_doi = normalize_doi(f"{ARXIV_DOI_PREFIX}{eprint}")
        if arxiv_doi not in keys:
            keys.append(arxiv_doi)
    isbn = normalize_isbn(entry.get_field("isbn"))
    if isbn:
        keys.append(isbn_key(isbn))
    return keys


def _lookup_plan(result) -> list[tuple[str, str, str, Callable[[], BibEntry]]]:
    """``(identity key, label, source, fetch)`` per identifier to try, in order.

    A book's several ISBNs are all tried until one resolves.
    """
    if result.doi:
        doi = result.doi
        return [(normalize_doi(doi), doi, "CrossRef", lambda: fetch_by_doi(doi))]
    if result.arxiv_id:
        arxiv_id = result.arxiv_id
        return [
            (
                normalize_doi(f"{ARXIV_DOI_PREFIX}{arxiv_id}"),
                f"arXiv:{arxiv_id}",
                "arXiv",
                lambda: fetch_by_arxiv_id(arxiv_id),
            )
        ]
    return [
        (
            isbn_key(isbn),
            f"ISBN {isbn}",
            "Open Library",
            lambda i=isbn: fetch_by_isbn(i),
        )
        for isbn in result.isbns
    ]


def process_pdf(
    path: str,
    existing_by_doi: dict[str, BibEntry],
    seen_in_batch: set[str],
) -> ImportRow:
    """Identify and fetch metadata for the PDF at *path*.

    *existing_by_doi* maps identity keys (see :func:`entry_identity_keys` —
    normalized DOI, or ``isbn:<ISBN-13>`` for a book) to the matching entry
    already in the open library (same object references — a ``LINK_EXISTING``
    result hands one of these back to be linked in place, not copied).
    *seen_in_batch* holds identity keys already resolved earlier in this same
    scan; the caller is expected to add a ``MATCHED``/``LINK_EXISTING``
    result's keys to it before processing the next file, so duplicate PDFs
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

        plan = _lookup_plan(result)
        if not plan:
            if result.unreadable:
                message = "Could not read this PDF (corrupt, encrypted, or not a PDF?)."
            elif result.no_text:
                message = "No extractable text (scanned PDF?)"
            else:
                message = "No DOI, arXiv id, or ISBN found."
            return ImportRow(
                path, filename, ImportStatus.NO_IDENTIFIER, message=message
            )

        for key, label, _source, _fetch in plan:
            if key in seen_in_batch:
                return ImportRow(
                    path,
                    filename,
                    ImportStatus.ALREADY_PRESENT,
                    message=f"Duplicate of another PDF in this import ({label}).",
                )

            existing_entry = existing_by_doi.get(key)
            if existing_entry is None:
                continue
            if (existing_entry.file or "").strip():
                return ImportRow(
                    path,
                    filename,
                    ImportStatus.ALREADY_PRESENT,
                    message=f"Already in library with a PDF linked ({label}).",
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

        failures: list[str] = []
        for _key, label, source, fetch in plan:
            last_error = ""
            for attempt in range(2):
                if attempt:
                    time.sleep(_RETRY_DELAY_SECONDS)
                try:
                    entry = fetch()
                    return ImportRow(path, filename, ImportStatus.MATCHED, entry=entry)
                except LookupError as exc:
                    # A definite "no such record" — retrying won't help.
                    last_error = str(exc)
                    break
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)
            failures.append(f"{source} lookup failed for {label}: {last_error}")

        return ImportRow(
            path,
            filename,
            ImportStatus.LOOKUP_FAILED,
            message="; ".join(failures),
        )
    except Exception as exc:  # noqa: BLE001 — never let one bad file crash a batch
        return ImportRow(
            path,
            filename,
            ImportStatus.LOOKUP_FAILED,
            message=f"Unexpected error: {exc}",
        )
