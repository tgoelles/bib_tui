# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Manual "Check for updates" command** — added a *Check for updates* entry to the command palette (`Ctrl+P`) that queries PyPI immediately for a newer bibtui release, bypassing the once-per-day automatic throttle, and reports the result.

### Fixed

- **Help menu alignment** — keybinding descriptions now line up in a consistent column across every section (the *Other* and *Library actions* sections were previously misaligned).
- **Help menu out-of-date entries** — the help now reflects current commands, including the *Check for updates* library action that was missing.

### Changed

- **Help menu internals** — removed a duplicated, hand-maintained copy of the keybindings reference; the help screen is now rendered from a single source of truth, preventing the two copies from drifting apart.
- **Modal styling** — all dialogs now share a common `_BaseModal` base class for their centered layout, border, background, and padding instead of each repeating the same CSS; individual modals only declare what differs (size, border color). No visual change.

## [0.14.0] - 2026-05-29

### Added

- **Citation preview in entry detail** — added citeproc-py based formatted citation preview with a CSL style selector (currently bundled with `copernicus-publications.csl`).
- **Copy citation shortcut** — added `Shift+C` to copy the currently rendered citation preview while keeping `Ctrl+C` as citekey/default copy behavior.
- **Config-based CSL styles directory** — citation styles now live in `~/.config/bibtui/csl`; on first run bibtui seeds common defaults: Copernicus, APA, IEEE, Vancouver, Chicago (author-date), and Harvard (Cite Them Right).
- **Import citekey conflict handling** — DOI/paste imports now handle existing keys by rejecting same-title duplicates and otherwise assigning the next free lowercase suffix (`a` … `z`, e.g. `Goelles2025a`).

## [0.13.0] - 2026-05-29

### Added

- **PDF actions UI added** - moved  PDF operations into a dedicated collapsible `PDF` section with state-aware disabled actions.
- **Copy PDF action behavior** — copy uses OS file clipboard formats (Linux `wl-copy`/`xclip` URI list, macOS `osascript`, Windows `Set-Clipboard -Path`).

### Fixed

- **Safer OpenAlex DOI fetching** — when a DOI is present but OpenAlex finds no DOI match, PDF fetching no longer falls back to title search, preventing false-positive downloads of wrong PDFs (regression covered with an `inproceedings` DOI case).

## [0.12.4] - 2026-05-04

### Fixed

- **bibtexparser import crash on startup** — removed a runtime type annotation reference to `bibtexparser.model.Library` in the BibTeX parser, preventing `AttributeError: module 'bibtexparser.model' has no attribute 'Library'` on environments where that symbol is absent.

## [0.12.3] - 2026-05-04

Error, release yanked

## [0.12.2] - 2026-05-04

### Changed

- **BibTeX save strategy** — saving now preserves untouched source text and applies minimal diffs instead of rewriting the whole file.
- **Entry update granularity** — changed entries are now patched at field level so unchanged fields in the same entry stay byte-identical whenever possible.
- **Change detection** — entry change detection now uses bibtexparser-derived field maps instead of a hard-coded field tuple; custom / unknown fields in `raw_fields` are handled uniformly without any special-casing.

## [0.12.1] - 2026-05-04

- **From DOI import compatibility** — pinned `httpx` to `<1.0` to avoid runtime breakage with `habanero` when pre-release `httpx 1.0` variants are installed (`get() got an unexpected keyword argument 'params'`).

## [0.12.0] - 2026-05-02

### Added

- **File browser startup mode** — start bibtui without an initial file, using Textual's native file tree to browse and open library files. Includes quick access to recently opened files
- **Icon** -- I made a simple pixel based icon. So you can install it as a TUI with an icon.
- **Optional OpenAlex PDF lookup** — add an OpenAlex API key in Settings to enable an additional PDF fetch source (used before Unpaywall).
- **OpenAlex fetch strategy** — OpenAlex now prefers DOI lookup first and falls back to title search when DOI is missing or unresolved.
- **BibTeX copy shortcut** — added `Ctrl+Shift+C` to copy the currently selected full BibTeX entry, plus `Ctrl+Y` as a terminal-safe fallback.

### Changed

- **PDF fetch success feedback** — success messages now show which provider supplied the PDF (for example OpenAlex, arXiv, Copernicus, Unpaywall, or Direct URL).

### Fixed

- **Theme synching with omarchy** -- now it can sync with any omarchy theme and does it automatically.

## [0.11.6] - 2026-04-01

### Added

- **Copernicus PDF fetching** — PDFs for all `10.5194` publications (preprints and articles) are now fetched directly from copernicus.org using the DOI structure.

### Fixed

- **From DOI — preprint journal** — journal name is now resolved for preprints via Crossref lookup; EGUsphere returns `"EGUsphere"` as a special case.
- **From DOI — preprint year** — year extraction now falls back to the `posted` date field.

## [0.11.0] — 2026-02-27

### Added

- **Table-pane maximize toggle** — press `m` to maximize/restore the entry table pane for focused browsing.
- **Date-added table column** — entry list now includes an `Added` column with normalized date display and sorting support.
- **Library PDF fetch preflight modal** — library-wide fetch now opens a dedicated confirmation modal with an `Overwrite broken links` toggle.
- **Release helper for minor bumps** — added `just minor` to bump, tag, and push minor versions.

### Changed

- **Library fetch workflow** — existing local PDFs are auto-linked before batch fetching missing files.
- **PDF linking behavior** — fetching now re-links an entry to an already existing destination PDF when the stored link is broken.
- **Entry refresh UX** — entry selection is preserved after list refresh operations.
- **Layout behavior** — entry list pane now uses flexible width (`1fr`) for better split behavior.
- **Release task naming** — `just release-patch` was renamed to `just patch`.

### Fixed

- **Date handling consistency** — DOI imports now use centralized date-added timestamp utilities.
- **Regression coverage for dates** — added tests for extracting, parsing, and formatting bibliography date fields.

## [0.10.0] — 2026-02-26

### Added

- **Library-wide PDF fetching** — new command-palette workflow to fetch PDFs for all entries missing local files.
- **Library-wide citekey unification** — new command to normalize citekeys to canonical `AuthorYear` form across the whole library.
- **OpenAlex quick lookup** — `Shift+B` opens OpenAlex for the selected entry from the footer action; search uses title first and falls back to DOI.

### Changed

- **Citekey generation and normalization** — improved canonicalization and collision handling for more consistent keys.
- **Clipboard behavior in context** — `Ctrl+C` now prefers focused text widgets (e.g., raw BibTeX view) and falls back to citekey copy when no text widget is focused.
- **Documentation updates** — README installation/upgrade guidance and help text were updated for the new library and OpenAlex workflows.

### Fixed

- **Raw-view copy usability** — copying selected text now works reliably in non-edit raw BibTeX contexts.
- **Regression coverage expansion** — added tests for library fetch and citekey normalization/unification paths.

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
