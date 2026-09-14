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
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])
