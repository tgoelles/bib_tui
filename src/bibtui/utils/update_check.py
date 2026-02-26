import json
import urllib.request
from datetime import UTC, datetime, timedelta

from packaging.version import InvalidVersion, Version

PACKAGE_NAME = "bibtui"
PYPI_JSON_URL = f"https://pypi.org/pypi/{PACKAGE_NAME}/json"
CHECK_INTERVAL = timedelta(days=1)


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_utc_iso(value: datetime) -> str:
    return (
        value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )


def parse_utc_iso(value: str) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def is_due(last_check_utc: str, now: datetime | None = None) -> bool:
    now_utc = now or utc_now()
    last = parse_utc_iso(last_check_utc)
    if last is None:
        return True
    return (now_utc - last) >= CHECK_INTERVAL


def notified_today(last_notified_utc: str, now: datetime | None = None) -> bool:
    now_utc = now or utc_now()
    last = parse_utc_iso(last_notified_utc)
    if last is None:
        return False
    return last.date() == now_utc.date()


def is_newer_version(installed: str, latest: str) -> bool:
    try:
        return Version(latest) > Version(installed)
    except InvalidVersion:
        return False


def _stable_versions(releases: dict) -> list[Version]:
    stable: list[Version] = []
    for value in releases.keys():
        try:
            version = Version(value)
        except InvalidVersion:
            continue
        if version.is_prerelease or version.is_devrelease:
            continue
        stable.append(version)
    return stable


def fetch_latest_stable_version(timeout: int = 3) -> str | None:
    req = urllib.request.Request(
        PYPI_JSON_URL,
        headers={"User-Agent": "bibtui update-check"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    releases = data.get("releases")
    if not isinstance(releases, dict):
        return None

    stable = _stable_versions(releases)
    if not stable:
        return None
    return str(max(stable))
