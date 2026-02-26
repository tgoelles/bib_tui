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
    try:
        with open(CONFIG_PATH, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return default_config()
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
        f"auto_fetch_pdf = {'true' if config.auto_fetch_pdf else 'false'}",
        "",
    ]
    CONFIG_PATH.write_text("\n".join(lines), encoding="utf-8")
