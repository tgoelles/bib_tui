# Development

bibtui is open source under the MIT license, and **contributions are welcome** —
whether that's a bug report, a feature idea, or a pull request.

## Issues & pull requests

- :material-bug: **Found a bug or have an idea?**
  [Open an issue](https://github.com/tgoelles/bib_tui/issues). Steps to
  reproduce and your bibtui version (`bibtui --version`) help a lot.
- :material-source-pull: **Want to contribute code?** Pull requests are very
  welcome. For a larger change, opening an issue first to discuss the approach
  saves everyone time.

## Local setup

```bash
git clone https://github.com/tgoelles/bib_tui
cd bib_tui
uv sync
```

Common tasks are wrapped as [`just`](https://github.com/casey/just) recipes —
run `just` on its own to list them. Run the app against the example library:

```bash
just run          # open tests/bib_examples/MyCollection.bib
just run_nofile   # start with the file browser
just dev          # run with Textual live reload while you edit
just fresh        # delete your config to test the first-run experience
```

## Tests and linting

```bash
just test   # uv run pytest -v tests
just lint   # uv run ruff check src/
```

By default pytest skips two groups of tests:

- `network`: tests that make real HTTP requests (CrossRef, Unpaywall, …), which
  can fail when a remote service changes. Run them with `uv run pytest -m network`.
- `slow`: the exhaustive save-integrity sweep that edits every entry in the
  example libraries (about 20 s). Run it with `uv run pytest -m slow`.

CI runs everything except `network` (`uv run pytest -m "not network"`) across
Python 3.12–3.14, so the slow sweep runs there.

The save-integrity tests (`tests/test_save_integrity.py`) edit entries,
save, reload and check that only the edited field changed, both in the data and
in the file text. When you hit a `.bib` layout that breaks saving, add it as an
entry to `tests/bib_examples/edge_cases.bib`; it is then tested with every edit
automatically.

## Working on the docs

The documentation is built with
[Material for MkDocs](https://squidfunk.github.io/mkdocs-material/). The `docs`
recipes install the `docs` dependency group on demand:

```bash
just docs          # serve with live reload at http://127.0.0.1:8000
just docs-build    # build the site into ./site (mkdocs build --strict)
just screenshots   # regenerate the screenshots from the live app
```

Screenshots are generated from the running app so they never go stale. On every
push to `main`, a GitHub Actions workflow runs `just screenshots`' command,
builds the site, and deploys it to GitHub Pages.

## Project conventions

- The `.bib` file is the source of truth — no hidden database, no schema beyond
  BibTeX.
- The non-UI logic is covered by tests; UI code is kept thin.
- bibtui aims at a **focused feature set**. For bulk cleanup, reach for
  [bibtex-tidy](https://github.com/FlamingTempura/bibtex-tidy) or edit the `.bib`
  directly.

Thanks for helping make bibtui better. :material-heart:
