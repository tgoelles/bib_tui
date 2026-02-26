import os


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
