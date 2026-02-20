from __future__ import annotations
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "bib_tui" / "config.toml"


@dataclass
class Config:
    pdf_base_dir: str = ""


def load_config() -> Config:
    if not CONFIG_PATH.exists():
        return Config()
    with open(CONFIG_PATH, "rb") as f:
        data = tomllib.load(f)
    return Config(
        pdf_base_dir=data.get("pdf", {}).get("base_dir", ""),
    )


def save_config(config: Config) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        f'[pdf]\nbase_dir = "{config.pdf_base_dir}"\n',
        encoding="utf-8",
    )


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
