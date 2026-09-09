"""Write text to the OS clipboard through a native helper command.

Textual's :meth:`App.copy_to_clipboard` only emits an OSC 52 escape sequence.
Many setups ignore it: macOS Terminal.app has no OSC 52 support at all, and
iTerm2 and tmux keep it off by default.  This module shells out to the platform
clipboard tool as a reliable local path.  Callers should still emit OSC 52 too,
so copying keeps working over SSH and in terminals without a CLI clipboard tool.
"""

import shutil
import subprocess
import sys

_TIMEOUT = 5


def _candidates() -> list[list[str]]:
    """Clipboard-write commands to try, in priority order for this platform."""
    if sys.platform == "darwin":
        return [["pbcopy"]]
    if sys.platform == "win32":
        return [["clip"]]
    # Linux / *BSD: Wayland first, then the common X11 helpers.
    return [
        ["wl-copy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
    ]


def copy_to_os_clipboard(text: str) -> bool:
    """Write *text* to the OS clipboard using a native tool.

    Returns True on the first helper that succeeds, False when none is
    installed or every one fails.  Never raises.
    """
    payload = text.encode("utf-8")
    for argv in _candidates():
        if shutil.which(argv[0]) is None:
            continue
        try:
            subprocess.run(
                argv,
                input=payload,
                check=True,
                capture_output=True,
                timeout=_TIMEOUT,
            )
            return True
        except (OSError, subprocess.SubprocessError):
            continue
    return False
