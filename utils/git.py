from __future__ import annotations
import subprocess
import os


def commit(path: str, message: str) -> bool:
    """
    Stage the given file and create a git commit.
    Returns True if a commit was made, False otherwise.
    """
    dir_path = os.path.dirname(os.path.abspath(path))

    # Check if inside a git repo
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=dir_path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False

    # Stage the file
    subprocess.run(
        ["git", "add", os.path.abspath(path)],
        cwd=dir_path,
        capture_output=True,
    )

    # Check if there's anything staged
    status = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=dir_path,
        capture_output=True,
    )
    if status.returncode == 0:
        # Nothing staged (no changes)
        return False

    # Commit
    result = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=dir_path,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0
