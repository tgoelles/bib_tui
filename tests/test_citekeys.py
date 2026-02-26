from bibtui.bib.citekeys import (
    author_year_base,
    canonicalize_author_year_key,
    is_author_year_key,
    is_canonical_author_year_key,
    make_unique_key,
)


def test_author_year_base_strips_latex_braces_and_accents() -> None:
    author = r"{G{\"o}lles}, Thomas and Someone, Else"
    assert author_year_base(author, "2025") == "Goelles2025"


def test_author_year_base_handles_apostrophe_and_hyphen() -> None:
    author = "O'Neil-Smith, Jane"
    assert author_year_base(author, "2024") == "ONeilSmith2024"


def test_author_year_base_handles_caron_macro() -> None:
    author = r"Mo{\v{c}}nik, Bor"
    assert author_year_base(author, "2023") == "Mocnik2023"


def test_author_year_base_falls_back_when_year_missing() -> None:
    assert author_year_base("Smith, John", "n/a") == "Smith0000"


def test_is_author_year_key_accepts_optional_suffix() -> None:
    assert is_author_year_key("Goelles2025")
    assert is_author_year_key("Goelles2025a")
    assert not is_author_year_key("goelles2025")
    assert not is_author_year_key("Goelles25")


def test_make_unique_key_adds_letter_suffixes() -> None:
    used = {"Goelles2025", "Goelles2025a"}
    assert make_unique_key("Goelles2025", used) == "Goelles2025b"


def test_canonicalize_author_year_key_normalizes_case() -> None:
    assert canonicalize_author_year_key("STEINIGER2021") == "Steiniger2021"
    assert canonicalize_author_year_key("steiniger2021a") == "Steiniger2021a"
    assert canonicalize_author_year_key("IRVINE-FYNN2025") == "Irvine-Fynn2025"


def test_is_canonical_author_year_key() -> None:
    assert is_canonical_author_year_key("Melcher2014")
    assert is_canonical_author_year_key("Irvine-Fynn2025")
    assert not is_canonical_author_year_key("MELCHER2014")
    assert not is_canonical_author_year_key("Irvine-fynn2025")
