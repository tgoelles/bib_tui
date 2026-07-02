# Importing references

You rarely type BibTeX by hand in bibtui. There are three ways to add an
entry, and all of them refuse to create duplicate cite keys.

## Create a new entry

Press <kbd>n</kbd> to open the new-entry form. Pick the entry type (article,
book, inproceedings, …) and the form shows that type's fields under their real
BibTeX names: **required fields are marked with `*`** and listed in the hint
under the type selector, then `doi` and `note`, then the remaining optional
fields.

The cursor starts in the first field (usually the author) rather than the cite
key, because the key is filled in for you: it's suggested automatically from the
author and year (in `AuthorYear` form) and shown dimmed and italic while
auto-generated, so you can see at a glance that it will follow the author/year.
Type your own key any time to take over; the styling switches to a normal key
and stops auto-updating.

Every new entry is stamped with a `date-added` timestamp automatically, so the
**Added** column and date sorting work straight away — you never enter it by
hand. When you save, the entry is validated with the BibTeX parser first, so a
malformed cite key or field can't be written to your `.bib` file.

Switching the entry type re-shapes the form to match the new type while keeping
any values you already typed.

!!! note "Keywords are managed separately"

    The form doesn't include a keywords field — keywords are curated in the
    [keywords picker](keywords.md) (<kbd>k</kbd>), which lets you reuse the ones
    already in your library. Add the entry first, then press <kbd>k</kbd>.

### Custom fields

Need a field the form doesn't show — `note`, `isbn`, `urldate`, or anything
else? At the bottom of the form, pick one from the **Common field** dropdown or
type any field name and press <kbd>Enter</kbd> (or **Add**). It appears as a new
input you can fill in, and the <kbd>✕</kbd> button removes it again. Any field
name is accepted, so you're never limited to the built-in list.

## Import by DOI

Press <kbd>d</kbd>, paste a DOI, and bibtui fetches the full metadata online and
builds the entry for you.

![Importing an entry by DOI](../assets/img/doi-import.svg){ loading=lazy }

This is the quickest way to add a paper you found in a browser or a reference
list — copy the DOI, press <kbd>d</kbd>, paste, done.

!!! tip "PDFs are fetched automatically"

    With **Auto-fetch PDF on import** enabled (the default), bibtui downloads the
    open-access PDF right after import — so a DOI often becomes a fully-linked
    entry, PDF and all, in one step. It needs a DOI or URL on the entry and a PDF
    directory set. Turn it off in [settings](../configuration.md) if you'd rather
    fetch manually with <kbd>f</kbd>.

## Paste raw BibTeX

If you already have a BibTeX snippet (for example from a publisher's "cite this"
button or Google Scholar), press <kbd>Ctrl</kbd>+<kbd>V</kbd> to paste it
directly as a new entry.

## Cite-key conflicts

Every method checks your library for an existing entry with the same cite key:

- If a different paper already uses the key, bibtui assigns the next free
  lowercase suffix — `Goelles2025`, then `Goelles2025a`, `Goelles2025b`, and so
  on.
- If the key **and title** match an existing entry, the import is rejected as a
  duplicate, so you don't end up with the same paper twice.

## Unify cite keys

Imported references can arrive with inconsistent keys. From the command palette
(<kbd>Ctrl</kbd>+<kbd>P</kbd>) choose **Library: Unify citekeys (AuthorYear)** to
normalise every key to the `AuthorYear` convention. Entries that already match
are left untouched.

!!! warning

    Changing cite keys can break `\cite{...}` references in existing LaTeX
    documents. Run this on a fresh library, or be ready to update your
    manuscripts — and since your `.bib` is under
    [version control](../collaboration.md), you can always review the diff first.
