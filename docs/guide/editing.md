# Editing & citations

## Editing an entry

Press <kbd>e</kbd> on the selected entry to edit it. bibtui offers two modes,
and you switch between them with <kbd>v</kbd>:

- **Field form** — the same dynamic form as [creating a new
  entry](importing.md#create-a-new-entry): inputs are labelled with the real
  BibTeX field names for the entry's type (required fields marked `*`), and you
  can change the type, edit any field, or add custom ones. Best for quick
  corrections.
- **Raw BibTeX** — edit the entry's BibTeX source directly. Best for power users.

Save with <kbd>Ctrl</kbd>+<kbd>S</kbd>, cancel with <kbd>Esc</kbd>. Remember that
edits live in memory until you write the file with <kbd>w</kbd>. The field form
runs the [same validation](importing.md#what-gets-checked-when-you-write) as
adding a new entry — auto-fixing small issues, flagging others, and blocking on
required fields you clear — except that a field which was *already* empty when
you opened the entry is only flagged, so you can never be trapped editing a
messy entry.

!!! note "Keywords, rating and read state aren't in the form"

    Keywords are managed separately in the [keywords picker](keywords.md)
    (<kbd>k</kbd>), and the rating, read state and priority have their own
    shortcuts — so the edit form leaves them out and never disturbs them.

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
