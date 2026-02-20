from __future__ import annotations
import sys
import os


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: bib-tui <file.bib>")
        sys.exit(1)

    bib_path = sys.argv[1]

    if not os.path.exists(bib_path):
        print(f"Error: file not found: {bib_path}")
        sys.exit(1)

    from bib_tui.app import BibTuiApp
    BibTuiApp(bib_path).run()


if __name__ == "__main__":
    main()
