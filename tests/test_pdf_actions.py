from bibtui.app import BibTuiApp
from bibtui.bib.models import BibEntry
from bibtui.utils.config import Config
from bibtui.widgets.entry_detail import EntryDetail
from bibtui.widgets.entry_list import EntryList
from bibtui.widgets.modals import PdfActionsModal

# ---------------------------------------------------------------------------
# action_pdf_actions_menu / _on_pdf_actions_choice — the `p` chooser
# ---------------------------------------------------------------------------


def test_action_pdf_actions_menu_requires_selected_entry(monkeypatch) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    pushed = []
    notes: list[str] = []

    class DummyList:
        selected_entry = None

    monkeypatch.setattr(app, "query_one", lambda selector: DummyList())
    monkeypatch.setattr(app, "push_screen", lambda *a, **k: pushed.append(a))
    monkeypatch.setattr(app, "notify", lambda message, **kwargs: notes.append(message))

    app.action_pdf_actions_menu()

    assert pushed == []
    assert notes and "No entry selected" in notes[-1]


def test_action_pdf_actions_menu_pushes_modal_with_entry_and_base_dir(
    monkeypatch, tmp_path
) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._config = Config(pdf_base_dir=str(tmp_path))
    entry = BibEntry(key="Smith2023", entry_type="article")

    class DummyList:
        selected_entry = entry

    monkeypatch.setattr(app, "query_one", lambda selector: DummyList())
    pushed = []
    monkeypatch.setattr(
        app, "push_screen", lambda screen, callback=None: pushed.append(screen)
    )

    app.action_pdf_actions_menu()

    assert len(pushed) == 1
    assert isinstance(pushed[0], PdfActionsModal)
    assert pushed[0]._entry is entry


def test_on_pdf_actions_choice_dispatches_to_each_action(monkeypatch) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    calls: list[str] = []
    for name in (
        "action_open_pdf",
        "action_fetch_pdf",
        "action_add_pdf",
        "action_pdf_copy_file",
        "action_pdf_copy_path",
        "action_pdf_delete",
    ):
        monkeypatch.setattr(app, name, lambda _n=name: calls.append(_n))

    for choice, expected in [
        ("open", "action_open_pdf"),
        ("fetch", "action_fetch_pdf"),
        ("add", "action_add_pdf"),
        ("copy_file", "action_pdf_copy_file"),
        ("copy_path", "action_pdf_copy_path"),
        ("delete", "action_pdf_delete"),
    ]:
        app._on_pdf_actions_choice(choice)
        assert calls == [expected]
        calls.clear()


def test_on_pdf_actions_choice_none_is_a_noop(monkeypatch) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    monkeypatch.setattr(app, "action_open_pdf", lambda: (_ for _ in ()).throw(AssertionError))

    app._on_pdf_actions_choice(None)  # must not raise / must not call anything


def test_action_pdf_copy_path(monkeypatch, tmp_path) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    copied: list[str] = []
    notes: list[str] = []

    path = str(tmp_path / "paper.pdf")
    monkeypatch.setattr(app, "_selected_entry_pdf_path", lambda: (None, path))
    monkeypatch.setattr(app, "copy_to_clipboard", lambda value: copied.append(value))
    monkeypatch.setattr(app, "notify", lambda message, **kwargs: notes.append(message))
    monkeypatch.setattr("bibtui.app.copy_to_os_clipboard", lambda text: True)

    app.action_pdf_copy_path()

    assert copied == [path]
    assert notes and "Copied PDF path" in notes[-1]


def test_action_pdf_copy_file(monkeypatch, tmp_path) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    copied_files: list[str] = []
    notes: list[str] = []

    path = str(tmp_path / "paper.pdf")
    monkeypatch.setattr(app, "_selected_entry_pdf_path", lambda: (None, path))
    monkeypatch.setattr(
        app,
        "_copy_pdf_file_to_clipboard",
        lambda value: copied_files.append(value),
    )
    monkeypatch.setattr(app, "notify", lambda message, **kwargs: notes.append(message))

    app.action_pdf_copy_file()

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
            self.shown: BibEntry | None = None

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
