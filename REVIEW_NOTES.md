# Branch review — `tog_pdf_doi` (PDF import, .bib import, chooser/footer rework)

Reviewed: 11 commits vs `main`, +3413/-46 lines. Baseline is **green**:
`uv run ruff check src/` passes, `uv run pytest -m "not network" -q` → 437 passed.
Keep it that way — every item below must end with both still green.

Work through the sections in order; **P1 is user-visible breakage, everything
else is cleanup.** Do not refactor beyond what's listed.

---

## P1 — Stale user docs (actively wrong, ship-blocking) — DONE

`d` used to be "import by DOI" at top level. On this branch `d` opens the online
documentation, and DOI import moved to `n` → `d`. Published docs still tell users
to press `d` to import a DOI, so following them now opens a browser.

1. **`docs/guide/importing.md`** — the main importing guide, never updated:
   - Line 3: "There are **three** ways to add an entry" → now five
     (manually, DOI, PDF, `.bib` file, paste).
   - Lines 70 + 76: "Press <kbd>d</kbd>, paste a DOI…" → must become
     `n` then `d`.
   - "Paste raw BibTeX" section: still only mentions <kbd>Ctrl</kbd>+<kbd>V</kbd>
     (still correct — auto-detect). Add that it's also `n` → `v`.
   - **No section at all** for "Import from PDF" (`n` → `p`) or
     "Import .bib File" (`n` → `b`). Both need one, matching the depth of the
     existing "Import by DOI" section. Content to draw from: the `[Unreleased]`
     entries in `CHANGELOG.md` describe both features accurately.
   - The "Cite-key conflicts" section is still accurate — leave it.
2. **`docs/getting-started.md`** line 49: table row
   `| Import a new entry by DOI | <kbd>d</kbd> |` → `<kbd>n</kbd>` then
   `<kbd>d</kbd>`. Consider adding rows for import-from-PDF and import-.bib.
3. **`README.md`** line 42: "**Import by DOI** — paste a DOI…" — extend the
   feature bullets to mention PDF import and `.bib` import (they're headline
   features of this branch and the README lists far smaller ones).
4. `docs/guide/editing.md`'s <kbd>v</kbd> reference is **fine** (still
   toggle-view at app level, only hidden from the footer). Don't touch it.

---

## P2 — Code duplication (the main ask) — DONE (2a, 2b, 2c, 2d, 2e all addressed)

### 2a. Three near-identical file-picker modals — `src/bibtui/widgets/modals.py`

| Class                    | Line | Purpose                            |
| ------------------------ | ---- | ---------------------------------- |
| `AddPDFModal`          | 1797 | pick one PDF to attach to an entry |
| `PdfImportPickerModal` | 2313 | pick many PDFs to import           |
| `ImportBibPickerModal` | 3032 | pick one`.bib` file to import    |

They share the same skeleton: `_download_dir` + `~/Downloads` fallback, `_scan()`
globbing a directory sorted by mtime, a hint line, a filter `Input`, a list, an
`on_key` doing Down/Up focus hand-off + Space-preview + `x`-confirm, and a
preview method. Concretely:

- **`_refresh_list` is byte-identical** between `AddPDFModal` (1891) and
  `ImportBibPickerModal` (3124).
- **The size/age row label is triplicated** — the `1048576` MB/KB block at
  lines **1898, 2426, 3131**, each followed by the same
  `f"{p.name}  [dim]{size_str}  {age}[/dim]"`.
- **`_scan` is triplicated** (1870, 2388, 3104) — differs only in glob pattern
  (`*.pdf`/`*.bib`), hint element id, and the noun in the hint string.
- **`on_key` is triplicated** (1915, 2406-ish, 3148) — the
  Down/Up/Space/`x` block is the same logic in all three.
- **`_preview_selected`/`_preview_highlighted`** — same body, different error
  sink (`#add-error` / `#pip-error` / `#ibp-error`).
- **`_on_filter`** — same substring filter in all three.

**Suggested fix (conservative):** extract a shared mixin or small base class in
`modals.py` — e.g. `_FileBrowseMixin` — holding `_download_dir` handling,
`_scan()` (parameterised by a `_GLOB = "*.pdf"` class attr and a hint noun),
the row-label helper (`_file_row_label(path) -> str`, next to the existing
module-level `_format_age` at line 69), `_on_filter`, and the shared `on_key`
branches. Leave each subclass owning only what genuinely differs: its widget
ids, its list widget (`ListView` vs `SelectionList`/`PdfSelectionList`), and
its confirm semantics.

