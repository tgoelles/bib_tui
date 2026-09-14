"""Unit tests for the native OS clipboard helper."""

import subprocess

import pytest

from bibtui.utils import clipboard


class _Recorder:
    """Stand-in for subprocess.run that records calls and can be told to fail."""

    def __init__(self, *, fail_on: set[str] | None = None, exc: Exception | None = None):
        self.fail_on = fail_on or set()
        self.exc = exc
        self.calls: list[tuple[list[str], bytes]] = []

    def __call__(self, argv, *, input, check, capture_output, timeout):  # noqa: A002
        self.calls.append((argv, input))
        if self.exc is not None and argv[0] in self.fail_on:
            raise self.exc
        if argv[0] in self.fail_on:
            raise subprocess.CalledProcessError(1, argv)
        return subprocess.CompletedProcess(argv, 0, b"", b"")


@pytest.fixture
def on_platform(monkeypatch: pytest.MonkeyPatch):
    def _set(name: str) -> None:
        monkeypatch.setattr(clipboard.sys, "platform", name)

    return _set


def _all_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clipboard.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")


def _none_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clipboard.shutil, "which", lambda cmd: None)


# ---------------------------------------------------------------------------
# Platform command selection
# ---------------------------------------------------------------------------


def test_macos_uses_pbcopy(monkeypatch, on_platform) -> None:
    on_platform("darwin")
    _all_present(monkeypatch)
    rec = _Recorder()
    monkeypatch.setattr(clipboard.subprocess, "run", rec)

    assert clipboard.copy_to_os_clipboard("hello") is True
    assert rec.calls == [(["pbcopy"], b"hello")]


def test_windows_uses_clip(monkeypatch, on_platform) -> None:
    on_platform("win32")
    _all_present(monkeypatch)
    rec = _Recorder()
    monkeypatch.setattr(clipboard.subprocess, "run", rec)

    assert clipboard.copy_to_os_clipboard("x") is True
    assert rec.calls[0][0] == ["clip"]


def test_linux_prefers_wl_copy(monkeypatch, on_platform) -> None:
    on_platform("linux")
    _all_present(monkeypatch)
    rec = _Recorder()
    monkeypatch.setattr(clipboard.subprocess, "run", rec)

    assert clipboard.copy_to_os_clipboard("x") is True
    assert rec.calls[0][0] == ["wl-copy"]


def test_linux_falls_back_to_xclip_when_wl_copy_missing(monkeypatch, on_platform) -> None:
    on_platform("linux")
    monkeypatch.setattr(
        clipboard.shutil,
        "which",
        lambda cmd: None if cmd == "wl-copy" else f"/usr/bin/{cmd}",
    )
    rec = _Recorder()
    monkeypatch.setattr(clipboard.subprocess, "run", rec)

    assert clipboard.copy_to_os_clipboard("x") is True
    assert rec.calls[0][0] == ["xclip", "-selection", "clipboard"]


def test_linux_falls_back_to_xsel_when_it_is_the_only_helper(monkeypatch, on_platform):
    on_platform("linux")
    monkeypatch.setattr(
        clipboard.shutil, "which", lambda cmd: "/usr/bin/xsel" if cmd == "xsel" else None
    )
    rec = _Recorder()
    monkeypatch.setattr(clipboard.subprocess, "run", rec)

    assert clipboard.copy_to_os_clipboard("x") is True
    assert rec.calls[0][0] == ["xsel", "--clipboard", "--input"]


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------


def test_returns_false_when_no_helper_installed(monkeypatch, on_platform) -> None:
    on_platform("linux")
    _none_present(monkeypatch)
    called = False

    def _run(*a, **k):
        nonlocal called
        called = True

    monkeypatch.setattr(clipboard.subprocess, "run", _run)

    assert clipboard.copy_to_os_clipboard("x") is False
    assert called is False  # never even attempted


def test_tries_next_helper_when_first_fails(monkeypatch, on_platform) -> None:
    on_platform("linux")
    _all_present(monkeypatch)
    rec = _Recorder(fail_on={"wl-copy"})
    monkeypatch.setattr(clipboard.subprocess, "run", rec)

    assert clipboard.copy_to_os_clipboard("x") is True
    assert [c[0][0] for c in rec.calls] == ["wl-copy", "xclip"]


def test_returns_false_when_every_helper_fails(monkeypatch, on_platform) -> None:
    on_platform("linux")
    _all_present(monkeypatch)
    rec = _Recorder(fail_on={"wl-copy", "xclip", "xsel"})
    monkeypatch.setattr(clipboard.subprocess, "run", rec)

    assert clipboard.copy_to_os_clipboard("x") is False
    assert [c[0][0] for c in rec.calls] == ["wl-copy", "xclip", "xsel"]


def test_swallows_oserror_from_subprocess(monkeypatch, on_platform) -> None:
    on_platform("darwin")
    _all_present(monkeypatch)
    rec = _Recorder(fail_on={"pbcopy"}, exc=OSError("boom"))
    monkeypatch.setattr(clipboard.subprocess, "run", rec)

    assert clipboard.copy_to_os_clipboard("x") is False


def test_swallows_timeout_expired(monkeypatch, on_platform) -> None:
    on_platform("darwin")
    _all_present(monkeypatch)
    rec = _Recorder(fail_on={"pbcopy"}, exc=subprocess.TimeoutExpired("pbcopy", 5))
    monkeypatch.setattr(clipboard.subprocess, "run", rec)

    assert clipboard.copy_to_os_clipboard("x") is False


# ---------------------------------------------------------------------------
# Payload encoding
# ---------------------------------------------------------------------------


def test_text_is_passed_as_utf8_bytes_on_stdin(monkeypatch, on_platform) -> None:
    on_platform("darwin")
    _all_present(monkeypatch)
    rec = _Recorder()
    monkeypatch.setattr(clipboard.subprocess, "run", rec)

    clipboard.copy_to_os_clipboard("café — ☕")
    assert rec.calls[0][1] == "café — ☕".encode("utf-8")
