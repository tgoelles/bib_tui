from __future__ import annotations
import sys
import os


def main() -> None:
    if len(sys.argv) < 2:
        # Try MyCollection.bib in same directory as default
        default = os.path.join(os.path.dirname(__file__), "MyCollection.bib")
        if os.path.exists(default):
            bib_path = default
        else:
            print("Usage: bib-tui <file.bib>")
            sys.exit(1)
    else:
        bib_path = sys.argv[1]

    if not os.path.exists(bib_path):
        print(f"Error: file not found: {bib_path}")
        sys.exit(1)

    from app import BibTuiApp
    BibTuiApp(bib_path).run()


if __name__ == "__main__":
    main()