**Constraints:** all three modals have Pilot tests that poke private attrs —
`tests/test_pdf_import_picker.py` uses `modal._filtered`, `modal._all_pdfs`,
`modal._selected`, `modal._download_dir`; `tests/test_bib_file_picker.py` uses
`modal._filtered`, `modal._all_files`, `modal._download_dir`. Either keep those
attribute names or update the tests in the same commit. Note the pointless
naming split: `_all_pdfs` vs `_all_files` for the same concept — unify on
`_all_files` while you're in there.

### 2b. Two near-identical report modals

`PdfImportReviewModal` (2523) and `BibFileImportReviewModal` (2783) both render a
read-only `OptionList` of ✓/✗ rows and a single "Import N Entries" button:

- The ✓/✗ + `self.app.current_theme.success` / `.error` `Text` construction is
  duplicated at **2656/2659/2664** and **2888/2891**.
- The "Import N Entr(y|ies)" label logic is duplicated at **2687** and **2875**.
- The matched-row format `"{title_short} ({authors_short}, {year or '?'})"`
  appears in both.

**Suggested fix:** two small module-level helpers next to `_format_age`, e.g.
`_report_row(text: str, ok: bool, theme) -> Text` and
`_import_button_label(n: int) -> str`. A shared base class is probably
over-engineering here (one modal scans in a background thread, the other is
synchronous) — helpers are enough.

### 2c. Three DOI normalizers

- `src/bibtui/utils/doi.py:normalize_doi` (new this branch — strips prefix **and**
  lowercases)
- `src/bibtui/pdf/fetcher.py:_normalized_doi` (line 359 — same regex, **no**
  lowercase)
- `src/bibtui/bib/validate.py:_normalize_doi` (line 91 — different regex constant,
  no lowercase)

**Suggested fix:** make `utils/doi.py` the single home. Give it an explicit
`lower: bool = True` parameter (or a second `strip_doi_url_prefix()` helper) and
have the other two call it. **Be careful:** `fetcher._normalized_doi` deliberately
preserves case for the OpenAlex URL filter and `validate._normalize_doi` feeds an
auto-fix written back into the user's `.bib` — do not start lowercasing DOIs in
those two paths. If keeping behaviour identical makes the merge awkward, just
have both delegate the prefix-stripping and keep casing local.

### 2d. Duplicated test scaffolding

`tests/test_bib_file_import.py` and `tests/test_pdf_import_app.py` contain a
**49-line byte-identical block** (`DummyDataTable`, `DummyList`, `DummyDetail`,
`_wire_dummies`). `tests/test_library_fetch.py` and `tests/test_pdf_actions.py`
have their own older variants of the same idea. There is **no `tests/conftest.py`**.

**Suggested fix:** add `tests/conftest.py` with the dummy widgets and a
`wire_dummies` fixture/helper; import it from the two new files. Optionally
migrate the two older files too — but only if the suite stays green.

Also: `tests/test_pdf_import_app.py` repeats the literal
`"tests/bib_examples/MyCollection.bib"` **14 times** inline, while every sibling
test file defines a module-level `BIB = …` constant. Make it consistent.

### 2e. Function-level imports

The branch added function-body imports that have no cycle justification:
`from bibtui.utils.doi import normalize_doi` ×4 (`app.py` 533 & 590,
`modals.py` 2616 & 2822) and `from bibtui.pdf.import_scan import ImportStatus` ×3.
`utils/doi.py` imports only `re`, so it is safe at module top level.
Move those to the top of each file. (The `bibtui.pdf.fetcher` /
`bibtui.pdf.paths` lazy imports inside methods match the existing house style for
heavy modules — leave those alone.)

**Correction found while implementing:** the `ImportStatus`/`process_pdf`
imports were *not* moved to module level after all. `bibtui.pdf.import_scan`
itself does `from bibtui.bib.doi import fetch_by_doi` at its own top level,
and `bib/doi.py` does `from habanero import Crossref` at its top level
(~0.1s import) — so hoisting `ImportStatus` in `modals.py` would make every
app startup pay for importing `habanero`, which today only happens lazily
when DOI import (or PDF import) is actually used. That's exactly the "heavy
module" lazy-import convention this same item told you to leave alone for
`fetcher`/`paths` — it just wasn't obvious until tracing `import_scan`'s own
imports. Left those four `from bibtui.pdf.import_scan import ...` lines as
local imports; only the `normalize_doi` imports (genuinely cheap, `re`-only)
were hoisted.

