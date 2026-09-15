"""Tests for the app-level PDF import wiring in bibtui.app."""

from conftest import DummyList, wire_dummies

from bibtui.app import BibTuiApp
from bibtui.bib.models import BibEntry
from bibtui.utils.config import Config

BIB = "tests/bib_examples/MyCollection.bib"


# ---------------------------------------------------------------------------
# _existing_entries_by_doi
# ---------------------------------------------------------------------------


def test_existing_entries_by_doi_normalizes_and_skips_empty() -> None:
    app = BibTuiApp(BIB)
    e_a = BibEntry(key="a", entry_type="article", doi="https://doi.org/10.1000/TEST")
    e_b = BibEntry(key="b", entry_type="article", doi="")
    e_c = BibEntry(key="c", entry_type="article", doi="10.2000/other")
    app._entries = [e_a, e_b, e_c]

    result = app._existing_entries_by_doi()

    assert result == {"10.1000/test": e_a, "10.2000/other": e_c}
    # Same objects, not copies — PDF import mutates them in place to link.
    assert result["10.1000/test"] is e_a


# ---------------------------------------------------------------------------
# action_import_pdf guard
# ---------------------------------------------------------------------------


def test_action_import_pdf_requires_pdf_base_dir(monkeypatch) -> None:
    app = BibTuiApp(BIB)
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
    app = BibTuiApp(BIB)
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
    app = BibTuiApp(BIB)
    app._config = Config(pdf_base_dir=str(tmp_path))
    existing = BibEntry(key="Existing2020", entry_type="article", doi="10.9/x")
    app._entries = [existing]
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
    assert pushed[0]._existing_by_doi == {"10.9/x": existing}


def test_on_pdf_import_picked_empty_list_does_not_push(monkeypatch) -> None:
    app = BibTuiApp(BIB)
    pushed = []
    monkeypatch.setattr(app, "push_screen", lambda *a, **k: pushed.append(a))

    app._on_pdf_import_picked([])

    assert pushed == []


def test_on_pdf_import_picked_none_result_does_nothing(monkeypatch) -> None:
    app = BibTuiApp(BIB)
    pushed = []
    monkeypatch.setattr(app, "push_screen", lambda *a, **k: pushed.append(a))

    app._on_pdf_import_picked(None)

    assert pushed == []


# ---------------------------------------------------------------------------
# _on_pdf_import_review_done
# ---------------------------------------------------------------------------


def test_on_pdf_import_review_done_appends_new_entries(monkeypatch) -> None:
    app = BibTuiApp(BIB)
    app._entries = []
    app._dirty = False
    dummy_list, _dummy_detail, notifications = wire_dummies(app, monkeypatch)

    new_entry = BibEntry(key="New2024", entry_type="article", doi="10.1/n")
    app._on_pdf_import_review_done({"new": [new_entry], "relinked": []})

    assert app._entries == [new_entry]
    assert dummy_list.refresh_calls == 1
    assert any("Imported 1 entry" in msg for msg, _sev in notifications)


def test_on_pdf_import_review_done_relinks_existing_entry_without_appending(
    monkeypatch,
) -> None:
    app = BibTuiApp(BIB)
    existing = BibEntry(key="Old2020", entry_type="article", doi="10.1/o")
    app._entries = [existing]
    app._dirty = False
    dummy_list, dummy_detail, notifications = wire_dummies(
        app, monkeypatch, dummy_list=DummyList(selected=existing)
    )

    # The review modal mutates the same object in place before calling back.
    existing.file = ":Old2020.pdf:PDF"
    app._on_pdf_import_review_done({"new": [], "relinked": [existing]})

    assert app._entries == [existing]  # not duplicated
    assert app._dirty is True
    assert dummy_list.refresh_calls == 1
    assert dummy_detail.shown is existing
    assert any("Linked PDF to 1 existing entry" in msg for msg, _sev in notifications)


def test_on_pdf_import_review_done_handles_both_new_and_relinked(monkeypatch) -> None:
    app = BibTuiApp(BIB)
    existing = BibEntry(key="Old2020", entry_type="article", doi="10.1/o")
    app._entries = [existing]
    app._dirty = False
    dummy_list, _dummy_detail, notifications = wire_dummies(app, monkeypatch)

    new_entry = BibEntry(key="New2024", entry_type="article", doi="10.1/n")
    existing.file = ":Old2020.pdf:PDF"
    app._on_pdf_import_review_done({"new": [new_entry], "relinked": [existing]})

    assert app._entries == [existing, new_entry]
    assert dummy_list.refresh_calls == 2  # one per branch — both ran
    assert any("Imported 1 entry" in msg for msg, _sev in notifications)
    assert any("Linked PDF to 1 existing entry" in msg for msg, _sev in notifications)


def test_on_pdf_import_review_done_none_or_empty_does_nothing(monkeypatch) -> None:
    app = BibTuiApp(BIB)
    app._entries = []
    calls = []
    monkeypatch.setattr(app, "query_one", lambda *a, **k: calls.append(a))

    app._on_pdf_import_review_done(None)
    app._on_pdf_import_review_done({})
    app._on_pdf_import_review_done({"new": [], "relinked": []})

    assert app._entries == []
    assert calls == []


# ---------------------------------------------------------------------------
# _finalize_imported_entries
# ---------------------------------------------------------------------------


def test_finalize_imported_entries_appends_all_and_refreshes_once(monkeypatch) -> None:
    app = BibTuiApp(BIB)
    app._entries = []
    app._dirty = False
    dummy_list, dummy_detail, notifications = wire_dummies(app, monkeypatch)

    e1 = BibEntry(key="Alpha2023", entry_type="article", doi="10.1/a")
    e2 = BibEntry(key="Beta2023", entry_type="article", doi="10.1/b")

    app._finalize_imported_entries([e1, e2])

    assert app._entries == [e1, e2]
    assert app._dirty is True
    assert dummy_list.refresh_calls == 1
    assert dummy_detail.shown is e2
    assert any("Imported 2 entries" in msg for msg, _sev in notifications)


def test_finalize_imported_entries_renames_on_key_conflict(monkeypatch) -> None:
    app = BibTuiApp(BIB)
    existing = BibEntry(key="Smith2023", entry_type="article", title="Existing Paper")
    app._entries = [existing]
    app._dirty = False
    wire_dummies(app, monkeypatch)

    incoming = BibEntry(key="Smith2023", entry_type="article", title="A Different Paper")
    app._finalize_imported_entries([incoming])

    assert incoming.key == "Smith2023a"


def test_finalize_imported_entries_never_triggers_auto_fetch(monkeypatch) -> None:
    """Entries from PDF import already have their PDF linked — auto-fetch
    would immediately refetch and overwrite it, since _maybe_auto_fetch has
    no "already has a file" guard."""
    app = BibTuiApp(BIB)
    app._config = Config(pdf_base_dir="/tmp/pdfs", auto_fetch_pdf=True)
    app._entries = []
    wire_dummies(app, monkeypatch)

    called = []
    monkeypatch.setattr(app, "_maybe_auto_fetch", lambda entry: called.append(entry))

    entry = BibEntry(
        key="Gamma2023", entry_type="article", doi="10.1/g", file=":Gamma2023.pdf:PDF"
    )
    app._finalize_imported_entries([entry])

    assert called == []


def test_finalize_imported_entries_reports_errors_without_crashing(monkeypatch) -> None:
    app = BibTuiApp(BIB)
    app._entries = []
    wire_dummies(app, monkeypatch)
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
