"""The search query language, shared by the live search box and saved filters.

A query is a list of terms. A term is a plain word (searched in title, author,
keywords and cite key) or ``prefix:value`` for one field (``a:smith``,
``y:2010-``). Terms combine with boolean operators, as in Web of Science's
Advanced Search::

    a:(smith OR jones) k:ice              either author, tagged ice
    (t:glacier OR t:"ice sheet") y:2015-  either topic, 2015 or later
    k:ice NOT r:read                      ice papers not yet read
    rt:>=4 OR pr:high                     well rated, or urgent

Grammar — ``NOT`` binds tightest, then ``AND`` (also implied between terms),
then ``OR``::

    or_expr  := and_expr ("OR" and_expr)*
    and_expr := not_expr (["AND"] not_expr)*
    not_expr := "NOT" not_expr | primary
    primary  := "(" or_expr ")" | prefix ":(" or_expr ")" | term

``AND``/``OR``/``NOT`` are operators only as bare words, in any case; quoted
(``"or"``) or prefixed (``t:not``) they are ordinary search terms.

The search box filters on every keystroke, so a half-typed query must still
work: an unclosed ``(`` is closed at the end, and a trailing operator or empty
group (``a:smith OR``, ``NOT``, ``(``) is ignored. Only a query that can't be
completed by typing more — ``OR OR``, a stray ``)``, ``()`` — raises
:class:`QueryError`.
"""

from collections.abc import Callable
from dataclasses import dataclass

from bibtui.bib.latex import decode_latex
from bibtui.bib.models import BibEntry

Matcher = Callable[[BibEntry], bool]

FIELD_PREFIXES: dict[str, str] = {
    "t": "title",
    "title": "title",
    "a": "author",
    "author": "author",
    "j": "journal",
    "journal": "journal",
    "k": "keywords",
    "kw": "keywords",
    "keyword": "keywords",
    "keywords": "keywords",
    "y": "year",
    "year": "year",
    "u": "url",
    "url": "url",
    "c": "citekey",
    "citekey": "citekey",
    "key": "citekey",
    "r": "read_state",
    "state": "read_state",
    "read": "read_state",
    "pr": "priority",
    "priority": "priority",
    "urgency": "priority",
    "rt": "rating",
    "rating": "rating",
    "rank": "rating",
}

_OPERATORS = {"AND", "OR", "NOT"}


class QueryError(ValueError):
    """The query is malformed in a way that typing more cannot fix."""


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Token:
    # "term", "op", "(", ")", or "group" (a field prefix opening a group: a:( )
    kind: str
    value: str = ""
    field: str | None = None


def _term_token(text: str) -> _Token:
    """A ``prefix:value`` field term, or a plain word.

    An unknown prefix or an empty value (``foo:bar``, ``a:``) is searched as
    plain text, exactly as typed.
    """
    prefix, sep, value = text.partition(":")
    field = FIELD_PREFIXES.get(prefix.lower()) if sep else None
    if field and value:
        return _Token("term", value.lower(), field)
    return _Token("term", text.lower())


def _tokenize(query: str) -> list[_Token]:
    """Split *query* into terms, operators and parentheses.

    Double quotes keep spaces and parentheses inside one value
    (``k:"sea ice"``, ``t:"(in)stability"``); an unclosed quote runs to the end
    of the query, as it does while it is still being typed. Apostrophes are
    ordinary characters, so ``a:o'brien`` works.
    """
    tokens: list[_Token] = []
    i, n = 0, len(query)
    while i < n:
        ch = query[i]
        if ch.isspace():
            i += 1
            continue
        if ch in "()":
            tokens.append(_Token(ch))
            i += 1
            continue

        parts: list[str] = []
        quoted = False
        while i < n and not query[i].isspace() and query[i] not in "()":
            if query[i] == '"':
                end = query.find('"', i + 1)
                if end == -1:
                    end = n
                parts.append(query[i + 1 : end])
                quoted = True
                i = end + 1
            else:
                parts.append(query[i])
                i += 1
        text = "".join(parts)

        if i < n and query[i] == "(" and not quoted and text.endswith(":"):
            field = FIELD_PREFIXES.get(text[:-1].lower())
            if field:
                tokens.append(_Token("group", field=field))
                i += 1
                continue
        if not quoted and text.upper() in _OPERATORS:
            tokens.append(_Token("op", text.upper()))
            continue
        tokens.append(_term_token(text))
    return tokens


