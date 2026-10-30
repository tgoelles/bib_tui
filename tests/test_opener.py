"""Tests for bibtui.utils.opener.open_with_default_app.

Regression coverage for a real cross-platform bug: the "Open PDF" action (and
the Add-PDF modal's preview-on-space) only special-cased macOS and otherwise
always ran ``xdg-open`` — which does not exist on Windows, so opening a PDF
silently failed there with a "Could not open PDF" notification. Every branch
is exercised here so a future change can't reintroduce a platform that falls
through to the Linux-only ``xdg-open`` branch.
"""

import os
import signal
import subprocess
import sys
import time

import pytest

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


@pytest.mark.parametrize("system", ["Linux", "Darwin"])
def test_viewer_is_detached_and_silenced(monkeypatch, system) -> None:
    """The viewer must not write into the TUI or die when bibtui exits."""
    kwargs: list[dict] = []
    monkeypatch.setattr("bibtui.utils.opener.platform.system", lambda: system)
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: kwargs.append(kw))

    open_with_default_app("/tmp/paper.pdf")

    assert kwargs == [
        {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "start_new_session": True,
        }
    ]


_FAKE_VIEWER = """#!/bin/sh
echo $$ > "$VIEWER_PID_FILE"
echo "Gtk-WARNING: noise from the viewer" >&2
exec sleep 30
"""

_BIBTUI_STANDIN = """
import sys, time
from bibtui.utils.opener import open_with_default_app
open_with_default_app("/tmp/paper.pdf")
print("opened", flush=True)
time.sleep(30)
"""


@pytest.mark.skipif(sys.platform != "linux", reason="uses xdg-open and signals")
def test_viewer_survives_hangup_and_stays_quiet(tmp_path) -> None:
    """End to end: a stand-in for bibtui opens a fake viewer, then its process
    group gets the hang-up a closing terminal sends. The viewer must survive,
    and its stderr must not reach bibtui's terminal."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    viewer = bin_dir / "xdg-open"
    viewer.write_text(_FAKE_VIEWER)
    viewer.chmod(0o755)
    pid_file = tmp_path / "viewer.pid"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "VIEWER_PID_FILE": str(pid_file),
    }

    # Its own session, like bibtui running in its own terminal.
    app = subprocess.Popen(
        [sys.executable, "-c", _BIBTUI_STANDIN],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    viewer_pid = None
    try:
        assert app.stdout.readline().strip() == b"opened"
        for _ in range(100):
            if pid_file.exists() and pid_file.read_text().strip():
                break
            time.sleep(0.05)
        viewer_pid = int(pid_file.read_text())

        os.killpg(app.pid, signal.SIGHUP)  # the terminal closes
        app.wait(timeout=5)
        time.sleep(0.2)

        os.kill(viewer_pid, 0)  # raises ProcessLookupError if the viewer died
        assert b"noise from the viewer" not in app.stderr.read()
    finally:
        if app.poll() is None:
            app.kill()
        if viewer_pid is not None:
            try:
                os.kill(viewer_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
