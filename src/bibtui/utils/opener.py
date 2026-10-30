"""Open a file with the OS's default application, cross-platform.

A single place for the "open this PDF the way the OS would" logic, shared by
the main app (Open PDF action) and the Add PDF modal (space-to-preview).
Previously each call site only special-cased macOS (``open``) and otherwise
always shelled out to ``xdg-open`` — which doesn't exist on Windows, so the
Windows ``else`` branch silently failed there. See CHANGELOG.
"""

import os
import platform
import subprocess


def _spawn_detached(args: list[str]) -> None:
    """Start *args* fully detached from bibtui's terminal.

    * Output goes to ``/dev/null``: viewers print GTK/Qt/Poppler warnings, which
      would otherwise land on top of the TUI.
    * ``start_new_session`` puts the viewer in its own session, so the hang-up
      sent when bibtui's terminal closes (and Ctrl+C) doesn't reach it — the
      viewer stays open after bibtui exits.
    """
    subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def open_with_default_app(path: str) -> None:
    """Open *path* with the platform's default handler for its file type.

    Raises whatever the underlying platform call raises (``OSError``,
    ``subprocess.CalledProcessError``, ...) on failure — callers are expected
    to catch and report it.
    """
    system = platform.system()
    if system == "Windows":
        # os.startfile is Windows-only; it isn't in the typeshed stubs for
        # other platforms, hence the ignore comment.
        os.startfile(path)  # type: ignore[attr-defined]
    elif system == "Darwin":
        _spawn_detached(["open", path])
    else:
        _spawn_detached(["xdg-open", path])