# ---------------------------------------------------------------------------
# Matching one term
# ---------------------------------------------------------------------------


def _year_matches(entry_year: str, value: str) -> bool:
    """Match a ``y:`` filter value against an entry's year.

    Supports an exact/substring match (``2010``), a closed range
    (``2010-2020``), an open range (``2010-`` = 2010 or later, ``-2010`` = up
    to 2010), and comparisons (``>2010``, ``>=2010``, ``<2010``, ``<=2010``).
    A non-numeric entry year never satisfies a range or comparison — only
    the plain substring form can match it.
    """
    for op, op_len in ((">=", 2), ("<=", 2), (">", 1), ("<", 1)):
        if value.startswith(op):
            bound_str = value[op_len:]
            if not bound_str.isdigit() or not entry_year.isdigit():
                return False
            bound, year = int(bound_str), int(entry_year)
            if op == ">=":
                return year >= bound
            if op == "<=":
                return year <= bound
            if op == ">":
                return year > bound
            return year < bound

    if "-" in value:
        y_min_str, _, y_max_str = value.partition("-")
        if entry_year.isdigit():
            year = int(entry_year)
            try:
                if y_min_str and y_max_str:
                    return int(y_min_str) <= year <= int(y_max_str)
                if y_min_str:  # "2010-" → 2010 or later
                    return year >= int(y_min_str)
                if y_max_str:  # "-2010" → up to 2010
                    return year <= int(y_max_str)
            except ValueError:
                pass
        return value in entry_year

    return value in entry_year


def _rating_matches(rating: int, value: str) -> bool:
    """Match a ``rating:`` value: ``3`` (exactly), ``>=3``, ``>3``, ``<=2``,
    ``<2``, or a range ``3-5`` / ``4-`` / ``-2``. ``0`` means unrated.

    Unlike a year, a plain number matches exactly: ``rt:3`` must not match 13.
    A value that isn't a number or range matches nothing.
    """
    for op in (">=", "<=", ">", "<"):
        if value.startswith(op):
            bound = value[len(op) :]
            if not bound.isdigit():
                return False
            return {
                ">=": rating >= int(bound),
                "<=": rating <= int(bound),
                ">": rating > int(bound),
                "<": rating < int(bound),
            }[op]
    if "-" in value:
        low, _, high = value.partition("-")
        if (low and not low.isdigit()) or (high and not high.isdigit()):
            return False
        if not (low or high):
            return False
        return (not low or rating >= int(low)) and (not high or rating <= int(high))
    return value.isdigit() and rating == int(value)


def _term_matches(entry: BibEntry, field: str | None, value: str) -> bool:
    """Whether one (already lower-cased) term matches *entry*."""
    if field is None:
        return (
            value in entry.title_plain.lower()
            or value in entry.author.lower()
            or value in entry.keywords.lower()
            or value in entry.key.lower()
        )
    if field == "title":
        return value in entry.title_plain.lower()
    if field == "author":
        return value in entry.author.lower()
    if field == "keywords":
        return value in entry.keywords.lower()
    if field == "year":
        return _year_matches(entry.year, value)
    if field == "journal":
        journal = entry.journal or entry.raw_fields.get("booktitle", "")
        return value in decode_latex(journal).lower()
    if field == "url":
        return value in entry.url.lower()
    if field == "citekey":
        return value in entry.key.lower()
    if field == "read_state":
        # Exact match, not substring: "read" and "to-read" are distinct
        # states and a substring match would conflate them.
        return value == entry.read_state.lower()
    if field == "priority":
        return value == entry.priority_label.lower()
    if field == "rating":
        return _rating_matches(entry.rating, value)
    return False


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _all(matchers: list[Matcher]) -> Matcher:
    if len(matchers) == 1:
        return matchers[0]
    return lambda entry: all(m(entry) for m in matchers)


