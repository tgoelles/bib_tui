"""LaTeX-to-Unicode decoding for display (``Sch{\\"o}ner`` -> ``Schöner``).

A leaf module (imports nothing from the rest of bibtui) so both the data model
and the rendering code can use it without import cycles.

bibtexparser ships :class:`~bibtexparser.middlewares.LatexDecodingMiddleware`
for this, but it builds its decoder for bibliographic *fields* — short, mostly
prose values. Abstracts are neither: a quarter of them in a working library
carry maths and spacing macros, and the stock decoder mangles two common cases
badly enough to change the meaning, so the decoder is configured here instead.
See ``_EXTRA_MACROS`` for what those cases are.
"""

from functools import lru_cache

from pylatexenc.latex2text import (  # type: ignore[import-untyped]
    LatexNodes2Text,
    MacroTextSpec,
    get_default_latex_context_db,
)

_EXTRA_MACROS = [
    # Without these two the decoded text is wrong rather than merely plainer:
    # `\ensuremath{\mu}g` would come out as `g` (a factor of a million in a
    # unit) and `12\hspace{0.167em}years` as `12years`.
    MacroTextSpec("ensuremath", simplify_repl="%s"),
    MacroTextSpec("hspace", simplify_repl=" "),
    MacroTextSpec("vspace", simplify_repl=" "),
    MacroTextSpec("mbox", simplify_repl="%s"),
    # As bibtexparser does: don't wrap URLs in '< ... >'.
    MacroTextSpec("url", simplify_repl="%s"),
]


def _build_decoder() -> LatexNodes2Text:
    context = get_default_latex_context_db()
    context.add_context_category("bibtui", prepend=True, macros=_EXTRA_MACROS)
    # math_mode="text" turns `$\pm$` into `±` and `$\mu$` into `μ`; the default
    # leaves the raw macros sitting in the text.
    return LatexNodes2Text(latex_context=context, math_mode="text")


_DECODER = _build_decoder()


@lru_cache(maxsize=4096)
def decode_latex(value: str) -> str:
    if not value:
        return ""
    try:
        text = _DECODER.latex_to_text(value)
    except Exception:
        return value
    # `^{\circ}` decodes to a superscript ring operator; in a bibliography it
    # is always a degree sign (`1.8^∘C`, `70^∘ N`), which reads much better as
    # `1.8°C` — and costs two fewer columns in a narrow pane.
    return text.replace("^∘", "°")
