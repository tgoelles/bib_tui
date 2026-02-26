import re
import unicodedata
from string import ascii_lowercase

_AUTHOR_YEAR_RE = re.compile(r"^[A-Z][A-Za-z0-9-]*\d{4}[a-z]?$")
_AUTHOR_YEAR_PARTS_RE = re.compile(r"^([A-Za-z0-9-]+?)(\d{4})([A-Za-z]?)$")
_YEAR_RE = re.compile(r"(\d{4})")


def is_author_year_key(key: str) -> bool:
    return bool(_AUTHOR_YEAR_RE.fullmatch((key or "").strip()))


def canonicalize_author_year_key(key: str) -> str:
    """Normalize casing for AuthorYear-like keys.

    Examples:
    - STEINIGER2021 -> Steiniger2021
    - steininger2021a -> Steininger2021a
    """
    k = (key or "").strip()
    match = _AUTHOR_YEAR_PARTS_RE.fullmatch(k)
    if not match:
        return k
    author_part, year_part, suffix = match.groups()
    if not author_part:
        return k
    author_part = "-".join(
        segment[0].upper() + segment[1:].lower() if segment else segment
        for segment in author_part.split("-")
    )
    return f"{author_part}{year_part}{suffix.lower()}"


def is_canonical_author_year_key(key: str) -> bool:
    k = (key or "").strip()
    return is_author_year_key(k) and canonicalize_author_year_key(k) == k


def author_year_base(author_field: str, year_field: str) -> str:
    surname = _extract_primary_surname(author_field)
    year = _extract_year(year_field)
    return f"{surname}{year}"


def make_unique_key(base_key: str, used: set[str]) -> str:
    if base_key not in used:
        return base_key
    for suffix in ascii_lowercase:
        candidate = f"{base_key}{suffix}"
        if candidate not in used:
            return candidate
    n = 2
    while True:
        candidate = f"{base_key}z{n}"
        if candidate not in used:
            return candidate
        n += 1


def _extract_year(year_field: str) -> str:
    match = _YEAR_RE.search(year_field or "")
    if match:
        return match.group(1)
    return "0000"


def _extract_primary_surname(author_field: str) -> str:
    if not author_field:
        return "Unknown"

    first_author = (author_field.split(" and ")[0] or "").strip()
    if not first_author:
        return "Unknown"

    if "," in first_author:
        surname_raw = first_author.split(",", 1)[0]
    else:
        parts = first_author.split()
        surname_raw = parts[-1] if parts else first_author

    normalized = _normalize_token(surname_raw)
    if not normalized:
        return "Unknown"

    if normalized.isupper():
        normalized = normalized.title()

    return normalized[0].upper() + normalized[1:]


def _normalize_token(text: str) -> str:
    cleaned = _normalize_latex_text(text)
    for src, dst in (
        ("ä", "ae"),
        ("Ä", "Ae"),
        ("ö", "oe"),
        ("Ö", "Oe"),
        ("ü", "ue"),
        ("Ü", "Ue"),
        ("ß", "ss"),
    ):
        cleaned = cleaned.replace(src, dst)
    cleaned = unicodedata.normalize("NFKD", cleaned)
    cleaned = "".join(ch for ch in cleaned if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^A-Za-z0-9]", "", cleaned)
    return cleaned


def _normalize_latex_text(text: str) -> str:
    t = text or ""
    for src, dst in (
        (r"\\ss", "ss"),
        (r"\\SS", "SS"),
        (r"\\ae", "ae"),
        (r"\\AE", "AE"),
        (r"\\oe", "oe"),
        (r"\\OE", "OE"),
        (r"\\aa", "aa"),
        (r"\\AA", "AA"),
        (r"\\o", "o"),
        (r"\\O", "O"),
        (r"\\l", "l"),
        (r"\\L", "L"),
    ):
        t = t.replace(src, dst)

    def _umlaut_repl(match: re.Match[str]) -> str:
        ch = match.group(1)
        return {
            "a": "ae",
            "A": "Ae",
            "o": "oe",
            "O": "Oe",
            "u": "ue",
            "U": "Ue",
        }.get(ch, ch)

    t = re.sub(r'\\"\s*\{?\s*([A-Za-z])\s*\}?', _umlaut_repl, t)

    # Common one-letter accent macros, e.g. {\"o}, \'e, \v{c}
    t = re.sub(
        r"\\[\"'`^~=.uvHckrbdt]\s*\{?\s*([A-Za-z])\s*\}?",
        r"\1",
        t,
    )

    # Remaining command wrappers around one token: \textit{X} -> X
    t = re.sub(r"\\[A-Za-z]+\s*\{([^}]*)\}", r"\1", t)

    # Remove any remaining commands and braces
    t = re.sub(r"\\[A-Za-z]+", "", t)
    t = t.replace("{", "").replace("}", "")

    return t
