import re

_DOI_URL_PREFIX_RE = re.compile(r"^https?://(?:dx\.)?doi\.org/", re.IGNORECASE)


def normalize_doi(doi: str, *, lower: bool = True) -> str:
    """Normalize a DOI for comparison/lookup purposes.

    Strips a leading ``https://doi.org/`` (or ``dx.doi.org``) prefix, so
    ``10.1000/Test`` and ``https://doi.org/10.1000/test`` compare equal.
    Lowercases by default; pass ``lower=False`` for a case-preserving strip
    (e.g. building a lookup URL, where the DOI's own case must survive).
    """
    norm = _DOI_URL_PREFIX_RE.sub("", doi.strip())
    return norm.lower() if lower else norm
