# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.8] — 2026-02-24

### Added
- **Auto-fetch PDF on import** — when the setting is enabled and a PDF base directory is configured, a PDF is automatically fetched after adding an entry via DOI or BibTeX paste.
- **Jump to newly added entry** — after importing via DOI or pasting a BibTeX entry, the table cursor now scrolls to and selects the new entry.
- **Add PDF modal preview** — the Add PDF dialog now shows a file preview before linking.
- **Citekey search filter** — search supports `c:` / `citekey:` / `key:` prefix to filter by citation key.
- **Journal search filter** — search supports `j:` / `journal:` prefix to filter by journal or booktitle.
- **`fresh` dev command** — `just fresh` deletes config files to reproduce the first-run experience.
- **Improved onboarding** — better first-run modal and config initialisation flow.

### Fixed
- `Backspace` now also triggers entry deletion (unified with `Delete`).
- Config-related test fixed.
