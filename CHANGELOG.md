# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.9] — 2026-02-26

### Added
- **Background update check** — checks PyPI once per day on startup in a non-blocking background thread and notifies when a newer stable release is available.
- **Update-check setting** — new Settings toggle to enable/disable startup update checks (enabled by default).
- **Update metadata persistence** — stores last check time, last notification time, and latest seen version in config under `[updates]`.

### Changed
- **PDF module consolidation** — PDF path helpers and fetch logic are now grouped under `bibtui.pdf`.
- **Settings layout readability** — helper text is shown before each control with clearer spacing between setting groups.

### Fixed
- **Theme consistency in modals** — removed hard-coded Rich color tags from Add PDF / Fetch PDF related messaging so colors follow theme tokens.
- **Safer PDF downloads** — downloads now use atomic temp-file writes and cleanup to avoid leaving partial files.
- **Direct URL fetch robustness** — falls back to GET when HEAD is blocked and validates PDF via content type or PDF magic bytes.
- **Config resilience** — invalid or unreadable config files now fall back to defaults instead of crashing startup.

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
