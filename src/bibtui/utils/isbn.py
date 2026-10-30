import re

_NON_ISBN_CHARS_RE = re.compile(r"[^0-9Xx]")


def _isbn10_valid(digits: str) -> bool:
    if not re.fullmatch(r"\d{9}[\dX]", digits):
        return False
    total = sum(
        (10 - i) * (10 if ch == "X" else int(ch)) for i, ch in enumerate(digits)
    )
    return total % 11 == 0


def _isbn13_check_digit(first12: str) -> str:
    total = sum((1 if i % 2 == 0 else 3) * int(ch) for i, ch in enumerate(first12))
    return str((10 - total % 10) % 10)


def normalize_isbn(raw: str) -> str | None:
    """Return *raw* as a checksum-valid ISBN-13, or ``None`` if it isn't one.

    Accepts ISBN-10 or ISBN-13 with any hyphens/spaces; an ISBN-10 is
    converted to its ISBN-13 (978-prefixed) form so the two spellings of the
    same book compare equal.
    """
    digits = _NON_ISBN_CHARS_RE.sub("", raw or "").upper()
    if re.fullmatch(r"97[89]\d{10}", digits):
        return digits if _isbn13_check_digit(digits[:12]) == digits[12] else None
    if len(digits) == 10 and _isbn10_valid(digits):
        body = "978" + digits[:9]
        return body + _isbn13_check_digit(body)
    return None
