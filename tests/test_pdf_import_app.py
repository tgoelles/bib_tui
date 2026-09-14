"""Tests for the app-level PDF import wiring in bibtui.app."""

from textual.widgets import DataTable

from bibtui.app import BibTuiApp
from bibtui.bib.models import BibEntry
from bibtui.utils.config import Config
from bibtui.widgets.entry_detail import EntryDetail
from bibtui.widgets.entry_list import EntryList


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


def _wire_dummies(app, monkeypatch, dummy_list=None, dummy_detail=None):
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


# ---------------------------------------------------------------------------
# _existing_dois
# ---------------------------------------------------------------------------


def test_existing_dois_normalizes_and_skips_empty() -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._entries = [
        BibEntry(key="a", entry_type="article", doi="https://doi.org/10.1000/TEST"),
        BibEntry(key="b", entry_type="article", doi=""),
        BibEntry(key="c", entry_type="article", doi="10.2000/other"),
    ]
    assert app._existing_dois() == {"10.1000/test", "10.2000/other"}


# ---------------------------------------------------------------------------
# action_import_pdf guard
# ---------------------------------------------------------------------------


def test_action_import_pdf_requires_pdf_base_dir(monkeypatch) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._config = Config(pdf_base_dir="")
    pushed = []
    monkeypatch.setattr(app, "push_screen", lambda *a, **k: pushed.append(a))
    notifications = []
    monkeypatch.setattr(
        app, "notify", lambda message, **kwargs: notifications.append(message)
    )

    app.action_import_pdf()

    assert pushed == []
    assert notifications and "base directory" in notifications[0].lower()


def test_action_import_pdf_passes_download_dir_to_picker(monkeypatch, tmp_path) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._config = Config(pdf_base_dir=str(tmp_path), pdf_download_dir="/some/downloads")
    pushed = []
    monkeypatch.setattr(
        app, "push_screen", lambda screen, callback=None: pushed.append(screen)
    )

    app.action_import_pdf()

    assert len(pushed) == 1
    assert pushed[0]._download_dir == "/some/downloads"


# ---------------------------------------------------------------------------
# _on_pdf_import_picked
# ---------------------------------------------------------------------------


def test_on_pdf_import_picked_pushes_review_with_selected_paths(
    monkeypatch, tmp_path
) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._config = Config(pdf_base_dir=str(tmp_path))
    app._entries = []
    pushed = []
    monkeypatch.setattr(
        app, "push_screen", lambda screen, callback=None: pushed.append(screen)
    )

    pdf1 = tmp_path / "a.pdf"
    pdf2 = tmp_path / "b.pdf"
    pdf1.write_bytes(b"fake")
    pdf2.write_bytes(b"fake")

    app._on_pdf_import_picked([str(pdf1), str(pdf2)])

    assert len(pushed) == 1
    assert pushed[0]._paths == [str(pdf1), str(pdf2)]


def test_on_pdf_import_picked_empty_list_does_not_push(monkeypatch) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    pushed = []
    monkeypatch.setattr(app, "push_screen", lambda *a, **k: pushed.append(a))

    app._on_pdf_import_picked([])

    assert pushed == []


def test_on_pdf_import_picked_none_result_does_nothing(monkeypatch) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    pushed = []
    monkeypatch.setattr(app, "push_screen", lambda *a, **k: pushed.append(a))

    app._on_pdf_import_picked(None)

    assert pushed == []


# ---------------------------------------------------------------------------
# _finalize_imported_entries
# ---------------------------------------------------------------------------


def test_finalize_imported_entries_appends_all_and_refreshes_once(monkeypatch) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._entries = []
    app._dirty = False
    dummy_list, dummy_detail, notifications = _wire_dummies(app, monkeypatch)

    e1 = BibEntry(key="Alpha2023", entry_type="article", doi="10.1/a")
    e2 = BibEntry(key="Beta2023", entry_type="article", doi="10.1/b")

    app._finalize_imported_entries([e1, e2])

    assert app._entries == [e1, e2]
    assert app._dirty is True
    assert dummy_list.refresh_calls == 1
    assert dummy_detail.shown is e2
    assert any("Imported 2 entries" in msg for msg, _sev in notifications)


def test_finalize_imported_entries_renames_on_key_conflict(monkeypatch) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    existing = BibEntry(key="Smith2023", entry_type="article", title="Existing Paper")
    app._entries = [existing]
    app._dirty = False
    _wire_dummies(app, monkeypatch)

    incoming = BibEntry(key="Smith2023", entry_type="article", title="A Different Paper")
    app._finalize_imported_entries([incoming])

    assert incoming.key == "Smith2023a"


def test_finalize_imported_entries_never_triggers_auto_fetch(monkeypatch) -> None:
    """Entries from PDF import already have their PDF linked — auto-fetch
    would immediately refetch and overwrite it, since _maybe_auto_fetch has
    no "already has a file" guard."""
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._config = Config(pdf_base_dir="/tmp/pdfs", auto_fetch_pdf=True)
    app._entries = []
    _wire_dummies(app, monkeypatch)

    called = []
    monkeypatch.setattr(app, "_maybe_auto_fetch", lambda entry: called.append(entry))

    entry = BibEntry(
        key="Gamma2023", entry_type="article", doi="10.1/g", file=":Gamma2023.pdf:PDF"
    )
    app._finalize_imported_entries([entry])

    assert called == []


def test_finalize_imported_entries_reports_errors_without_crashing(monkeypatch) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._entries = []
    _wire_dummies(app, monkeypatch)
    notifications = []
    monkeypatch.setattr(
        app,
        "notify",
        lambda message, **kwargs: notifications.append((message, kwargs.get("severity"))),
    )

    no_key = BibEntry(key="", entry_type="article")
    ok_entry = BibEntry(key="Delta2023", entry_type="article")

    app._finalize_imported_entries([no_key, ok_entry])

    assert app._entries == [ok_entry]
    assert any("Imported 1 entry" in msg for msg, _sev in notifications)
    assert any(sev == "warning" for _msg, sev in notifications)
