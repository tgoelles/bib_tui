# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`bib-tui` is a terminal user interface (TUI) application for browsing and managing BibTeX bibliography files (`.bib`). It is built with [Textual](https://textual.textualize.io/), a Python TUI framework. The project is in early development — `main.py` is currently a stub.

`MyCollection.bib` is a sample BibTeX file used for development/testing.

## Package Manager

This project uses **`uv`** (not pip or poetry). Always use `uv` for dependency management.

```bash
uv sync                  # Install dependencies
uv add <package>         # Add a dependency
uv run python main.py    # Run the app
```

## Running the App

```bash
uv run python main.py
```

## Textual Development

Textual ships with a dev console for live reloading and inspection:

```bash
uv run textual run --dev main.py   # Run with Textual dev tools
uv run textual console             # Open dev console (in separate terminal)
```

## Key Dependencies

- `textual >= 8.0.0` — TUI framework (widgets, layouts, CSS styling, reactive state)
- `textual-dev >= 1.8.0` — Textual development tools (live reload, console)
- Python >= 3.12 (pinned to 3.14 via `.python-version`)

## Architecture Notes

Textual apps follow a component model:

- The entry point (`main.py`) creates and runs a `textual.app.App` subclass
- UI is composed of `Widget` subclasses arranged in a `compose()` method
- Styling is done via Textual CSS (`.tcss` files) or inline CSS strings
- State is managed via `reactive` attributes that trigger automatic re-renders
- Event handling uses `on_*` methods or the `@on` decorator
