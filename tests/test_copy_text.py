"""Tests for BibTuiApp._copy_text and the copy actions that use it."""

import types

import pytest

from bibtui.app import BibTuiApp
from bibtui.bib.models import BibEntry
from bibtui.widgets.entry_detail import EntryDetail
from bibtui.widgets.entry_list import EntryList

BIB = "tests/bib_examples/MyCollection.bib"


@pytest.fixture
def app(monkeypatch):
    app = BibTuiApp(BIB)
    app._osc52: list[str] = []
    app._notes: list[str] = []
    monkeypatch.setattr(app, "copy_to_clipboard", lambda v: app._osc52.append(v))
    monkeypatch.setattr(app, "notify", lambda msg, **kw: app._notes.append(msg))
    return app


@pytest.fixture
def native(monkeypatch):
    """Record calls to the native clipboard helper (and stop it touching the real one)."""
    calls: list[str] = []
    monkeypatch.setattr(
        "bibtui.app.copy_to_os_clipboard", lambda text: calls.append(text) or True
    )
    return calls


# ---------------------------------------------------------------------------
# _copy_text
# ---------------------------------------------------------------------------


def test_copy_text_writes_via_osc52_and_native_tool(app, native) -> None:
    app._copy_text("payload", "Copied")
    assert app._osc52 == ["payload"]
    assert native == ["payload"]


def test_copy_text_notification_is_just_the_label(app, native) -> None:
    app._copy_text("x", "Copied BibTeX: Foo2020")
    assert app._notes == ["Copied BibTeX: Foo2020"]


# ---------------------------------------------------------------------------
# copy actions route their payload through _copy_text
# ---------------------------------------------------------------------------


def _fake_query_one(mapping: dict):
    def query_one(expect_type, *args, **kwargs):
        return mapping[expect_type]

    return query_one


def test_action_copy_entry_copies_bibtex(app, monkeypatch) -> None:
    entry = BibEntry(key="Smith2021", entry_type="article", title="Hi")
    monkeypatch.setattr(
        app,
        "query_one",
        _fake_query_one({EntryList: types.SimpleNamespace(selected_entry=entry)}),
    )
    captured: list[tuple[str, str]] = []
    monkeypatch.setattr(app, "_copy_text", lambda text, label: captured.append((text, label)))

    app.action_copy_entry()

    text, label = captured[0]
    assert text.startswith("@article{Smith2021")
    assert label == "Copied BibTeX: Smith2021"


def test_action_copy_citation_copies_preview_text(app, monkeypatch) -> None:
    entry = BibEntry(key="Smith2021", entry_type="article")
    detail = types.SimpleNamespace(citation_preview_text=lambda: "Smith, J. (2021). Hi.")
    monkeypatch.setattr(
        app,
        "query_one",
        _fake_query_one(
            {
                EntryList: types.SimpleNamespace(selected_entry=entry),
                EntryDetail: detail,
            }
        ),
    )
    captured: list[tuple[str, str]] = []
    monkeypatch.setattr(app, "_copy_text", lambda text, label: captured.append((text, label)))

    app.action_copy_citation()

    assert captured == [("Smith, J. (2021). Hi.", "Copied citation: Smith2021")]


def test_action_copy_key_copies_cite_key_when_no_text_widget_focused(
    app, monkeypatch
) -> None:
    entry = BibEntry(key="Smith2021", entry_type="article")
    monkeypatch.setattr(type(app), "focused", property(lambda self: None))
    monkeypatch.setattr(
        app,
        "query_one",
        _fake_query_one({EntryList: types.SimpleNamespace(selected_entry=entry)}),
    )
    captured: list[tuple[str, str]] = []
    monkeypatch.setattr(app, "_copy_text", lambda text, label: captured.append((text, label)))

    app.action_copy_key()

    assert captured == [("Smith2021", "Copied: Smith2021")]
