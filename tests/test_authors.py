"""JabRef-style author formatting."""

from bibtui.bib.authors import AUTHOR_SEPARATOR, format_authors, split_authors


def test_split_on_and() -> None:
    assert split_authors("Smith, Jane and Doe, John") == ["Smith, Jane", "Doe, John"]


def test_split_is_case_insensitive_and_tolerates_whitespace() -> None:
    assert split_authors("A, B  AND\n C, D And E, F") == ["A, B", "C, D", "E, F"]


def test_and_inside_braces_is_part_of_the_name() -> None:
    assert split_authors("{Barnes and Noble} and Smith, J") == [
        "{Barnes and Noble}",
        "Smith, J",
    ]


def test_a_name_merely_containing_and_is_not_split() -> None:
    assert split_authors("Anderson, Sandy and Brand, Andy") == [
        "Anderson, Sandy",
        "Brand, Andy",
    ]


def test_empty_and_blank_fields_have_no_authors() -> None:
    assert format_authors("") == ()
    assert format_authors("   ") == ()


def test_last_first_names_are_kept_as_written() -> None:
    assert format_authors("Schlager, Birgit and Maier, Franz Michael") == (
        "Schlager, Birgit",
        "Maier, Franz Michael",
    )


def test_names_without_a_comma_are_not_reordered() -> None:
    # Could be an institution or a single name — never guess.
    assert format_authors(
        "Intergovernmental Panel on Climate Change and Meteodrones"
    ) == (
        "Intergovernmental Panel on Climate Change",
        "Meteodrones",
    )


def test_latex_escapes_are_decoded() -> None:
    assert format_authors('Sch{\\"o}ner, Wolfgang and N{\\o}jgaard, J.K.') == (
        "Schöner, Wolfgang",
        "Nøjgaard, J.K.",
    )


def test_braces_around_an_institution_are_dropped() -> None:
    assert format_authors("{World Health Organization} and Smith, Jane") == (
        "World Health Organization",
        "Smith, Jane",
    )


def test_and_others_becomes_et_al() -> None:
    assert format_authors("Smith, Jane and others") == ("Smith, Jane", "et al.")


def test_whitespace_around_commas_is_tidied() -> None:
    assert format_authors("Smith,Jane   Q. and  Doe ,  John") == (
        "Smith, Jane Q.",
        "Doe, John",
    )


def test_separator_is_a_slash() -> None:
    assert AUTHOR_SEPARATOR == " / "
