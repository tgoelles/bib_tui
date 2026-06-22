# Editing & citations

## Editing an entry

Press <kbd>e</kbd> on the selected entry to edit it. bibtui offers two modes,
and you switch between them with <kbd>v</kbd>:

- **Field form** — a labelled form with one input per field. Best for quick
  corrections.
- **Raw BibTeX** — edit the entry's BibTeX source directly. Best for power users
  and for fields the form doesn't surface.

Save with <kbd>Ctrl</kbd>+<kbd>S</kbd>, cancel with <kbd>Esc</kbd>. Remember that
edits live in memory until you write the file with <kbd>w</kbd>.

## Deleting an entry

Press <kbd>Delete</kbd> (or <kbd>Backspace</kbd>) and confirm. Deletion only
takes effect in your file when you save.

## Citation previews

The detail pane renders a **formatted citation** for the selected entry using a
[CSL](https://citationstyles.org/) style. bibtui loads styles from
`~/.config/bibtui/csl/` and seeds common ones on first run — Copernicus, APA,
IEEE, Vancouver, Chicago author-date, and Harvard. See
[configuration](../configuration.md#citation-styles-csl) for adding more.

## Copying

bibtui has a copy shortcut for every common need:

| Shortcut                                   | Copies                                            |
| ------------------------------------------ | ------------------------------------------------- |
| <kbd>Ctrl</kbd>+<kbd>C</kbd>               | selected text, or the cite key if nothing is focused |
| <kbd>Shift</kbd>+<kbd>C</kbd>             | the formatted citation in your current CSL style  |
| <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>C</kbd> | the full BibTeX entry                          |
| <kbd>Ctrl</kbd>+<kbd>Y</kbd>              | the full BibTeX entry (terminal-safe fallback)    |

!!! info "Clipboard over SSH"

    bibtui copies via the OSC 52 terminal escape sequence, so copying works even
    over SSH — provided your terminal supports it (most modern ones do). If a
    copy doesn't land, <kbd>Ctrl</kbd>+<kbd>Y</kbd> is the most compatible
    fallback.
