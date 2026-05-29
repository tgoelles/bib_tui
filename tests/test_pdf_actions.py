from bibtui.app import BibTuiApp
from bibtui.bib.models import BibEntry
from bibtui.utils.config import Config
from bibtui.widgets.entry_detail import EntryDetail
from bibtui.widgets.entry_list import EntryList
from bibtui.widgets.modals import PDFActionsModal


def test_action_pdf_actions_opens_modal_when_local_pdf_exists(tmp_path) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._config = Config(pdf_base_dir=str(tmp_path))

    entry = BibEntry(key="k1", entry_type="article", file=":k1.pdf:PDF")
    app._entries = [entry]
    (tmp_path / "k1.pdf").write_bytes(b"%PDF-1.4 fake")

    class DummyList:
        selected_entry = entry

    captured: dict[str, object] = {}

    def fake_query_one(selector):
        if selector is EntryList:
            return DummyList()
        raise AssertionError(f"Unexpected selector: {selector}")

    def fake_push_screen(screen, callback):
        captured["screen"] = screen
        captured["callback"] = callback

    app.query_one = fake_query_one  # type: ignore[method-assign]
    app.push_screen = fake_push_screen  # type: ignore[method-assign]

    app.action_pdf_actions()

    assert isinstance(captured.get("screen"), PDFActionsModal)


def test_on_pdf_action_selected_copy_path(monkeypatch, tmp_path) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    copied: list[str] = []
    notes: list[str] = []

    monkeypatch.setattr(app, "copy_to_clipboard", lambda value: copied.append(value))
    monkeypatch.setattr(app, "notify", lambda message, **kwargs: notes.append(message))

    path = str(tmp_path / "paper.pdf")
    app._on_pdf_action_selected("k1", path, "copy-path")

    assert copied == [path]
    assert notes and "Copied PDF path" in notes[-1]


def test_on_pdf_action_selected_copy_file(monkeypatch, tmp_path) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    copied_files: list[str] = []
    notes: list[str] = []

    monkeypatch.setattr(
        app,
        "_copy_pdf_file_to_clipboard",
        lambda value: copied_files.append(value),
    )
    monkeypatch.setattr(app, "notify", lambda message, **kwargs: notes.append(message))

    path = str(tmp_path / "paper.pdf")
    app._on_pdf_action_selected("k1", path, "copy-file")

    assert copied_files == [path]
    assert notes and "Copied PDF file to clipboard" in notes[-1]


def test_copy_pdf_file_to_clipboard_uses_wl_copy_on_linux(
    monkeypatch, tmp_path
) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    calls: list[tuple[list[str], bytes | None, bool]] = []

    monkeypatch.setattr("bibtui.app.platform.system", lambda: "Linux")
    monkeypatch.setattr(
        "bibtui.app.shutil.which",
        lambda name: "/usr/bin/wl-copy" if name == "wl-copy" else None,
    )

    def fake_run(args, input=None, check=False, **kwargs):
        calls.append((list(args), input, check))

    monkeypatch.setattr("bibtui.app.subprocess.run", fake_run)

    app._copy_pdf_file_to_clipboard(str(pdf_path))

    expected_uri = pdf_path.resolve().as_uri()
    assert calls == [
        (
            ["/usr/bin/wl-copy", "--type", "text/uri-list"],
            f"{expected_uri}\n".encode("utf-8"),
            True,
        )
    ]


def test_copy_pdf_file_to_clipboard_requires_tool_on_linux(
    monkeypatch, tmp_path
) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    monkeypatch.setattr("bibtui.app.platform.system", lambda: "Linux")
    monkeypatch.setattr("bibtui.app.shutil.which", lambda _name: None)

    try:
        app._copy_pdf_file_to_clipboard(str(pdf_path))
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "wl-copy" in str(exc) or "xclip" in str(exc)


def test_do_delete_pdf_removes_file_and_unlinks_entry(tmp_path, monkeypatch) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._config = Config(pdf_base_dir=str(tmp_path))

    entry = BibEntry(key="k1", entry_type="article", file=":k1.pdf:PDF")
    app._entries = [entry]
    app._dirty = False

    pdf_path = tmp_path / "k1.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    class DummyList:
        def __init__(self) -> None:
            self.selected_entry = entry
            self.refreshed: list[BibEntry] = []

        def refresh_row(self, refreshed_entry: BibEntry) -> None:
            self.refreshed.append(refreshed_entry)

    class DummyDetail:
        def __init__(self) -> None:
            self.shown = None

        def show_entry(self, shown_entry: BibEntry | None) -> None:
            self.shown = shown_entry

    dummy_list = DummyList()
    dummy_detail = DummyDetail()
    notes: list[str] = []

    def fake_query_one(selector):
        if selector is EntryList:
            return dummy_list
        if selector is EntryDetail:
            return dummy_detail
        raise AssertionError(f"Unexpected selector: {selector}")

    monkeypatch.setattr(app, "query_one", fake_query_one)
    monkeypatch.setattr(app, "notify", lambda message, **kwargs: notes.append(message))

    app._do_delete_pdf(entry.key, str(pdf_path))

    assert not pdf_path.exists()
    assert entry.file == ""
    assert app._dirty is True
    assert dummy_list.refreshed == [entry]
    assert dummy_detail.shown is entry
    assert notes and "Deleted PDF and unlinked" in notes[-1]


def test_action_copy_citation_copies_rendered_preview(monkeypatch) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    entry = BibEntry(key="k1", entry_type="article")
    copied: list[str] = []
    notes: list[str] = []

    class DummyList:
        selected_entry = entry

    class DummyDetail:
        def citation_preview_text(self) -> str:
            return "Doe, J.: Demo title, 2024."

    def fake_query_one(selector):
        if selector is EntryList:
            return DummyList()
        if selector is EntryDetail:
            return DummyDetail()
        raise AssertionError(f"Unexpected selector: {selector}")

    monkeypatch.setattr(app, "query_one", fake_query_one)
    monkeypatch.setattr(app, "copy_to_clipboard", lambda value: copied.append(value))
    monkeypatch.setattr(app, "notify", lambda message, **kwargs: notes.append(message))

    app.action_copy_citation()

    assert copied == ["Doe, J.: Demo title, 2024."]
    assert notes and "Copied citation: k1" in notes[-1]


def test_action_copy_citation_warns_when_preview_unavailable(monkeypatch) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    entry = BibEntry(key="k1", entry_type="article")
    notes: list[str] = []

    class DummyList:
        selected_entry = entry

    class DummyDetail:
        def citation_preview_text(self) -> str:
            return ""

    def fake_query_one(selector):
        if selector is EntryList:
            return DummyList()
        if selector is EntryDetail:
            return DummyDetail()
        raise AssertionError(f"Unexpected selector: {selector}")

    monkeypatch.setattr(app, "query_one", fake_query_one)
    monkeypatch.setattr(app, "notify", lambda message, **kwargs: notes.append(message))

    app.action_copy_citation()

    assert notes and "Citation preview unavailable" in notes[-1]
