"""Tests for the `n` New Entry chooser and its routing in bibtui.app."""

from bibtui.app import BibTuiApp
from bibtui.widgets.modals import NewEntryChooserModal, NewEntryModal

BIB = "tests/bib_examples/MyCollection.bib"


def test_action_new_entry_pushes_chooser(monkeypatch) -> None:
    app = BibTuiApp(BIB)
    pushed = []
    monkeypatch.setattr(app, "push_screen", lambda screen, callback=None: pushed.append(screen))

    app.action_new_entry()

    assert len(pushed) == 1
    assert isinstance(pushed[0], NewEntryChooserModal)


def test_choice_blank_opens_new_entry_modal(monkeypatch) -> None:
    app = BibTuiApp(BIB)
    pushed = []
    monkeypatch.setattr(app, "push_screen", lambda screen, callback=None: pushed.append(screen))

    app._on_new_entry_choice("blank")

    assert len(pushed) == 1
    assert isinstance(pushed[0], NewEntryModal)


def test_choice_doi_delegates_to_action_doi_import(monkeypatch) -> None:
    app = BibTuiApp(BIB)
    calls = []
    monkeypatch.setattr(app, "action_doi_import", lambda: calls.append("doi"))

    app._on_new_entry_choice("doi")

    assert calls == ["doi"]


def test_choice_pdf_delegates_to_action_import_pdf(monkeypatch) -> None:
    app = BibTuiApp(BIB)
    calls = []
    monkeypatch.setattr(app, "action_import_pdf", lambda: calls.append("pdf"))

    app._on_new_entry_choice("pdf")

    assert calls == ["pdf"]


def test_choice_paste_delegates_to_action_paste_import(monkeypatch) -> None:
    app = BibTuiApp(BIB)
    calls = []
    monkeypatch.setattr(app, "action_paste_import", lambda: calls.append("paste"))

    app._on_new_entry_choice("paste")

    assert calls == ["paste"]


def test_choice_none_does_nothing(monkeypatch) -> None:
    app = BibTuiApp(BIB)
    pushed = []
    monkeypatch.setattr(app, "push_screen", lambda *a, **k: pushed.append(a))

    app._on_new_entry_choice(None)

    assert pushed == []
