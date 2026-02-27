from datetime import datetime

from bibtui.utils.dates import (
    extract_date_added,
    format_bib_date,
    now_date_added_value,
    parse_bib_date,
)


def test_extract_date_added_prefers_canonical_key() -> None:
    raw = {
        "date_added": "2024-01-02",
        "date-added": "2025-02-03T04:05:06",
    }
    assert extract_date_added(raw) == "2025-02-03T04:05:06"


def test_parse_bib_date_iso_timestamp() -> None:
    parsed = parse_bib_date("2025-02-03T04:05:06")
    assert parsed == datetime(2025, 2, 3, 4, 5, 6)


def test_format_bib_date_normalizes_to_day() -> None:
    assert format_bib_date("2025-02-03T04:05:06") == "2025-02-03"
    assert format_bib_date("2025/02/03") == "2025-02-03"


def test_format_bib_date_fallback_for_unknown_formats() -> None:
    assert format_bib_date("03.02.2025 04:05") == "03.02.2025"


def test_now_date_added_value_format() -> None:
    stamp = now_date_added_value()
    assert len(stamp) == 19
    assert stamp[4] == "-"
    assert stamp[7] == "-"
    assert stamp[10] == "T"
