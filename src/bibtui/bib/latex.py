"""LaTeX-to-Unicode decoding for display (``Sch{\\"o}ner`` -> ``Schöner``).

A leaf module (imports nothing from the rest of bibtui) so both the data model
and the rendering code can use it without import cycles.
"""

from bibtexparser.middlewares import LatexDecodingMiddleware

_LATEX_DECODER = LatexDecodingMiddleware(allow_inplace_modification=False)


def decode_latex(value: str) -> str:
    if not value:
        return ""
    try:
        return _LATEX_DECODER._decoder.latex_to_text(value)
    except Exception:
        return value
