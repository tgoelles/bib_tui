import json
from datetime import UTC, datetime, timedelta

from bibtui.utils import update_check


def test_is_due_when_never_checked() -> None:
    now = datetime(2026, 2, 26, 12, 0, tzinfo=UTC)
    assert update_check.is_due("", now)


def test_is_due_false_within_24h() -> None:
    now = datetime(2026, 2, 26, 12, 0, tzinfo=UTC)
    last = now - timedelta(hours=6)
    assert not update_check.is_due(update_check.to_utc_iso(last), now)


def test_is_due_true_after_24h() -> None:
    now = datetime(2026, 2, 26, 12, 0, tzinfo=UTC)
    last = now - timedelta(days=1, minutes=1)
    assert update_check.is_due(update_check.to_utc_iso(last), now)


def test_notified_today_true_same_date() -> None:
    now = datetime(2026, 2, 26, 19, 0, tzinfo=UTC)
    notified = datetime(2026, 2, 26, 1, 0, tzinfo=UTC)
    assert update_check.notified_today(update_check.to_utc_iso(notified), now)


def test_notified_today_false_other_date() -> None:
    now = datetime(2026, 2, 26, 1, 0, tzinfo=UTC)
    notified = datetime(2026, 2, 25, 23, 59, tzinfo=UTC)
    assert not update_check.notified_today(update_check.to_utc_iso(notified), now)


def test_is_newer_version() -> None:
    assert update_check.is_newer_version("0.9.8", "0.10.0")
    assert not update_check.is_newer_version("0.10.0", "0.9.8")


def test_fetch_latest_stable_version_prefers_stable(monkeypatch) -> None:
    payload = {
        "releases": {
            "0.9.8": [{}],
            "0.10.0rc1": [{}],
            "0.10.0": [{}],
        }
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    def fake_urlopen(req, timeout=0):
        return FakeResponse()

    monkeypatch.setattr(update_check.urllib.request, "urlopen", fake_urlopen)

    assert update_check.fetch_latest_stable_version() == "0.10.0"


def test_fetch_latest_stable_version_returns_none_on_network_error(monkeypatch) -> None:
    def fake_urlopen(req, timeout=0):
        raise OSError("offline")

    monkeypatch.setattr(update_check.urllib.request, "urlopen", fake_urlopen)

    assert update_check.fetch_latest_stable_version() is None
