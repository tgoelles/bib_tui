# Installation

bibtui is a single Python package. It runs anywhere Python 3.12+ does — your
laptop, a remote server over SSH, or an HPC login node.

!!! warning "Platform support"

    bibtui is actively developed and tested on **Linux** and **macOS**. It is
    pure Python on top of [Textual](https://textual.textualize.io/), which
    itself supports Windows Terminal, so it should work on **Windows** in
    principle — but it has not yet been tested there, and hasn't seen the same
    real-world mileage as Linux/macOS. If you try it on Windows, please
    [open an issue](https://github.com/tgoelles/bib_tui/issues) with whatever
    you find, good or bad.

## Recommended — uv

[uv](https://docs.astral.sh/uv/) is the fastest way to install and run bibtui.
It installs the app into an isolated environment in under a second.

```bash
uv tool install bibtui
```

Update an existing installation:

```bash
uv tool upgrade bibtui
```

### Try it without installing

`uvx` runs bibtui in a throwaway environment — nothing is installed permanently:

```bash
uvx bibtui              # opens the file browser
uvx bibtui references.bib
```

## pip

```bash
pip install bibtui
```

## Verify

```bash
bibtui --version
```

Then open a library:

```bash
bibtui references.bib
```

…or just run `bibtui` and pick a file from the built-in browser.

## Staying up to date

bibtui checks PyPI once a day and tells you when a newer version is available.
You can also trigger a check on demand from the command palette
(<kbd>Ctrl</kbd>+<kbd>P</kbd> → **Check for updates**).
