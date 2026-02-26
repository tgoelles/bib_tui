import asyncio
import os

from bibtui.app import BibTuiApp
from bibtui.bib.models import BibEntry
from bibtui.pdf.fetcher import pdf_filename
from bibtui.utils.config import Config
from bibtui.widgets.entry_detail import EntryDetail
from bibtui.widgets.entry_list import EntryList
from bibtui.widgets.modals import ConfirmModal


def test_missing_pdf_candidates_respects_overwrite_broken_option(tmp_path) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._config = Config(pdf_base_dir=str(tmp_path))

    existing = BibEntry(key="haspdf", entry_type="article", file=":haspdf.pdf:PDF")
    empty = BibEntry(key="empty", entry_type="article", file="")
    broken = BibEntry(key="broken", entry_type="article", file=":broken.pdf:PDF")
    app._entries = [existing, empty, broken]

    (tmp_path / "haspdf.pdf").write_bytes(b"%PDF-1.4 fake")

    no_overwrite = app._missing_pdf_candidates(overwrite_broken_links=False)
    assert [e.key for e in no_overwrite] == ["empty"]

    with_overwrite = app._missing_pdf_candidates(overwrite_broken_links=True)
    assert [e.key for e in with_overwrite] == ["empty", "broken"]


def test_missing_pdf_candidates_uses_key_fallback_lookup(tmp_path) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._config = Config(pdf_base_dir=str(tmp_path))

    # Stored file path does not exist, but key-based fallback should count as present.
    entry = BibEntry(key="fallback", entry_type="article", file=":nonexistent.pdf:PDF")
    app._entries = [entry]

    fallback_path = tmp_path / "fallback - title.pdf"
    fallback_path.write_bytes(b"%PDF-1.4 fake")

    candidates = app._missing_pdf_candidates(overwrite_broken_links=True)
    assert candidates == []


def test_on_batch_fetch_missing_pdfs_done_relinks_and_marks_dirty(
    tmp_path, monkeypatch
) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._config = Config(pdf_base_dir=str(tmp_path))

    entry1 = BibEntry(key="k1", entry_type="article")
    entry2 = BibEntry(key="k2", entry_type="article", file=":k2.pdf:PDF")
    app._entries = [entry1, entry2]
    app._dirty = False

    class DummyList:
        def __init__(self) -> None:
            self.selected_entry = entry1
            self.refreshed = False

        def refresh_entries(self, entries) -> None:
            self.refreshed = entries is app._entries

    class DummyDetail:
        def __init__(self) -> None:
            self.shown = None

        def show_entry(self, entry) -> None:
            self.shown = entry

    dummy_list = DummyList()
    dummy_detail = DummyDetail()
    notifications: list[str] = []

    def fake_query_one(selector):
        if selector is EntryList:
            return dummy_list
        if selector is EntryDetail:
            return dummy_detail
        raise AssertionError(f"Unexpected selector: {selector}")

    monkeypatch.setattr(app, "query_one", fake_query_one)
    monkeypatch.setattr(
        app, "notify", lambda message, **kwargs: notifications.append(message)
    )

    saved_path = os.path.join(str(tmp_path), "k1.pdf")
    result = {
        "paths_by_key": {"k1": saved_path},
        "success": 1,
        "failed": 0,
        "skipped": 0,
    }

    app._on_batch_fetch_missing_pdfs_done(result)

    assert entry1.file == ":k1.pdf:PDF"
    assert entry2.file == ":k2.pdf:PDF"
    assert app._dirty is True
    assert dummy_list.refreshed is True
    assert dummy_detail.shown is entry1
    assert notifications
    assert "1 fetched" in notifications[-1]


def test_scan_citekey_unification_skips_already_matching_pattern() -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._entries = [
        BibEntry(
            key="Goelles2025",
            entry_type="article",
            author="Gölles, Thomas",
            year="2025",
        ),
        BibEntry(
            key="weird_key", entry_type="article", author=r"M{\"o}ller, A", year="2025"
        ),
    ]

    scan = app._scan_citekey_unification()

    assert scan["already_ok"] == 1
    assert len(scan["plan"]) == 1
    entry, new_key = scan["plan"][0]
    assert entry.key == "weird_key"
    assert new_key == "Moeller2025"


def test_scan_citekey_unification_skips_when_author_or_year_missing() -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._entries = [
        BibEntry(key="KeepNoAuthor", entry_type="article", author="", year="2025"),
        BibEntry(
            key="KeepNoYear", entry_type="article", author="Steininger, Karl", year=""
        ),
    ]

    scan = app._scan_citekey_unification()

    assert scan["skipped_missing_metadata"] == 2
    assert scan["already_ok"] == 0
    assert scan["plan"] == []


def test_scan_citekey_unification_normalizes_key_casing_from_author_year() -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._entries = [
        BibEntry(
            key="STEINIGER2021",
            entry_type="article",
            author="Steininger, Karl",
            year="2021",
        ),
        BibEntry(
            key="steinininger2021",
            entry_type="article",
            author="Steininger, Karl",
            year="2021",
        ),
    ]

    scan = app._scan_citekey_unification()

    assert len(scan["plan"]) == 2
    assert scan["plan"][0][1] == "Steininger2021"
    assert scan["plan"][1][1] == "Steininger2021a"


def test_scan_citekey_unification_keeps_canonical_key_even_if_author_differs() -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._entries = [
        BibEntry(
            key="Melcher2014",
            entry_type="article",
            author="Mechler, Reinhard",
            year="2014",
        )
    ]

    scan = app._scan_citekey_unification()

    assert scan["already_ok"] == 1
    assert scan["plan"] == []