def _any(matchers: list[Matcher]) -> Matcher:
    if len(matchers) == 1:
        return matchers[0]
    return lambda entry: any(m(entry) for m in matchers)


class _Parser:
    """Recursive-descent parser over the token list.

    Each rule returns a matcher, or ``None`` for an operand that is missing
    only because the query ends there (still being typed).
    """

    def __init__(self, tokens: list[_Token]) -> None:
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> _Token | None:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _at_op(self, op: str) -> bool:
        token = self._peek()
        return token is not None and token.kind == "op" and token.value == op

    def parse(self) -> Matcher | None:
        matcher = self._or_expr(None)
        if self._peek() is not None:  # only a ")" stops the top level early
            raise QueryError("')' without a matching '('")
        return matcher

    def _or_expr(self, field: str | None) -> Matcher | None:
        left = self._and_expr(field)
        alternatives = [left] if left is not None else []
        while self._at_op("OR"):
            self._pos += 1
            if left is None:
                raise QueryError("OR needs a term on both sides")
            right = self._and_expr(field)
            if right is None:
                if self._peek() is None:
                    break  # "a OR" — the second term is still being typed
                raise QueryError("OR needs a term on both sides")
            alternatives.append(right)
            left = right
        return _any(alternatives) if alternatives else None

    def _and_expr(self, field: str | None) -> Matcher | None:
        terms: list[Matcher] = []
        while True:
            if self._at_op("AND"):
                # AND is the default anyway; a leading or doubled one is
                # ignored, as it always has been.
                self._pos += 1
                continue
            token = self._peek()
            if token is None or token.kind == ")" or self._at_op("OR"):
                break
            matcher = self._not_expr(field)
            if matcher is not None:
                terms.append(matcher)
        return _all(terms) if terms else None

    def _not_expr(self, field: str | None) -> Matcher | None:
        if not self._at_op("NOT"):
            return self._primary(field)
        self._pos += 1
        token = self._peek()
        if token is None:
            return None  # trailing NOT
        if token.kind == ")" or self._at_op("AND") or self._at_op("OR"):
            raise QueryError("NOT needs a term after it")
        inner = self._not_expr(field)
        if inner is None:
            return None  # "NOT (" — the group is still being typed
        return lambda entry: not inner(entry)

    def _primary(self, field: str | None) -> Matcher | None:
        token = self._tokens[self._pos]
        self._pos += 1
        if token.kind == "term":
            term_field = token.field or field
            value = token.value
            return lambda entry: _term_matches(entry, term_field, value)

        # "(" or "prefix:(" — a prefix applies to the group's plain words;
        # a term with its own prefix inside the group keeps that prefix.
        inner = self._or_expr(token.field if token.kind == "group" else field)
        if self._peek() is None:
            return inner  # unclosed group, closed at the end of the query
        self._pos += 1  # the ")"
        if inner is None:
            raise QueryError("empty parentheses")
        return inner


def compile_query(query: str) -> Matcher:
    """Turn *query* into a function that tests one entry.

    Parse once and apply the result to every entry. An empty query matches
    everything. Raises :class:`QueryError` for a malformed query.
    """
    matcher = _Parser(_tokenize(query)).parse()
    return matcher if matcher is not None else (lambda entry: True)


def matches_query(entry: BibEntry, query: str) -> bool:
    """Whether *entry* matches *query*; see :func:`compile_query`."""
    return compile_query(query)(entry)
