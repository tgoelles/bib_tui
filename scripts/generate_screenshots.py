#!/usr/bin/env python3
"""Generate the documentation screenshots from the live application.

This drives the real ``BibTuiApp`` headlessly (via Textual's test harness) over
the example library in ``tests/bib_examples/MyCollection.bib`` and saves crisp
SVG screenshots into ``docs/assets/img/``. Because the images are produced from
the running app, they never drift from the actual UI — the docs workflow
regenerates them on every deploy.

Run locally with::

    uv run python scripts/generate_screenshots.py
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path

from textual.widgets import DataTable, Input

from bibtui.app import BibTuiApp
from bibtui.bib import parser
from bibtui.pdf.paths import parse_jabref_path
from bibtui.widgets.entry_detail import EntryDetail
from bibtui.widgets.entry_list import EntryList
from bibtui.widgets.modals import (
    DOIModal,
    HelpModal,
    KeywordsModal,
    SettingsModal,
)

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_BIB = ROOT / "tests" / "bib_examples" / "MyCollection.bib"
OUT_DIR = ROOT / "docs" / "assets" / "img"

# A roomy terminal so the detail pane and all table columns are visible.
TERM_SIZE = (200, 80)

# An action mutates the app before a screenshot; ``None`` means capture as-is.
Action = Callable[["BibTuiApp", object], Awaitable[None]]


def _seed_pdf_dir() -> str:
    """Create placeholder PDFs so entries with a ``file`` field show the PDF icon."""
    pdf_dir = Path(tempfile.mkdtemp(prefix="bibtui-shots-"))
    for entry in parser.load(str(SAMPLE_BIB)):
        if not entry.file:
            continue
        name = os.path.basename(parse_jabref_path(entry.file))
        if not name:
            continue
        if not name.lower().endswith(".pdf"):
            name += ".pdf"
        try:
            (pdf_dir / name).write_bytes(b"%PDF-1.4\n%demo\n")
        except OSError:
            continue
    return str(pdf_dir)


def _make_app(theme: str, pdf_dir: str) -> BibTuiApp:
    app = BibTuiApp(str(SAMPLE_BIB))
    # Pin everything that would otherwise depend on the developer's real config,
    # so screenshots are identical on every machine and in CI.
    app._first_run = False
    app._config.theme = theme
    app._config.pdf_base_dir = pdf_dir
    app._config.pdf_download_dir = str(Path.home() / "Downloads")
    app._config.unpaywall_email = "you@university.edu"
    app._config.openalex_api_key = ""
    app._config.default_citation_style = "copernicus-publications"
    return app


async def _capture(
    theme: str, shots: list[tuple[str, Action | None]], pdf_dir: str
) -> None:
    """Open the app under *theme* and save each requested shot.

    *shots* is a list of ``(filename, action)`` pairs. ``action`` is either
    ``None`` (capture the main view) or an async callable that mutates the app
    before the screenshot is taken.
    """
    app = _make_app(theme, pdf_dir)
    async with app.run_test(size=TERM_SIZE) as pilot:
        await pilot.pause()
        await pilot.pause()
        for filename, action in shots:
            if action is not None:
                await action(app, pilot)
                await pilot.pause()
            app.save_screenshot(str(OUT_DIR / filename))
            # Reset to a clean main view between modal shots.
            while app.screen is not app.screen_stack[0]:
                app.pop_screen()
            await pilot.pause()


async def _search(app: BibTuiApp, pilot) -> None:
    entry_list = app.query_one(EntryList)
    search = app.query_one("#search-input", Input)
    search.focus()
    await pilot.pause()
    search.value = "a:goelles"
    # Mirror what typing does so the table re-filters.
    entry_list.search_text = search.value
    await pilot.pause()
    # Move the cursor to the first match so the detail pane follows the filter.
    app.query_one(DataTable).move_cursor(row=0)
    app.query_one(EntryDetail).show_entry(entry_list.selected_entry)
    await pilot.pause()


async def _help(app: BibTuiApp, pilot) -> None:
    await app.push_screen(HelpModal())


async def _keywords(app: BibTuiApp, pilot) -> None:
    entry = app.query_one(EntryList).selected_entry
    assert entry is not None
    all_kws, kw_counts = app._all_keywords()
    await app.push_screen(KeywordsModal(entry, all_kws, kw_counts))


async def _settings(app: BibTuiApp, pilot) -> None:
    await app.push_screen(SettingsModal(app._config))


async def _doi(app: BibTuiApp, pilot) -> None:
    await app.push_screen(DOIModal())
    await pilot.pause()
    app.screen.query_one("#doi-input", Input).value = "10.5194/tc-17-1123-2023"


async def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pdf_dir = _seed_pdf_dir()

    # Hero + feature shots in the primary dark theme.
    await _capture(
        "catppuccin-mocha",
        [
            ("library.svg", None),
            ("search.svg", _search),
            ("keywords.svg", _keywords),
            ("help.svg", _help),
            ("settings.svg", _settings),
            ("doi-import.svg", _doi),
        ],
        pdf_dir,
    )

    # Theme gallery — same library, different looks.
    await _capture("nord", [("theme-nord.svg", None)], pdf_dir)
    await _capture("catppuccin-latte", [("theme-light.svg", None)], pdf_dir)
    await _capture("gruvbox", [("theme-gruvbox.svg", None)], pdf_dir)

    print(f"Wrote screenshots to {OUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