def test_scan_citekey_unification_keeps_hyphenated_canonical_key() -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._entries = [
        BibEntry(
            key="Irvine-Fynn2025",
            entry_type="article",
            author="Irvine-Fynn, Tristram",
            year="2025",
        )
    ]

    scan = app._scan_citekey_unification()

    assert scan["already_ok"] == 1
    assert scan["plan"] == []


def test_start_unify_citekeys_hints_when_only_missing_metadata(monkeypatch) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    notifications: list[str] = []

    monkeypatch.setattr(
        app,
        "_scan_citekey_unification",
        lambda: {
            "total": 2,
            "already_ok": 0,
            "skipped_missing_metadata": 2,
            "plan": [],
        },
    )
    monkeypatch.setattr(
        app, "notify", lambda message, **kwargs: notifications.append(message)
    )
    monkeypatch.setattr(
        app,
        "push_screen",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("should not open confirm")
        ),
    )

    app._start_library_unify_citekeys()

    assert notifications
    assert "missing author/year" in notifications[-1]


def test_unify_citekeys_integration_shows_warning_modal_text(monkeypatch) -> None:
    captured: dict[str, str] = {}

    async def _run() -> None:
        app = BibTuiApp("tests/bib_examples/MyCollection.bib")

        original_push_screen = app.push_screen

        def intercept_push_screen(screen, *args, **kwargs):
            if isinstance(screen, ConfirmModal):
                captured["message"] = screen._message
                return None
            return original_push_screen(screen, *args, **kwargs)

        monkeypatch.setattr(app, "push_screen", intercept_push_screen)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._entries = [
                BibEntry(
                    key="old_key",
                    entry_type="article",
                    author="Steininger, Karl",
                    year="2021",
                ),
                BibEntry(
                    key="keep_no_year",
                    entry_type="article",
                    author="NoYear, Author",
                    year="",
                ),
            ]
            app._start_library_unify_citekeys()
            await pilot.pause()

    asyncio.run(_run())

    assert "message" in captured
    msg = captured["message"]
    assert "Existing LaTeX documents using old citekeys may break" in msg
    assert "Skipped (missing author/year): 1" in msg
    assert "Continue?" in msg


def test_apply_citekey_unification_renames_key_and_pdf(tmp_path, monkeypatch) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._config = Config(pdf_base_dir=str(tmp_path))

    entry = BibEntry(
        key="old_key",
        entry_type="article",
        title="Ice",
        author="Gölles, Thomas",
        year="2025",
        file=":old_key - Ice.pdf:PDF",
    )
    app._entries = [entry]

    old_path = tmp_path / "old_key - Ice.pdf"
    old_path.write_bytes(b"%PDF-1.4 fake")

    class DummyList:
        def __init__(self) -> None:
            self.selected_entry = entry
            self.refreshed = False

        def refresh_entries(self, entries) -> None:
            self.refreshed = entries is app._entries

    class DummyDetail:
        def __init__(self) -> None:
            self.shown = None

        def show_entry(self, shown_entry) -> None:
            self.shown = shown_entry

    dummy_list = DummyList()
    dummy_detail = DummyDetail()
    notifications: list[str] = []

    def fake_query_one(selector):
        if selector is EntryList:
            return dummy_list
        if selector is EntryDetail:
            return dummy_detail
        raise AssertionError(f"Unexpected selector: {selector}")

    monkeypatch.setattr(app, "query_one", fake_query_one)
    monkeypatch.setattr(
        app, "notify", lambda message, **kwargs: notifications.append(message)
    )

    app._apply_citekey_unification([(entry, "Goelles2025")])

    expected_path = tmp_path / pdf_filename(
        BibEntry(key="Goelles2025", entry_type="article", title="Ice")
    )
    assert entry.key == "Goelles2025"
    assert entry.file == ":Goelles2025 - Ice.pdf:PDF"
    assert expected_path.exists()
    assert not old_path.exists()
    assert app._dirty is True
    assert dummy_list.refreshed is True
    assert dummy_detail.shown is entry
    assert notifications and "Citekeys unified" in notifications[-1]


def test_apply_citekey_unification_skips_file_rename_on_target_conflict(
    tmp_path, monkeypatch
) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._config = Config(pdf_base_dir=str(tmp_path))

    entry = BibEntry(
        key="old_key",
        entry_type="article",
        title="Ice",
        author="Gölles, Thomas",
        year="2025",
        file=":old_key - Ice.pdf:PDF",
    )
    app._entries = [entry]

    old_path = tmp_path / "old_key - Ice.pdf"
    old_path.write_bytes(b"%PDF-1.4 fake")

    target_name = pdf_filename(
        BibEntry(key="Goelles2025", entry_type="article", title="Ice")
    )
    target_path = tmp_path / target_name
    target_path.write_bytes(b"%PDF-1.4 existing")

    class DummyList:
        def __init__(self) -> None:
            self.selected_entry = entry

        def refresh_entries(self, entries) -> None:
            return None

    class DummyDetail:
        def show_entry(self, shown_entry) -> None:
            return None

    notifications: list[str] = []

    def fake_query_one(selector):
        if selector is EntryList:
            return DummyList()
        if selector is EntryDetail:
            return DummyDetail()
        raise AssertionError(f"Unexpected selector: {selector}")

    monkeypatch.setattr(app, "query_one", fake_query_one)
    monkeypatch.setattr(
        app, "notify", lambda message, **kwargs: notifications.append(message)
    )

    app._apply_citekey_unification([(entry, "Goelles2025")])

    assert entry.key == "Goelles2025"
    assert entry.file == ":old_key - Ice.pdf:PDF"
    assert old_path.exists()
    assert target_path.exists()
    assert any("file renames skipped" in msg for msg in notifications)
