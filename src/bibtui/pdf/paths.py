import os
import unicodedata


def _resolve_normalized(path: str) -> str | None:
    """Like ``os.path.exists`` but tolerant of Unicode normalization mismatches.

    Returns the path that actually exists on disk (which may differ from
    *path* only in how accented characters are encoded), or ``None``.

    A path built from text parsed out of a .bib file is normally in NFC form
    (the common form for UTF-8 text on Linux/Windows). On macOS, filenames
    written to disk by third-party tools (including some sync/cloud-drive
    clients) can end up in NFD form instead, so a byte-exact comparison of an
    NFC path against an NFD-named file fails even though the file is right
    there — the PDF looks "missing" only because of how its accented
    characters are encoded, not because it's actually absent.  Try the exact
    path first, then both normal forms, before giving up.
    """
    if os.path.exists(path):
        return path
    directory, name = os.path.split(path)
    if not name:
        return None
    for form in ("NFC", "NFD"):
        candidate = os.path.join(directory, unicodedata.normalize(form, name))
        if os.path.exists(candidate):
            return candidate
    return None


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


def find_pdf_for_entry(
    file_field: str, entry_key: str, base_dir: str = ""
) -> str | None:
    """Return an existing PDF path for an entry, or None.

    First tries the path stored in *file_field*.  If that doesn't exist,
    falls back to a glob search for ``{entry_key}*.pdf`` in *base_dir* to
    handle filename mismatches between JabRef and bibtui naming conventions.
    """
    import glob as _glob

    if file_field:
        path = parse_jabref_path(file_field, base_dir)
        resolved = _resolve_normalized(path)
        if resolved is not None:
            return resolved

    if base_dir and entry_key:
        matches = _glob.glob(os.path.join(base_dir, f"{entry_key}*.pdf"))
        if matches:
            return matches[0]

    return None


def pdf_link_state(file_field: str, entry_key: str, base_dir: str = "") -> str:
    """Classify an entry's local-PDF state: one of ``"none"`` (no ``file``
    field at all), ``"found"`` (linked and located via
    :func:`find_pdf_for_entry`), or ``"missing"`` (linked but not located).

    The single source of truth for "is there a local PDF, and in what
    state" — used by the table's file-status column, the detail pane's
    compact PDF status label, and the PDF actions menu's row filtering, so
    all three always agree (they used to each answer this slightly
    differently, which could show the table and detail pane disagreeing).
    """
    if not file_field:
        return "none"
    return "found" if find_pdf_for_entry(file_field, entry_key, base_dir) else "missing"


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
