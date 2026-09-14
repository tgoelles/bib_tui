"""Tests for bibtui.utils.opener.open_with_default_app.

Regression coverage for a real cross-platform bug: the "Open PDF" action (and
the Add-PDF modal's preview-on-space) only special-cased macOS and otherwise
always ran ``xdg-open`` — which does not exist on Windows, so opening a PDF
silently failed there with a "Could not open PDF" notification. Every branch
is exercised here so a future change can't reintroduce a platform that falls
through to the Linux-only ``xdg-open`` branch.
"""

import subprocess

from bibtui.utils.opener import open_with_default_app


def test_uses_xdg_open_on_linux(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("bibtui.utils.opener.platform.system", lambda: "Linux")
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: calls.append(args))

    open_with_default_app("/tmp/paper.pdf")

    assert calls == [["xdg-open", "/tmp/paper.pdf"]]


def test_uses_open_on_macos(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("bibtui.utils.opener.platform.system", lambda: "Darwin")
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: calls.append(args))

    open_with_default_app("/tmp/paper.pdf")

    assert calls == [["open", "/tmp/paper.pdf"]]


def test_uses_os_startfile_on_windows(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("bibtui.utils.opener.platform.system", lambda: "Windows")
    # os.startfile only exists on real Windows; patch it in unconditionally
    # so this test can run on Linux/macOS CI too.
    monkeypatch.setattr("bibtui.utils.opener.os.startfile", calls.append, raising=False)

    open_with_default_app(r"C:\Users\me\papers\paper.pdf")

    assert calls == [r"C:\Users\me\papers\paper.pdf"]
