"""Turn a BibTeX ``author`` field into JabRef-style display names.

BibTeX separates authors with ``and``; the viewer shows them as
``Last, First / Last, First``. Names are shown as written — a name without a
comma (``Meteodrones``, ``Intergovernmental Panel on Climate Change``) may be
an institution, so it is never reordered — but LaTeX escapes are decoded
(``Sch{\\"o}ner`` -> ``Schöner``) and stray whitespace is tidied.
"""

import re
from functools import lru_cache

from bibtui.bib.citation_preview import _decode_latex

AUTHOR_SEPARATOR = " / "

_AND = re.compile(r"\s+and\s+", re.IGNORECASE)
_COMMA = re.compile(r"\s*,\s*")


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
    text = " ".join(_decode_latex(name).split())
    return _COMMA.sub(", ", text)


@lru_cache(maxsize=1024)
def format_authors(raw: str) -> tuple[str, ...]:
    """Display names for a BibTeX author field, in order."""
    return tuple(_display_name(name) for name in split_authors(raw))
