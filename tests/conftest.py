"""Shared test fixtures.

``DummyDataTable``/``DummyList``/``DummyDetail`` plus ``wire_dummies`` stand
in for the app's real ``DataTable``/``EntryList``/``EntryDetail`` widgets in
tests that exercise ``BibTuiApp`` methods without running a full Textual
pilot session. Originally duplicated between ``test_pdf_import_app.py`` and
``test_bib_file_import.py`` — shared here so new tests in that style don't
have to re-copy it.
"""

import pytest
from textual.widgets import DataTable

from bibtui.widgets.entry_detail import EntryDetail
from bibtui.widgets.entry_list import EntryList


@pytest.fixture(autouse=True)
def _isolated_filters_path(tmp_path, monkeypatch):
    """Point every test at its own filters.toml, never the real
    ~/.config/bibtui/filters.toml on the developer's machine — its active
    filter would otherwise silently narrow the entries any ``BibTuiApp(...)``
    loads in a test that doesn't override this itself."""
    monkeypatch.setattr("bibtui.utils.filters.FILTERS_PATH", tmp_path / "filters.toml")


class DummyDataTable:
    def move_cursor(self, **kwargs) -> None:
        pass


class DummyList:
    def __init__(self, selected=None) -> None:
        self.selected_entry = selected
        self.refresh_calls = 0
        self._filtered: list = []

    def refresh_entries(self, entries) -> None:
        self.refresh_calls += 1
        self._filtered = list(entries)


class DummyDetail:
    def __init__(self) -> None:
        self.shown = None

    def show_entry(self, entry) -> None:
        self.shown = entry


def wire_dummies(app, monkeypatch, dummy_list=None, dummy_detail=None):
    """Patch *app* so ``query_one(EntryList/EntryDetail/DataTable)`` returns
    dummies, ``notify`` records its calls, and ``call_after_refresh`` runs
    its callback immediately. Returns ``(dummy_list, dummy_detail,
    notifications)``."""
    dummy_list = dummy_list or DummyList()
    dummy_detail = dummy_detail or DummyDetail()
    notifications: list[tuple[str, str | None]] = []

    def fake_query_one(selector):
        if selector is EntryList:
            return dummy_list
        if selector is EntryDetail:
            return dummy_detail
        if selector is DataTable:
            return DummyDataTable()
        raise AssertionError(f"Unexpected selector: {selector}")

    monkeypatch.setattr(app, "query_one", fake_query_one)
    monkeypatch.setattr(
        app,
        "notify",
        lambda message, **kwargs: notifications.append((message, kwargs.get("severity"))),
    )
    monkeypatch.setattr(app, "call_after_refresh", lambda fn, *a, **k: fn(*a, **k))
    return dummy_list, dummy_detail, notifications
