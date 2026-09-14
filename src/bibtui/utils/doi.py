import re


def normalize_doi(doi: str) -> str:
    """Normalize a DOI for comparison/lookup purposes.

    Lowercases and strips a leading ``https://doi.org/`` (or ``dx.doi.org``)
    prefix, so ``10.1000/Test`` and ``https://doi.org/10.1000/test`` compare
    equal.
    """
    norm = doi.strip()
    norm = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", norm, flags=re.IGNORECASE)
    return norm.lower()
