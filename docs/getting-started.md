# Getting started

This page walks you from launching bibtui to the things you'll do every day:
search, read, tag, and fetch PDFs.

## Launch

```bash
bibtui MyCollection.bib
```

If you omit the file, bibtui opens a built-in file browser so you can pick one —
or browse to a new location. Recently opened files are listed for quick access.

### First run

The first time you start bibtui, a short onboarding wizard pre-fills sensible
defaults for:

- your **PDF directory** (where fetched PDFs are saved),
- your **Downloads folder** (used when attaching an existing PDF), and
- an **email for Unpaywall** (used only for rate-limiting — no registration).

You can change any of these later from the [settings](configuration.md) screen.

## The layout

![The bibtui library view](assets/img/library.svg){ loading=lazy }

- **Left** — a sortable table of your entries. The first columns are compact
  status icons: read state (`◉`), priority (`!`), a local-PDF indicator (`◫`),
  and a link (`🔗`) when the entry has a URL.
- **Right** — the detail pane for the selected entry: its fields, keywords, a
  formatted citation preview, and PDF actions.
- **Bottom** — the footer shows the most common key bindings.

Move through the list with the arrow keys (or the mouse). The detail pane
updates as you go.

## Everyday actions

| You want to…                       | Press                                   |
| ---------------------------------- | --------------------------------------- |
| Search                             | <kbd>s</kbd>                             |
| Edit the selected entry            | <kbd>e</kbd>                             |
| Edit keywords                      | <kbd>k</kbd>                             |
| Import a new entry by DOI          | <kbd>d</kbd>                             |
| Fetch the PDF for an entry         | <kbd>f</kbd>                             |
| Open the PDF                       | <kbd>Space</kbd>                         |
| Cycle read state (to-read → read)  | <kbd>r</kbd>                             |
| Set a star rating                  | <kbd>1</kbd>–<kbd>5</kbd> (or <kbd>0</kbd>) |
| Save your changes                  | <kbd>w</kbd>                             |
| Show all key bindings              | <kbd>?</kbd>                             |
| Command palette                    | <kbd>Ctrl</kbd>+<kbd>P</kbd>             |

See the full [keybindings reference](keybindings.md) for everything else.

## Saving and backups

bibtui writes changes back to the **same `.bib` file** when you press
<kbd>w</kbd>. Before overwriting, it writes a backup copy, and it applies minimal
diffs so untouched entries stay byte-for-byte identical — keeping your Git
history clean.

## Where to next

<div class="grid cards" markdown>

-   :material-magnify: __[Searching your library](guide/search.md)__ — the field
    prefixes that make a big library feel small.

-   :material-file-download: __[Fetching PDFs](guide/pdfs.md)__ — how the
    automatic PDF download works and where files go.

-   :material-source-branch: __[Working as a team](collaboration.md)__ — share a
    library with your group using Git.

</div>
