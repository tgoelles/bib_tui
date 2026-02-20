"""Smoke test — runs as a plain Python script, no pytest required.

Verifies that the installed package can mount the app and load entries.
Run with:  python tests/smoketest.py
"""

import asyncio
import sys
from pathlib import Path

from bibtui.app import BibTuiApp
from bibtui.widgets.entry_list import EntryList

BIB = Path(__file__).parent / "bib_examples" / "MyCollection.bib"


async def main() -> None:
    app = BibTuiApp(str(BIB))
    async with app.run_test() as pilot:
        await pilot.pause()

        entry_list = app.query_one(EntryList)
        assert len(entry_list._all_entries) > 0, "No entries loaded"
        assert "MyCollection" in app.title, "Title missing filename"
        print(f"OK  {len(entry_list._all_entries)} entries loaded from {BIB.name}")


if __name__ == "__main__":
    asyncio.run(main())
    print("Smoke test passed.")
    sys.exit(0)
