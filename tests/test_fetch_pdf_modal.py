"""Tests for FetchPDFModal's failure message and the `just_created` flag
that distinguishes "PDF fetch failed for an existing entry" from "the entry
was just added, but its PDF fetch failed" (see BibTuiApp._maybe_auto_fetch).
"""

from bibtui.app import BibTuiApp
from bibtui.bib.models import BibEntry
from bibtui.utils.config import Config
from bibtui.widgets.modals import FetchPDFModal

RAW_ERROR = "Could not fetch PDF:\n  • arXiv: no arXiv ID found\n  • Unpaywall: no direct PDF available"


def _entry() -> BibEntry:
    return BibEntry(key="Smith2023", entry_type="article", doi="10.1/x")


def test_format_fetch_error_default_title() -> None:
    modal = FetchPDFModal(_entry(), "/tmp/pdfs")

    message = modal._format_fetch_error(RAW_ERROR)

    assert message.startswith("Could not fetch PDF for this entry.")
    assert "arXiv: no arXiv ID found" in message
    assert "Unpaywall: no direct PDF available" in message


def test_format_fetch_error_just_created_title() -> None:
    modal = FetchPDFModal(_entry(), "/tmp/pdfs", just_created=True)

    message = modal._format_fetch_error(RAW_ERROR)

    assert message.startswith("Added 'Smith2023', but its PDF could not be fetched.")
    assert "arXiv: no arXiv ID found" in message


def test_maybe_auto_fetch_marks_fetch_as_just_created(monkeypatch) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._config = Config(pdf_base_dir="/tmp/pdfs", auto_fetch_pdf=True)
    calls = []
    monkeypatch.setattr(
        app,
        "_do_fetch_pdf",
        lambda entry, confirmed, **kw: calls.append((entry, confirmed, kw)),
    )

    entry = _entry()
    app._maybe_auto_fetch(entry)

    assert calls == [(entry, True, {"just_created": True})]


def test_manual_fetch_pdf_does_not_mark_just_created(monkeypatch) -> None:
    app = BibTuiApp("tests/bib_examples/MyCollection.bib")
    app._config = Config(pdf_base_dir="/tmp/pdfs")
    pushed = []
    monkeypatch.setattr(
        app, "push_screen", lambda screen, callback=None: pushed.append(screen)
    )

    app._do_fetch_pdf(_entry(), True)

    assert len(pushed) == 1
    assert pushed[0]._just_created is False
