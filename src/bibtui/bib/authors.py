"""Turn a BibTeX ``author`` field into JabRef-style display names.

BibTeX separates authors with ``and``; the viewer shows them as
``Last, First / Last, First``. Names are shown as written — a name without a
comma (``Meteodrones``, ``Intergovernmental Panel on Climate Change``) may be
an institution, so it is never reordered — but LaTeX escapes are decoded
(``Sch{\\"o}ner`` -> ``Schöner``) and stray whitespace is tidied.
"""

import re
from functools import lru_cache

from bibtui.bib.latex import decode_latex

AUTHOR_SEPARATOR = " / "

_AND = re.compile(r"\s+and\s+", re.IGNORECASE)
_COMMA = re.compile(r"\s*,\s*")
# Only names containing these can need LaTeX decoding — skipping the decoder for
# the rest keeps building a whole table of surnames cheap.
_LATEX_CHARS = re.compile(r"[\\{}~]")


def split_authors(raw: str) -> list[str]:
    """Split a BibTeX author field on top-level ``and`` (any case).

    An ``and`` inside braces is part of a name, e.g. ``{Barnes and Noble}``.
    """
    names: list[str] = []
    depth = 0
    start = 0
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        elif depth == 0 and ch.isspace():
            match = _AND.match(raw, i)
            if match:
                names.append(raw[start:i])
                start = i = match.end()
                continue
        i += 1
    names.append(raw[start:])
    return [name.strip() for name in names if name.strip()]


def _display_name(name: str) -> str:
    if name.lower() == "others":
        return "et al."
    if _LATEX_CHARS.search(name):
        name = decode_latex(name)
    return _COMMA.sub(", ", " ".join(name.split()))


@lru_cache(maxsize=1024)
def format_authors(raw: str) -> tuple[str, ...]:
    """Display names for a BibTeX author field, in order."""
    return tuple(_display_name(name) for name in split_authors(raw))


@lru_cache(maxsize=4096)
def first_surname(raw: str) -> str:
    """Surname of the first author (``""`` when there is none), decoded."""
    names = split_authors(raw)
    if not names:
        return ""
    first = _display_name(names[0])
    if first == "et al.":
        return ""
    if "," in first:
        return first.split(",")[0].strip()
    words = first.split()
    return words[-1] if words else first
