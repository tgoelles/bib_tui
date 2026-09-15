"""Tests for "Import .bib File" (`n` → `b`): bibtui.app wiring and
BibFileImportReviewModal's DOI-based duplicate detection.
"""

from conftest import wire_dummies
from textual.widgets import Button, OptionList

from bibtui.app import BibTuiApp
from bibtui.bib.models import BibEntry
from bibtui.widgets.modals import BibFileImportReviewModal, ImportBibPickerModal

BIB = "tests/bib_examples/MyCollection.bib"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _entry_text(key: str, doi: str = "", title: str = "A Paper") -> str:
    doi_line = f"  doi = {{{doi}}},\n" if doi else ""
    return (
        f"@article{{{key},\n"
        f"  title = {{{title}}},\n"
        "  author = {Doe, Jane},\n"
        "  year = {2023},\n"
        "  journal = {Nature},\n"
        f"{doi_line}"
        "}\n"
    )


def _write_bib(tmp_path, name: str, *entries_text: str):
    path = tmp_path / name
    path.write_text("\n".join(entries_text), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# action_import_bib_file / _on_bib_file_picked
# ---------------------------------------------------------------------------


def test_action_import_bib_file_pushes_picker(monkeypatch) -> None:
    app = BibTuiApp(BIB)
    pushed = []
    monkeypatch.setattr(
        app, "push_screen", lambda screen, callback=None: pushed.append(screen)
    )

    app.action_import_bib_file()

    assert len(pushed) == 1
    assert isinstance(pushed[0], ImportBibPickerModal)


def test_on_bib_file_picked_none_does_nothing(monkeypatch) -> None:
    app = BibTuiApp(BIB)
    pushed = []
    monkeypatch.setattr(app, "push_screen", lambda *a, **k: pushed.append(a))

    app._on_bib_file_picked(None)

    assert pushed == []


def test_on_bib_file_picked_malformed_file_notifies_error(tmp_path, monkeypatch) -> None:
    app = BibTuiApp(BIB)
    app._entries = []
    notes = []
    monkeypatch.setattr(
        app, "notify", lambda message, **kwargs: notes.append((message, kwargs.get("severity")))
    )
    path = tmp_path / "broken.bib"
    path.write_text("not { valid bibtex at all @@@", encoding="utf-8")

    app._on_bib_file_picked(str(path))

    # bibtexparser is lenient about junk text (it just finds 0 entries), so
    # either an error notification or the "no entries found" one is fine —
    # what matters is nothing was added and nothing crashed.
    assert app._entries == []
    assert notes
    assert notes[-1][1] in ("error", "warning")


def test_on_bib_file_picked_empty_file_notifies_warning(tmp_path, monkeypatch) -> None:
    app = BibTuiApp(BIB)
    app._entries = []
    notes = []
    monkeypatch.setattr(
        app, "notify", lambda message, **kwargs: notes.append((message, kwargs.get("severity")))
    )
    path = _write_bib(tmp_path, "empty.bib", "")

    app._on_bib_file_picked(path)

    assert app._entries == []
    assert notes and notes[-1][1] == "warning"
    assert "no entries" in notes[-1][0].lower()


def test_on_bib_file_picked_single_new_entry_is_added_directly(
    tmp_path, monkeypatch
) -> None:
    app = BibTuiApp(BIB)
    app._entries = []
    app._dirty = False
    app._config.auto_fetch_pdf = False
    dummy_list, _dummy_detail, notes = wire_dummies(app, monkeypatch)
    path = _write_bib(tmp_path, "one.bib", _entry_text("Doe2023", doi="10.1/new"))

    app._on_bib_file_picked(path)

    assert [e.key for e in app._entries] == ["Doe2023"]
    assert app._dirty is True
    assert dummy_list.refresh_calls == 1
    assert any("Added" in msg for msg, _sev in notes)


def test_on_bib_file_picked_single_duplicate_entry_is_skipped(
    tmp_path, monkeypatch
) -> None:
    app = BibTuiApp(BIB)
    existing = BibEntry(key="Existing2020", entry_type="article", doi="10.1/dup")
    app._entries = [existing]
    app._dirty = False
    notes = []
    monkeypatch.setattr(
        app, "notify", lambda message, **kwargs: notes.append((message, kwargs.get("severity")))
    )
    path = _write_bib(tmp_path, "dup.bib", _entry_text("Doe2023", doi="10.1/DUP"))

    app._on_bib_file_picked(path)

    assert app._entries == [existing]  # nothing added
    assert notes and notes[-1][1] == "warning"
    assert "Existing2020" in notes[-1][0]


def test_on_bib_file_picked_multi_entry_pushes_review_modal(tmp_path, monkeypatch) -> None:
    app = BibTuiApp(BIB)
    app._entries = []
    pushed = []
    monkeypatch.setattr(
        app, "push_screen", lambda screen, callback=None: pushed.append(screen)
    )
    path = _write_bib(
        tmp_path,
        "many.bib",
        _entry_text("A2023", doi="10.1/a"),
        _entry_text("B2023", doi="10.1/b"),
    )

    app._on_bib_file_picked(path)

    assert len(pushed) == 1
    modal = pushed[0]
    assert isinstance(modal, BibFileImportReviewModal)
    assert len(modal._new_entries) == 2


def test_on_bib_file_review_done_appends_entries(monkeypatch) -> None:
    app = BibTuiApp(BIB)
    app._entries = []
    app._dirty = False
    dummy_list, _dummy_detail, notes = wire_dummies(app, monkeypatch)

    e1 = BibEntry(key="A2023", entry_type="article", doi="10.1/a")
    e2 = BibEntry(key="B2023", entry_type="article", doi="10.1/b")
    app._on_bib_file_review_done([e1, e2])

    assert [e.key for e in app._entries] == ["A2023", "B2023"]
    assert dummy_list.refresh_calls == 1
    assert any("Imported 2 entries" in msg for msg, _sev in notes)


def test_on_bib_file_review_done_none_or_empty_does_nothing(monkeypatch) -> None:
    app = BibTuiApp(BIB)
    app._entries = []
    pushed = []
    monkeypatch.setattr(app, "query_one", lambda *a, **k: pushed.append(a))

    app._on_bib_file_review_done(None)
    app._on_bib_file_review_done([])

    assert app._entries == []
    assert pushed == []


# ---------------------------------------------------------------------------
# BibFileImportReviewModal duplicate detection (no app/mount needed)
# ---------------------------------------------------------------------------


def _entry(key: str, doi: str = "") -> BibEntry:
    return BibEntry(key=key, entry_type="article", title="A Paper", doi=doi)


def test_review_modal_marks_new_entries() -> None:
    entries = [_entry("A2023", "10.1/a"), _entry("B2023")]  # second has no DOI
    modal = BibFileImportReviewModal(entries, existing_by_doi={})

    assert modal._new_entries == entries
    assert all(reason is None for _e, reason in modal._rows)


def test_review_modal_flags_duplicate_against_library() -> None:
    existing = _entry("Old2020", "10.1/a")
    entries = [_entry("A2023", "10.1/A")]  # case-insensitive DOI match
    modal = BibFileImportReviewModal(entries, existing_by_doi={"10.1/a": existing})

    assert modal._new_entries == []
    _entry_obj, reason = modal._rows[0]
    assert reason == "Already in library as 'Old2020'"


def test_review_modal_flags_in_batch_duplicate() -> None:
    entries = [_entry("A2023", "10.1/x"), _entry("A2023b", "10.1/x")]
    modal = BibFileImportReviewModal(entries, existing_by_doi={})

    assert [e.key for e in modal._new_entries] == ["A2023"]
    _e0, reason0 = modal._rows[0]
    _e1, reason1 = modal._rows[1]
    assert reason0 is None
    assert reason1 == "Duplicate of another entry in this file"


def test_review_modal_no_doi_entries_are_never_flagged_as_duplicate() -> None:
    entries = [_entry("A2023"), _entry("B2023")]
    modal = BibFileImportReviewModal(entries, existing_by_doi={})

    assert len(modal._new_entries) == 2


async def test_review_modal_confirm_dismisses_with_new_entries_only(monkeypatch) -> None:
    existing = _entry("Old2020", "10.1/dup")
    entries = [_entry("New2023", "10.1/new"), _entry("Dup2023", "10.1/DUP")]

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        result: dict = {}
        modal = BibFileImportReviewModal(entries, existing_by_doi={"10.1/dup": existing})
        app.push_screen(modal, lambda r: result.__setitem__("v", r))
        await pilot.pause()

        ol = modal.query_one(OptionList)
        assert ol.option_count == 2
        btn = modal.query_one("#btn-import", Button)
        assert "1" in str(btn.label)
        assert btn.disabled is False

        modal._confirm()
        await pilot.pause()

        assert [e.key for e in result["v"]] == ["New2023"]


async def test_review_modal_import_button_disabled_when_all_duplicates(monkeypatch) -> None:
    existing = _entry("Old2020", "10.1/dup")
    entries = [_entry("Dup2023", "10.1/dup")]

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal = BibFileImportReviewModal(entries, existing_by_doi={"10.1/dup": existing})
        app.push_screen(modal)
        await pilot.pause()

        assert modal.query_one("#btn-import", Button).disabled is True
