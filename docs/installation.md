# Installation

bibtui is a single Python package. It runs anywhere Python 3.12+ does — your
laptop, a remote server over SSH, or an HPC login node.

!!! tip "Why the `--prerelease=allow` / `--pre` flag?"

    bibtui depends on `bibtexparser` v2, which is still published as a beta on
    PyPI. The flag tells your installer to allow it. Once bibtexparser ships a
    stable v2 release, the flag will no longer be needed.

## Recommended — uv

[uv](https://docs.astral.sh/uv/) is the fastest way to install and run bibtui.
It installs the app into an isolated environment in under a second.

```bash
uv tool install --prerelease=allow bibtui
```

Update an existing installation:

```bash
uv tool upgrade bibtui
```

### Try it without installing

`uvx` runs bibtui in a throwaway environment — nothing is installed permanently:

```bash
uvx --prerelease=allow bibtui              # opens the file browser
uvx --prerelease=allow bibtui references.bib
```

## pip

```bash
pip install --pre bibtui
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
