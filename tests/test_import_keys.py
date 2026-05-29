from bibtui.app import BibTuiApp
from bibtui.bib.models import BibEntry


def test_resolve_import_key_no_collision() -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._entries = []

    key, error = app._resolve_import_key(
        BibEntry(key="Goelles2025", entry_type="article", title="New title")
    )

    assert error is None
    assert key == "Goelles2025"


def test_resolve_import_key_same_title_rejected() -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._entries = [
        BibEntry(
            key="Goelles2025",
            entry_type="article",
            title="A cool paper",
        )
    ]

    key, error = app._resolve_import_key(
        BibEntry(
            key="Goelles2025",
            entry_type="article",
            title="  A COOL   paper ",
        )
    )

    assert key is None
    assert error is not None
    assert "same title" in error


def test_resolve_import_key_adds_suffix_for_different_title() -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._entries = [
        BibEntry(key="Goelles2025", entry_type="article", title="Paper A"),
    ]

    key, error = app._resolve_import_key(
        BibEntry(key="Goelles2025", entry_type="article", title="Paper B")
    )

    assert error is None
    assert key == "Goelles2025a"


def test_resolve_import_key_picks_next_free_suffix() -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._entries = [
        BibEntry(key="Goelles2025", entry_type="article", title="Paper A"),
        BibEntry(key="Goelles2025a", entry_type="article", title="Paper A1"),
        BibEntry(key="Goelles2025b", entry_type="article", title="Paper A2"),
    ]

    key, error = app._resolve_import_key(
        BibEntry(key="Goelles2025", entry_type="article", title="Paper C")
    )

    assert error is None
    assert key == "Goelles2025c"


def test_resolve_import_key_errors_when_suffixes_exhausted() -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._entries = [
        BibEntry(key="Goelles2025", entry_type="article", title="Original"),
        *[
            BibEntry(
                key=f"Goelles2025{suffix}",
                entry_type="article",
                title=f"Other {suffix}",
            )
            for suffix in "abcdefghijklmnopqrstuvwxyz"
        ],
    ]

    key, error = app._resolve_import_key(
        BibEntry(key="Goelles2025", entry_type="article", title="Completely new")
    )

    assert key is None
    assert error is not None
    assert "a-z" in error
