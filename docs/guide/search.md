# Searching your library

A reference library is only useful if you can find things in it. bibtui filters
as you type, across a library of thousands, with no indexing step.

Press <kbd>s</kbd> to jump to the search box, type your query, and the table
narrows live. Press <kbd>Enter</kbd> to move into the results, or
<kbd>Esc</kbd> to clear the search.

![Searching by author prefix](../assets/img/search.svg){ loading=lazy }

## Plain text

Type any words to search across **title, author, keywords and cite key** at
once. Multiple words are combined with AND — every word must match somewhere:

```text
glacier melt
```

## Whole words, truncation and phrases

A search word matches **whole words**, like in Web of Science: `ice` finds
"ice" and "ice-sheet", but not "price", "Alice" or "iceberg". Use `*` for any
run of letters, and quotes for a phrase:

```text
ice              # the word "ice" (also in "ice-sheet")
ice*             # words starting with "ice": iceberg, icefield, ice
glacier*         # glacier, glaciers, glacierized
*berg            # words ending in "berg": iceberg
"sea ice"        # the phrase, also written "sea-ice"
t:"ice sheet*"   # "ice sheet", "ice sheets" in the title
```

There is no automatic plural handling: `glacier` doesn't find "glaciers", so
add a `*` when you want both.

- Punctuation between words is flexible: `ice-sheet` also finds "ice sheet",
  and `a:o'brien` finds "O’Brien" with a typographic apostrophe.
- LaTeX is decoded first, so `a:schöner` finds `Sch{\"o}ner` and
  `t:façades` finds `Fa\c{c}ades`.
- Cite keys and URLs aren't prose: `c:` and `u:` match any part
  (`c:2025`, `u:arxiv`), and a plain word also finds any part of a cite key.

