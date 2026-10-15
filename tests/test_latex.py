"""LaTeX-to-Unicode decoding used for authors, titles and abstracts."""

import pytest

from bibtui.bib.latex import decode_latex


def test_accents_are_decoded() -> None:
    assert decode_latex(r"Sch{\"o}ner") == "Sch\u00f6ner"


def test_empty_input() -> None:
    assert decode_latex("") == ""


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Maths: the stock field decoder leaves these as raw macros.
        (r"0.5 $\pm$ 0.3", "0.5 \u00b1 0.3"),
        (r"$\sim$5 $\mu$m", "\u223c5 \u03bcm"),
        # \ensuremath used to swallow its argument: `\mu g` became `g`, which
        # is a factor of a million in a unit.
        (r"\ensuremath{\mu}g C", "\u03bcg C"),
        # \hspace used to vanish, gluing the words either side together.
        (r"12\hspace{0.167em}years", "12 years"),
        (r"\mbox{CO2} rose 11\%", "CO2 rose 11%"),
        # Degrees read better than a superscript ring operator.
        (r"1.8$^{\circ}$C", "1.8\u00b0C"),
        (r"70$^\circ$ N", "70\u00b0 N"),
        # Ranges.
        ("1983--2014", "1983\u20132014"),
        (r"41 \$/tCO2", "41 $/tCO2"),
    ],
)
def test_common_abstract_latex(raw: str, expected: str) -> None:
    assert decode_latex(raw) == expected


def test_malformed_latex_falls_back_to_the_raw_value() -> None:
    value = "unbalanced {group and $math"
    assert isinstance(decode_latex(value), str)


def test_repeated_calls_are_cached() -> None:
    decode_latex.cache_clear()
    text = r"0.5 $\pm$ 0.3 \ensuremath{\mu}g"
    decode_latex(text)
    decode_latex(text)
    assert decode_latex.cache_info().hits >= 1
