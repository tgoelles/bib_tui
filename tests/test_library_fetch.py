import os

from bibtui.app import BibTuiApp
from bibtui.bib.models import BibEntry
from bibtui.utils.config import Config
from bibtui.widgets.entry_detail import EntryDetail
from bibtui.widgets.entry_list import EntryList


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