While you type, a half-written word matches nothing until it's complete
(`gla` doesn't find "glacier"); type `gla*` to see matches early.

## Field prefixes

To search a specific field, prefix a term. Both a short and a long form work.
Quote a value that contains a space, e.g. `k:"sea ice"`:

| Prefix                 | Searches           | Example            |
| ---------------------- | ------------------ | ------------------ |
| `a:` / `author:`       | author             | `a:smith`          |
| `t:` / `title:`        | title              | `t:glacier`        |
| `j:` / `journal:`      | journal            | `j:nature`         |
| `k:` / `kw:`           | keyword            | `k:"sea ice"`      |
| `y:` / `year:`         | year, range or comparison | `y:2015-2023` |
| `u:` / `url:`          | URL                | `u:arxiv`          |
| `c:` / `citekey:`      | cite key           | `c:smith2020`      |
| `r:` / `state:`        | read state         | `r:to-read`        |
| `pr:` / `urgency:`     | urgency            | `pr:high`          |
| `rt:` / `rating:`      | rating, range or comparison | `rt:>=3`  |

## Year ranges

`y:` accepts more than a single year:

```text
y:2015-2023      # closed range: 2015 through 2023
y:2015-          # open range: 2015 or later
y:-2015          # open range: up to 2015
y:>2015          # strictly after 2015
y:>=2015         # 2015 or later (same as y:2015-)
y:<2015          # strictly before 2015
y:<=2015         # 2015 or earlier (same as y:-2015)
```

An entry with no year never matches a range or comparison.

## Rating

`rt:` takes the same comparisons and ranges, but a plain number matches
exactly. `0` means unrated:

```text
rt:5             # five stars
rt:>=3           # three stars or more
rt:2-4           # two to four stars
rt:0             # not rated yet
NOT rt:0         # rated at all
```

## Boolean search

For "either of these" or "but not that", use `OR` and `NOT`, and group with
parentheses — the same logic as Web of Science's Advanced Search:

```text
a:smith OR a:jones                     # either author
a:(smith OR jones)                     # the same: a prefix applies to a whole group
a:(smith OR jones) k:ice               # either author, tagged ice
k:ice NOT r:read                       # ice papers you haven't read yet
(t:glacier OR t:"ice sheet") y:2015-   # either topic, 2015 or later
j:(nature OR science)                  # either journal
```

`NOT` binds tightest, then `AND`, then `OR`, so `k:snow y:2016 OR a:smith`
means "(snow and 2016) or Smith". Use parentheses when in doubt.

- `AND`, `OR` and `NOT` work in any case (`or` too), but only as separate
  words. To search for the word itself, quote or prefix it: `t:"or"`, `t:not`.
- A plain word inside a prefixed group gets that prefix; a term with its own
  prefix keeps it: `a:(smith OR t:snow)`.
- Parentheses inside quotes are literal: `t:"(in)stability"`.
- While you type, an unfinished query still filters: `a:(smith OR` shows Smith.
  A query that can't be finished by typing more, like `OR OR` or a stray `)`,
  shows a short hint under the search box and keeps the last valid result.

## Combine terms

Prefixes and plain words can be mixed freely. Terms are combined with AND; the
optional `AND` keyword reads naturally but changes nothing:

```text
a:smith t:glacier            # Smith, with "glacier" in the title
j:nature AND y:2025          # in Nature, published in 2025
k:ice a:jones                # tagged "ice", authored by Jones
y:2010-                      # published 2010 or later
c:smith2020                  # a cite-key lookup (also finds smith2020a)
r:to-read pr:high            # still to read, high urgency
```

!!! tip "Find your own papers"

    `a:yourname` is a fast way to pull up everything you've authored — handy
    when assembling a CV or a grant report.

## Saved filters

A search you retype every session is really a saved view waiting to happen —
bibtui calls these **filters**. Keep one `.bib` file for everything, and use a
filter to work inside a slice of it, e.g. "Project X" = keyword `sepp`,
published 2010 or later.

Press <kbd>f</kbd> to open **Filters**:

```text
0 · All entries
1 · ● Project X        — k:sepp y:2010-
2 ·   To read           — r:to-read
```

| Key                       | Action                                                        |
| ------------------------- | -------------------------------------------------------------- |
| <kbd>0</kbd>–<kbd>9</kbd> | Jump straight to that filter (<kbd>0</kbd> is "All entries")   |
| <kbd>Enter</kbd>          | Select the highlighted row                                     |
| <kbd>w</kbd>               | Write the current search as a new (or updated) filter          |
| <kbd>e</kbd>               | Edit the highlighted filter's name/query                       |
| <kbd>d</kbd>               | Delete the highlighted filter (confirmation required)          |
| <kbd>Esc</kbd>             | Close the menu                                                 |

To save a filter: type a search (`k:sepp y:2010-`), press <kbd>f</kbd> then
<kbd>w</kbd>, and give it a name — typing an existing filter's name updates
it instead of creating a new one (confirmed first, in case it was a typo).
The active filter (marked `●`, and already highlighted when you reopen the
menu) is shown in a bar above the search box —
`Filter: Project X  k:sepp y:2010-  42 / 1203` — and in the app's title bar.

The search box then **refines within the active filter**, exactly like
adding another ANDed term. <kbd>Esc</kbd> clears only that refining search —
the filter itself stays on until you pick a different one from the
<kbd>f</kbd> menu, so you can't drop out of your current project by
accident. The last-active filter is remembered across restarts.

Deleting a filter (<kbd>d</kbd>) always drops you back to "All entries" —
even if the one you deleted wasn't the active one — so you never end up
looking at a just-deleted filter's results. "All entries" itself (row 0)
isn't a real filter and can't be deleted; trying to shows a notice instead
of silently doing nothing.

Filters are saved to `~/.config/bibtui/filters.toml` and apply to every `.bib`
file you open — see [Saved filters](../configuration.md#saved-filters) for
the file format.

## Sorting

Click any column header to sort by it; click again to reverse. The active sort
column is marked with `▲` (ascending) or `▼` (descending). Sort by **Added** to
see what's new, by **★** to surface your highest-rated reading, or by **Year**
to scan chronologically.

By default the table is sorted by **Added**, newest first. Your choice is
remembered: the sort you left is restored the next time you start bibtui (saved
under `[ui] sort_column` / `sort_reverse` in `config.toml`).

## Choosing columns

You're not limited to the default columns. From the command palette
(<kbd>Ctrl</kbd>+<kbd>P</kbd> → **Table: Configure columns**) you can pick which
columns the table shows and in what order, including the cite key or any BibTeX
field present in your library. See
[Table columns](../configuration.md#table-columns) for details.
