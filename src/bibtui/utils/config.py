import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "bibtui" / "config.toml"


@dataclass
class Config:
    pdf_base_dir: str = ""
    unpaywall_email: str = ""
    pdf_download_dir: str = ""
    auto_fetch_pdf: bool = True


def is_first_run() -> bool:
    """Return True if no config file exists yet (new installation)."""
    return not CONFIG_PATH.exists()


def _git_email() -> str:
    """Read user.email from global git config, or return empty string."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "config", "--global", "user.email"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def default_config() -> Config:
    """Return a Config pre-filled with sensible platform defaults."""
    home = Path.home()
    return Config(
        pdf_base_dir=str(home / "Documents" / "papers"),
        unpaywall_email=_git_email(),
        pdf_download_dir=str(home / "Downloads"),
    )


def load_config() -> Config:
    if not CONFIG_PATH.exists():
        return default_config()
    with open(CONFIG_PATH, "rb") as f:
        data = tomllib.load(f)
    pdf = data.get("pdf", {})
    return Config(
        pdf_base_dir=pdf.get("base_dir", ""),
        unpaywall_email=pdf.get("unpaywall_email", ""),
        pdf_download_dir=pdf.get("download_dir", ""),
        auto_fetch_pdf=pdf.get("auto_fetch_pdf", True),
    )


def _toml_escape(value: str) -> str:
    """Escape a string value for embedding in a TOML double-quoted string."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def save_config(config: Config) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "[pdf]",
        f'base_dir = "{_toml_escape(config.pdf_base_dir)}"',
        f'unpaywall_email = "{_toml_escape(config.unpaywall_email)}"',
        f'download_dir = "{_toml_escape(config.pdf_download_dir)}"',
        f'auto_fetch_pdf = {"true" if config.auto_fetch_pdf else "false"}',
        "",
    ]
    CONFIG_PATH.write_text("\n".join(lines), encoding="utf-8")


def parse_jabref_path(file_field: str, base_dir: str = "") -> str:
    """Resolve a JabRef-style file field to an absolute path.

    JabRef format: ``description:path:type``  (e.g. ``:Smith2023.pdf:PDF``)
    The description and type parts are optional.
    """
    path = file_field.strip()
    if ":" in path:
        parts = path.split(":")
        # ':path:type' → parts = ['', 'path', 'type']
        # 'desc:path:type' → parts = ['desc', 'path', 'type']
        path = parts[1] if len(parts) >= 2 else parts[0]
    path = path.strip()
    if base_dir and not os.path.isabs(path):
        path = os.path.join(base_dir, path)
    return path


def find_pdf_for_entry(file_field: str, entry_key: str, base_dir: str = "") -> str | None:
    """Return an existing PDF path for an entry, or None.

    First tries the path stored in *file_field*.  If that doesn't exist,
    falls back to a glob search for ``{entry_key}*.pdf`` in *base_dir* to
    handle filename mismatches between JabRef and bibtui naming conventions.
    """
    import glob as _glob

    if file_field:
        path = parse_jabref_path(file_field, base_dir)
        if os.path.exists(path):
            return path

    if base_dir and entry_key:
        matches = _glob.glob(os.path.join(base_dir, f"{entry_key}*.pdf"))
        if matches:
            return matches[0]

    return None


def format_jabref_path(filepath: str, base_dir: str = "") -> str:
    """Format a path as a JabRef file field value ``:filename.pdf:PDF``.

    If ``base_dir`` is set and ``filepath`` is inside it, store only the
    relative filename so the base directory stays configurable.
    """
    if base_dir:
        try:
            rel = os.path.relpath(filepath, base_dir)
            # relpath gives '..' paths if outside base_dir — keep absolute then
            if not rel.startswith(".."):
                filepath = rel
        except ValueError:
            pass  # different drives on Windows
    name = os.path.basename(filepath) if os.path.sep not in filepath else filepath
    # Use just the basename as the stored path to match JabRef convention
    return f":{name}:PDF"
