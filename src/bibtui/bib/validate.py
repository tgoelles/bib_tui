"""Submit-time validation for the new/edit entry form.

Pure and UI-independent so it can be unit-tested without Textual. Driven by the
same :data:`bibtui.bib.models.ENTRY_TYPES` table that builds the form, so there
is a single source of truth for which fields each entry type requires.

Three tiers of feedback (see :class:`ValidationResult`):

* ``applied_fixes`` — normalizations applied automatically (pages, DOI, escaping)
* ``warnings``      — surfaced but never block the write
* ``blocking_errors`` — must be resolved before the entry can be written

Nothing here ever runs on file load; messy existing libraries always open.
"""

import copy
import re
from dataclasses import dataclass, field
from datetime import datetime

from .models import ENTRY_TYPES, BibEntry
from .parser import is_serializable_entry

# Free-text fields where bare LaTeX specials should be escaped. Deliberately
# excludes doi/url/eprint/file and numeric fields, which must stay verbatim.
_TEXT_FIELDS: frozenset[str] = frozenset(
    {
        "title",
        "author",
        "journal",
        "abstract",
        "comment",
        "booktitle",
        "publisher",
        "series",
        "note",
        "editor",
        "organization",
        "institution",
        "school",
        "address",
        "howpublished",
        "annote",
        "type",
    }
)

# Only these three are escaped. $ _ \ { } are left alone because they are so
# often intentional LaTeX/math, and Unicode letters are left as-is for biblatex.
_BARE_SPECIAL_RE = re.compile(r"(?<!\\)([&%#])")

_SIMPLE_PAGE_RANGE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")

_DOI_URL_PREFIX_RE = re.compile(
    r"^\s*(?:https?://(?:dx\.)?doi\.org/|doi:)\s*", re.IGNORECASE
)

# Plausible publication-year bounds (upper bound is resolved at call time).
_MIN_PLAUSIBLE_YEAR = 1450


@dataclass
class ValidationResult:
    """Outcome of validating a single entry.

    ``entry`` always holds the normalized entry (with any auto-fixes applied);
    callers write it only when ``blocking_errors`` is empty.
    """

    entry: BibEntry
    applied_fixes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blocking_errors: list[dict] = field(default_factory=list)

    @property
    def is_writable(self) -> bool:
        return not self.blocking_errors


def _escape_bare_specials(value: str) -> str:
    return _BARE_SPECIAL_RE.sub(r"\\\1", value)


def _normalize_pages(value: str) -> str:
    match = _SIMPLE_PAGE_RANGE_RE.match(value)
    if match:
        return f"{match.group(1)}--{match.group(2)}"
    return value


def _normalize_doi(value: str) -> str:
    return _DOI_URL_PREFIX_RE.sub("", value).strip()


def _apply_fixes(entry: BibEntry, fixes: list[str]) -> None:
    """Mutate *entry* in place with auto-fixes, recording each in *fixes*."""

    def record(name: str, old: str, new: str) -> None:
        if new != old:
            entry.set_field(name, new)
            fixes.append(f"{name}: {old} → {new}")

    pages = entry.get_field("pages")
    if pages:
        record("pages", pages, _normalize_pages(pages))

    doi = entry.get_field("doi")
    if doi:
        record("doi", doi, _normalize_doi(doi))

    for name in _TEXT_FIELDS:
        current = entry.get_field(name)
        if current:
            record(name, current, _escape_bare_specials(current))


def _required_is_blocking(
    name: str, mode: str, baseline: BibEntry | None
) -> bool:
    """Return True if an empty required *name* should block rather than warn.

    A missing required field blocks for new entries, or for edits only when the
    field previously had a value (i.e. the user just cleared it) — never for a
    gap that already existed in the entry being edited.
    """
    if mode == "new":
        return True
    return bool(baseline and baseline.get_field(name).strip())


def validate_entry(
    entry: BibEntry,
    *,
    mode: str = "new",
    baseline: BibEntry | None = None,
) -> ValidationResult:
    """Validate *entry*, returning a normalized copy plus fixes/warnings/errors.

    ``mode`` is ``"new"`` or ``"edit"``. In edit mode, *baseline* is the entry
    as it was before editing; missing required fields that were already empty in
    the baseline are downgraded to warnings so editing a messy entry is never
    blocked ("you can't make it worse").
    """
    normalized = copy.deepcopy(entry)
    fixes: list[str] = []
    warnings: list[str] = []
    blocking: list[dict] = []

    _apply_fixes(normalized, fixes)

    # Cite key must always be present and usable.
    key = (normalized.key or "").strip()
    if not key:
        blocking.append({"field": "key", "message": "Cite key is required."})
    elif any(ch.isspace() for ch in key):
        blocking.append(
            {"field": "key", "message": "Cite key cannot contain spaces."}
        )

    spec = ENTRY_TYPES.get(normalized.entry_type, {})
    required = spec.get("required", [])

    for name in required:
        if normalized.get_field(name).strip():
            continue
        message = f"{name.capitalize()} is required for @{normalized.entry_type}."
        if _required_is_blocking(name, mode, baseline):
            blocking.append({"field": name, "message": message})
        else:
            warnings.append(f"{name} is missing (was already empty).")

    # Year plausibility: numeric-but-implausible is only ever a warning; a
    # non-numeric year is treated with the same severity as a required field.
    year_raw = normalized.get_field("year").strip()
    if year_raw:
        if year_raw.isdigit():
            year = int(year_raw)
            upper = datetime.now().year + 1
            if year < _MIN_PLAUSIBLE_YEAR or year > upper:
                warnings.append(
                    f"Year {year} looks implausible "
                    f"(expected {_MIN_PLAUSIBLE_YEAR}–{upper})."
                )
        elif "year" in required and _required_is_blocking("year", mode, baseline):
            blocking.append(
                {"field": "year", "message": "Year must be a number."}
            )
        else:
            warnings.append(f"Year '{year_raw}' is not a number.")

    # Final structural gate: reject anything bibtexparser can't round-trip.
    if not blocking and not is_serializable_entry(normalized):
        blocking.append(
            {
                "field": "key",
                "message": (
                    "Not valid BibTeX — check the cite key and field values "
                    "for unbalanced { } braces."
                ),
            }
        )

    return ValidationResult(
        entry=normalized,
        applied_fixes=fixes,
        warnings=warnings,
        blocking_errors=blocking,
    )