**Resolution:** 2a–2e all done — see `git log` on this branch for the
commits, or diff against the version of this file before this section was
edited. Kept green throughout (`ruff check src/`, `pytest -m "not network"`
→ 437 passed).

---

## P3 — Gaps between the design and the code

1. **CrossRef rate limiting was never implemented.** The original issue listed
   "rate limiting for CrossRef queries (avoid hammering the API on large
   folders)" as in-scope, and the plan specified a hardcoded ~0.2 s pause between
   lookups. `PdfImportReviewModal._scan` (modals.py ~2614) loops over every PDF
   with no delay — a 200-PDF folder fires 200 back-to-back requests.
   **Fix:** add a module-level constant (e.g. `_CROSSREF_PAUSE_SECONDS = 0.2`) and
   `time.sleep` it in the worker loop, but only after rows that actually hit the
   network (`MATCHED` / `LOOKUP_FAILED`) — skip it for `NO_IDENTIFIER`,
   `AMBIGUOUS`, `ALREADY_PRESENT`. It runs in a `@work(thread=True)` worker, so
   sleeping is safe. Guard the tests against wall-clock cost by monkeypatching
   the constant or the sleep.
   *Related, optional:* `bib/doi.py:fetch_by_doi` builds a fresh `Crossref()` per
   call and sets no `mailto`, so we're in CrossRef's anonymous pool. Adding a
   mailto (from `Config.unpaywall_email`, which the user already sets) would be a
   good follow-up — but that's a behaviour change, so raise it, don't silently do it.
2. **`parser.load()` runs on the UI thread.** `app.py:_on_bib_file_picked` (565)
   parses the chosen `.bib` synchronously. Every comparable flow on this branch
   (`PdfImportReviewModal._scan`, `FetchPDFModal._do_fetch`, `BatchFetchPDFModal`)
   uses `@work(thread=True)`. A large merge file will visibly freeze the UI.
   Low priority — parsing is fast — but note it, or background it for consistency.
3. **`identify.py` may flag ordinary papers as ambiguous.** `extract_identifier`
   (identify.py 75-133) returns `ambiguous=True` as soon as page 1-2 contain two
   distinct DOI strings — which is common (article DOI + publisher boilerplate or
   a reference list starting on page 2). Spec did say "flag rather than guess", so
   this is not a bug, but it should be **validated against a handful of real
   journal PDFs** before release. If the hit rate is poor, the cheapest
   improvement is to prefer the most frequently occurring DOI, or to try
   candidates against CrossRef in order rather than refusing outright.
4. **`no_text=True` is overloaded.** identify.py returns it both for "scanned PDF,
   no text layer" and for "corrupt/encrypted/unreadable file" (line 84), and
   `import_scan.py` renders both as *"No extractable text (scanned PDF?)"* —
   misleading for a corrupt file. Add a second flag or a distinct message.
5. **`identify.py` only matches new-style arXiv IDs.** `_ARXIV_RE` (line 36)
   accepts `\d{4}\.\d{4,5}` only, while `pdf/fetcher.py:_arxiv_id` (173) also
   handles old-style (`hep-th/9711200`). Pre-2007 preprints therefore won't be
   recognised on import. Document the limit or widen the regex.

---

## P4 — Consistency nits

1. **`BibFileImportReviewModal` has no preview and no nav hint.**
   `PdfImportReviewModal` shows a `#import-nav-hint` Static and binds Space to
   preview the highlighted row's source file; the `.bib` review modal has
   neither. Arguably fine (its rows are entries, not files) — but the *source
   `.bib` file* could be opened with Space, and the user asked twice for these
   flows to feel the same. Decide and make it deliberate; if leaving it out, say
   so in the class docstring.
2. **Error notifications print full absolute paths** (`app.py` 566, 570:
   `f"Could not parse {path}"`). Elsewhere the app shows basenames. Use
   `os.path.basename(path)` for readability.
3. **`ARG002` unused `event` args** on several `@on(...)` handlers — pre-existing
   house style (`FilePickerModal.on_recent_selected` does it too) and not flagged
   by the project's ruff config. **Leave alone.**

---

---

## Verification for every change

```
uv run ruff check src/
uv run pytest -m "not network" -q      # expect 437 passed (more if tests added)
uv run python tests/smoketest.py
```

For the docs changes, also skim `mkdocs build --strict` if docs deps are
installed (`uv sync --group docs`), since the docs CI runs with `--strict`.
