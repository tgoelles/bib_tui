# Keywords & tags

Keywords are bibtui's primary way to organise a library by topic. They're stored
in the standard `keywords` BibTeX field, so they travel with your `.bib` file
and work in other tools too.

## The keywords editor

Select an entry and press <kbd>k</kbd> to open the keywords editor.

![The keywords editor](../assets/img/keywords.svg){ loading=lazy }

- The list shows **every keyword in your library**, with the ones on the current
  entry checked.
- Type in the filter box to narrow the list, or to enter a brand-new keyword.
- <kbd>Space</kbd> toggles the highlighted keyword on or off for this entry.
- <kbd>Enter</kbd> adds the keyword you typed.
- <kbd>↑</kbd> / <kbd>↓</kbd> move between the filter and the list.
- <kbd>⌫</kbd> on a highlighted keyword deletes it **from every entry** — a quick
  way to clean up a typo or merge a duplicate tag.
- <kbd>Ctrl</kbd>+<kbd>S</kbd> saves your changes; <kbd>Esc</kbd> cancels.

## Filtering by topic

Once entries are tagged, the `k:` search prefix turns your keywords into a topic
filter. For example, `k:albedo` shows only entries tagged with that keyword. See
[Searching your library](search.md) for the full syntax.

## Reading workflow

Keywords pair naturally with bibtui's lightweight reading-status fields, which
all live in your `.bib` file:

- **Read state** — cycle to-read → skimmed → read with <kbd>r</kbd>.
- **Priority** — cycle high → medium → low with <kbd>p</kbd>.
- **Star rating** — press <kbd>1</kbd>–<kbd>5</kbd>, or <kbd>0</kbd> to clear.

Combine them with search and sorting to answer questions like "what high-priority
papers on sea ice have I not read yet?" — tag with `k:`, sort by priority, and
scan the read-state column.
