"""The "press w to write" hint after an edit must actually show the key.

``[w]`` in a notification is Textual markup for a style tag named ``w`` and
renders as nothing — "Press  to write." — so the hint has to spell it another
way.
"""

from conftest import DummyList, wire_dummies
from textual.content import Content

from bibtui.app import BibTuiApp
from bibtui.bib.models import BibEntry

BIB = "tests/bib_examples/MyCollection.bib"


def _rendered(notes: list[tuple[str, str | None]]) -> list[str]:
    return [Content.from_markup(message).plain for message, _severity in notes]


def test_keywords_updated_hint_shows_the_write_key(monkeypatch) -> None:
    app = BibTuiApp(BIB)
    entry = BibEntry(key="k", entry_type="article", keywords="a")
    app._entries = [entry]
    _list, _detail, notes = wire_dummies(
        app, monkeypatch, dummy_list=DummyList(selected=entry)
    )

    app._on_keywords_done(("a, b", set()))

    assert _rendered(notes) == ["Keywords updated. Press w to write."]
    assert entry.keywords == "a, b"


def test_entry_updated_hint_shows_the_write_key(monkeypatch) -> None:
    app = BibTuiApp(BIB)
    entry = BibEntry(key="k", entry_type="article", title="old")
    app._entries = [entry]
    _list, _detail, notes = wire_dummies(app, monkeypatch)

    app._on_edit_done(BibEntry(key="k", entry_type="article", title="new"))

    assert _rendered(notes) == ["Entry updated. Press w to write."]
    assert app._entries[0].title == "new"
