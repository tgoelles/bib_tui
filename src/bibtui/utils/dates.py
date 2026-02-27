from datetime import datetime

DATE_ADDED_KEYS: tuple[str, ...] = ("date-added", "date_added", "dateadded")


def now_date_added_value() -> str:
    """Return canonical timestamp used for newly added entries."""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def extract_date_added(raw_fields: dict[str, str]) -> str:
    """Return the first known raw date-added field value, if present."""
    for key in DATE_ADDED_KEYS:
        value = (raw_fields.get(key) or "").strip()
        if value:
            return value
    return ""


def parse_bib_date(value: str) -> datetime | None:
    """Parse a bibliography date string into a datetime if possible."""
    text = value.strip()
    if not text:
        return None

    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def format_bib_date(value: str, empty: str = "") -> str:
    """Format a bibliography date to compact YYYY-MM-DD for table display."""
    parsed = parse_bib_date(value)
    if parsed is not None:
        return parsed.strftime("%Y-%m-%d")
    return value[:10] if value else empty
