"""Test for the `ctrl+d` action that opens the online documentation."""

from bibtui import DOCS_URL
from bibtui.app import BibTuiApp


def test_action_open_docs_opens_browser_and_notifies(monkeypatch) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    opened: list[str] = []
    notes: list[str] = []

    monkeypatch.setattr("bibtui.app.webbrowser.open", lambda url: opened.append(url))
    monkeypatch.setattr(app, "notify", lambda message, **kwargs: notes.append(message))

    app.action_open_docs()

    assert opened == [DOCS_URL]
    assert notes and "documentation" in notes[-1].lower()
