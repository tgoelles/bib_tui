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

## Field prefixes

To search a specific field, prefix a term. Both a short and a long form work:

| Prefix                 | Searches      | Example            |
| ---------------------- | ------------- | ------------------ |
| `a:` / `author:`       | author        | `a:smith`          |
| `t:` / `title:`        | title         | `t:glacier`        |
| `j:` / `journal:`      | journal       | `j:nature`         |
| `k:` / `kw:`           | keyword       | `k:ice`            |
| `y:` / `year:`         | year or range | `y:2015-2023`      |
| `u:` / `url:`          | URL           | `u:arxiv`          |
| `c:` / `citekey:`      | cite key      | `c:smith2020`      |

## Combine terms

Prefixes and plain words can be mixed freely. The optional `AND` keyword reads
naturally but changes nothing — terms are always ANDed:

```text
a:smith t:glacier            # Smith, with "glacier" in the title
j:nature AND y:2025          # in Nature, published in 2025
k:ice a:jones                # tagged "ice", authored by Jones
y:2015-2023                  # anything in that year range
c:smith2020                  # an exact cite-key lookup
```

!!! tip "Find your own papers"

    `a:yourname` is a fast way to pull up everything you've authored — handy
    when assembling a CV or a grant report.

## Sorting

Click any column header to sort by it; click again to reverse. The active sort
column is marked with `▲` (ascending) or `▼` (descending). Sort by **Added** to
see what's new, by **★** to surface your highest-rated reading, or by **Year**
to scan chronologically.
