# Importing references

You rarely type BibTeX by hand in bibtui. There are two fast ways to add an
entry, and both refuse to create duplicate cite keys.

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

Both methods check your library for an existing entry with the same cite key:

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
