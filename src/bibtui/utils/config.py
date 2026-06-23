import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import tomli_w

CONFIG_PATH = Path.home() / ".config" / "bibtui" / "config.toml"
_BUNDLED_CSL_DIR = Path(__file__).resolve().parents[1] / "csl"
_DEFAULT_CSL_FILES = (
    "copernicus-publications.csl",
    "apa.csl",
    "ieee.csl",
    "vancouver.csl",
    "chicago-author-date.csl",
    "harvard-cite-them-right.csl",
)


@dataclass
class Config:
    pdf_base_dir: str = ""
    unpaywall_email: str = ""
    openalex_api_key: str = ""
    pdf_download_dir: str = ""
    auto_fetch_pdf: bool = True
    update_last_check_utc: str = ""
    update_last_notified_utc: str = ""
    update_latest_version: str = ""
    check_for_updates: bool = True
    recent_files: list[str] = field(default_factory=list)
    theme: str = ""  # empty means auto-detect from OS/Omarchy
    default_citation_style: str = "copernicus-publications"


def csl_dir() -> Path:
    """Return the user CSL directory next to config.toml."""
    return CONFIG_PATH.parent / "csl"


def ensure_csl_styles() -> None:
    """Seed the user CSL directory with bundled default styles if missing."""
    target_dir = csl_dir()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return

    for filename in _DEFAULT_CSL_FILES:
        src = _BUNDLED_CSL_DIR / filename
        dst = target_dir / filename
        if dst.exists() or not src.exists():
            continue
        try:
            shutil.copy2(src, dst)
        except OSError:
            continue


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


def _backup_corrupt_config() -> None:
    """Move an unparseable config aside so it is never silently overwritten."""
    backup = CONFIG_PATH.with_suffix(CONFIG_PATH.suffix + ".corrupt")
    try:
        shutil.move(str(CONFIG_PATH), str(backup))
    except OSError:
        pass


def load_config() -> Config:
    ensure_csl_styles()
    if not CONFIG_PATH.exists():
        return default_config()
    try:
        with open(CONFIG_PATH, "rb") as f:
            data = tomllib.load(f)
    except OSError:
        return default_config()
    except tomllib.TOMLDecodeError:
        # The file exists but cannot be parsed. Preserve it before any later
        # save() overwrites it with defaults, so the user can recover values.
        _backup_corrupt_config()
        return default_config()
    pdf = data.get("pdf", {})
    api_keys = data.get("api_keys", {})
    updates = data.get("updates", {})
    files_section = data.get("files", {})
    ui_section = data.get("ui", {})
    recent_raw = files_section.get("recent", [])
    recent_files = [str(r) for r in recent_raw if isinstance(r, str)]
    return Config(
        pdf_base_dir=pdf.get("base_dir", ""),
        unpaywall_email=pdf.get("unpaywall_email", ""),
        openalex_api_key=api_keys.get("openalex_api_key", ""),
        pdf_download_dir=pdf.get("download_dir", ""),
        auto_fetch_pdf=pdf.get("auto_fetch_pdf", True),
        update_last_check_utc=updates.get("last_check_utc", ""),
        update_last_notified_utc=updates.get("last_notified_utc", ""),
        update_latest_version=updates.get("latest_version", ""),
        check_for_updates=updates.get("check_for_updates", True),
        recent_files=recent_files,
        theme=ui_section.get("theme", ""),
        default_citation_style=ui_section.get(
            "default_citation_style", "copernicus-publications"
        ),
    )


def save_config(config: Config) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "pdf": {
            "base_dir": config.pdf_base_dir,
            "unpaywall_email": config.unpaywall_email,
            "download_dir": config.pdf_download_dir,
            "auto_fetch_pdf": config.auto_fetch_pdf,
        },
        "api_keys": {
            "openalex_api_key": config.openalex_api_key,
        },
        "updates": {
            "last_check_utc": config.update_last_check_utc,
            "last_notified_utc": config.update_last_notified_utc,
            "latest_version": config.update_latest_version,
            "check_for_updates": config.check_for_updates,
        },
        "files": {
            "recent": config.recent_files[:8],
        },
        "ui": {
            "theme": config.theme,
            "default_citation_style": config.default_citation_style,
        },
    }
    with open(CONFIG_PATH, "wb") as f:
        tomli_w.dump(data, f)
    ensure_csl_styles()
