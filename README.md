# bibtui

![bibtui logo](https://raw.githubusercontent.com/tgoelles/bib_tui/main/docs/logo/logo2.png)

> A quiet, powerful home for your references.

[![PyPI](https://img.shields.io/pypi/v/bibtui)](https://pypi.org/project/bibtui/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-bibtui-deeppurple)](https://tgoelles.github.io/bib_tui/)
[![Publish](https://github.com/tgoelles/bib_tui/actions/workflows/publish.yml/badge.svg)](https://github.com/tgoelles/bib_tui/actions/workflows/publish.yml)
[![CI](https://github.com/tgoelles/bib_tui/actions/workflows/ci.yml/badge.svg)](https://github.com/tgoelles/bib_tui/actions/workflows/ci.yml)

**bibtui** is a fast, keyboard-driven terminal app for researchers who work with
BibTeX. Open your `.bib` file, search thousands of references instantly, fetch
open-access PDFs with a single keystroke, and track what you've read — without
leaving the terminal. No database, no sync daemon, no account.

📖 **[Read the full documentation →](https://tgoelles.github.io/bib_tui/)**

![bibtui library view](https://raw.githubusercontent.com/tgoelles/bib_tui/main/docs/assets/img/library.png)

## Quick start

```bash
# Run without installing — opens the built-in file browser
uvx --prerelease=allow bibtui

# Or open a specific library directly
uvx --prerelease=allow bibtui myrefs.bib

# Or install permanently
uv tool install --prerelease=allow bibtui
```

> **Why `--prerelease=allow`?** bibtui depends on `bibtexparser` v2, still in
> beta on PyPI. Once it ships a stable v2, the flag is no longer needed.

## What you can do

- **Find anything, instantly** — search title, author, journal, keywords and
  cite key as you type, with field prefixes like `a:`, `t:`, `k:`, `y:`.
- **Download PDFs automatically** — one keystroke fetches the open-access PDF
  from arXiv, Copernicus, OpenAlex or Unpaywall and links it to the entry.
- **Import by DOI** — paste a DOI and the metadata is fetched for you.
- **Organise** — keywords, read states, priorities and star ratings, all stored
  in your `.bib` file.
- **Collaborate with Git** — your library is plain text, so a research group can
  share and review it like code.
  [Learn how →](https://tgoelles.github.io/bib_tui/collaboration/)
- **Run anywhere** — laptop, SSH, or an HPC cluster. Full Textual theming,
  keyboard and mouse.

## Documentation

| Guide | |
| ----- | - |
| [Installation](https://tgoelles.github.io/bib_tui/installation/) | Get bibtui running |
| [Getting started](https://tgoelles.github.io/bib_tui/getting-started/) | The everyday workflow |
| [Searching your library](https://tgoelles.github.io/bib_tui/guide/search/) | Field prefixes and sorting |
| [Fetching PDFs](https://tgoelles.github.io/bib_tui/guide/pdfs/) | Automatic open-access downloads |
| [Working as a team](https://tgoelles.github.io/bib_tui/collaboration/) | Share a library with Git |
| [Configuration](https://tgoelles.github.io/bib_tui/configuration/) | Settings, themes, CSL styles |

## Contributing

Bug reports, ideas and pull requests are welcome — see the
[development guide](https://tgoelles.github.io/bib_tui/development/) and
[open an issue](https://github.com/tgoelles/bib_tui/issues).

## License

MIT — see [LICENSE](LICENSE).
