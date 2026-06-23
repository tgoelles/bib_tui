from __future__ import annotations

import re
from pathlib import Path

from bibtexparser.middlewares import LatexDecodingMiddleware
from citeproc import (  # type: ignore[import-untyped]
    Citation,
    CitationItem,
    CitationStylesBibliography,
    CitationStylesStyle,
    formatter,
)
from citeproc.model import FormatNumber  # type: ignore[import-untyped]
from citeproc.source.json import CiteProcJSON  # type: ignore[import-untyped]

from bibtui.bib.models import BibEntry
from bibtui.utils.config import csl_dir, ensure_csl_styles

_DEFAULT_STYLE = "copernicus-publications"


# citeproc-py's page-range collapsing only understands page-range-format="chicago".
# Newer CSL styles (e.g. Chicago Manual of Style 18th ed.) declare "chicago-16" /
# "chicago-15", which leaves `index` unassigned in FormatNumber._format_last_page and
# raises UnboundLocalError for any entry with a page range. Fall back to the full last
# page (expanded range) for unknown variants instead of failing the whole citation.
_orig_format_last_page = FormatNumber._format_last_page


def _safe_format_last_page(self, first, last):  # type: ignore[no-untyped-def]
    try:
        return _orig_format_last_page(self, first, last)
    except UnboundLocalError:
        return last


FormatNumber._format_last_page = _safe_format_last_page


_LATEX_DECODER = LatexDecodingMiddleware(allow_inplace_modification=False)


def _decode_latex(value: str) -> str:
    if not value:
        return ""
    try:
        return _LATEX_DECODER._decoder.latex_to_text(value)
    except Exception:
        return value


def _configured_csl_dir() -> Path:
    ensure_csl_styles()
    return csl_dir()


def available_csl_styles() -> list[tuple[str, str]]:
    """Return available local CSL styles as (label, key) tuples."""
    style_dir = _configured_csl_dir()
    if not style_dir.exists():
        return []
    styles: list[tuple[str, str]] = []
    for p in sorted(style_dir.glob("*.csl")):
        key = p.stem
        label = key.replace("-", " ").title()
        styles.append((label, key))
    return styles


def default_csl_style_key() -> str:
    """Return default CSL style key, falling back to first available."""
    keys = [key for _label, key in available_csl_styles()]
    if _DEFAULT_STYLE in keys:
        return _DEFAULT_STYLE
    return keys[0] if keys else _DEFAULT_STYLE


def csl_style_path(style_key: str) -> Path:
    """Resolve style key to local CSL path."""
    return _configured_csl_dir() / f"{style_key}.csl"


def _split_authors(author_field: str) -> list[dict[str, str]]:
    names: list[dict[str, str]] = []
    for raw_name in [n.strip() for n in author_field.split(" and ") if n.strip()]:
        if "," in raw_name:
            family, given = [p.strip() for p in raw_name.split(",", 1)]
            item: dict[str, str] = {"family": family}
            if given:
                item["given"] = given
            names.append(item)
            continue

        parts = raw_name.split()
        if not parts:
            continue
        if len(parts) == 1:
            names.append({"family": parts[0]})
            continue
        names.append({"family": parts[-1], "given": " ".join(parts[:-1])})
    return names


def _entry_type_to_csl(entry_type: str) -> str:
    mapping = {
        "article": "article-journal",
        "book": "book",
        "inproceedings": "paper-conference",
        "incollection": "chapter",
        "phdthesis": "thesis",
        "mastersthesis": "thesis",
        "techreport": "report",
        "misc": "article",
    }
    return mapping.get(entry_type.lower(), "article")


def _year_to_issued(year: str) -> dict[str, list[list[int]]] | None:
    m = re.search(r"\d{4}", year or "")
    if not m:
        return None
    return {"date-parts": [[int(m.group(0))]]}


def _entry_to_csl_item(entry: BibEntry) -> dict:
    item: dict = {
        "id": (entry.key or "entry").lower(),
        "type": _entry_type_to_csl(entry.entry_type),
    }

    if entry.title:
        item["title"] = _decode_latex(entry.title)

    if entry.author:
        authors = _split_authors(_decode_latex(entry.author))
        if authors:
            item["author"] = authors

    issued = _year_to_issued(entry.year)
    if issued:
        item["issued"] = issued

    container = _decode_latex(entry.journal or entry.raw_fields.get("booktitle", ""))
    if container:
        item["container-title"] = container

    if entry.doi:
        item["DOI"] = entry.doi
    if entry.url:
        item["URL"] = entry.url

    # Optional common fields from raw metadata.
    if entry.raw_fields.get("volume"):
        item["volume"] = _decode_latex(entry.raw_fields["volume"])
    if entry.raw_fields.get("number"):
        item["issue"] = _decode_latex(entry.raw_fields["number"])
    if entry.raw_fields.get("pages"):
        item["page"] = _decode_latex(entry.raw_fields["pages"])
    if entry.raw_fields.get("publisher"):
        item["publisher"] = _decode_latex(entry.raw_fields["publisher"])

    return item


def render_citation_preview(entry: BibEntry, style_key: str) -> str:
    """Render a one-item bibliography entry for *entry* using local CSL style."""
    style_path = csl_style_path(style_key)
    if not style_path.exists():
        return ""

    try:
        item = _entry_to_csl_item(entry)
        source = CiteProcJSON([item])
        style = CitationStylesStyle(str(style_path), validate=False)
        bibliography = CitationStylesBibliography(style, source, formatter.plain)
        bibliography.register(Citation([CitationItem(item["id"])]))
        rendered = str(bibliography.bibliography()[0]).strip()
        return rendered
    except Exception:
        return ""
