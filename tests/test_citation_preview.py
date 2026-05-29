import unicodedata
from pathlib import Path

import pytest

from bibtui.bib.citation_preview import (
    available_csl_styles,
    csl_style_path,
    default_csl_style_key,
    render_citation_preview,
)
from bibtui.bib.models import BibEntry


@pytest.fixture(autouse=True)
def _use_temp_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("bibtui.utils.config.CONFIG_PATH", tmp_path / "config.toml")


def test_copernicus_style_is_available() -> None:
    keys = [key for _label, key in available_csl_styles()]
    assert "copernicus-publications" in keys
    assert csl_style_path("copernicus-publications").exists()


def test_requested_default_styles_are_available() -> None:
    keys = {key for _label, key in available_csl_styles()}
    assert {
        "copernicus-publications",
        "apa",
        "ieee",
        "vancouver",
        "chicago-author-date",
        "harvard-cite-them-right",
    }.issubset(keys)


def test_default_style_is_resolved() -> None:
    assert default_csl_style_key() == "copernicus-publications"


def test_render_citation_preview_for_article() -> None:
    entry = BibEntry(
        key="Demo2024",
        entry_type="article",
        title="A demonstration article",
        author="Doe, Jane and Smith, John",
        year="2024",
        journal="Journal of Tests",
        doi="10.1234/demo",
    )

    rendered = render_citation_preview(entry, "copernicus-publications")

    assert rendered
    assert "A demonstration article" in rendered
    assert "2024" in rendered


def test_render_citation_preview_unknown_style_returns_empty() -> None:
    entry = BibEntry(key="x", entry_type="article", title="X")
    assert render_citation_preview(entry, "style-that-does-not-exist") == ""


def test_render_citation_preview_decodes_latex_escapes() -> None:
    entry = BibEntry(
        key="Oerlemans1991",
        entry_type="article",
        title="A model for the surface balance of ice masses",
        author="Oerlemans, J.",
        year="1991",
        journal='Zeitschrift f{\\"{u}}r Gletscherkunde und Glacialgeologie',
        raw_fields={"pages": "63--83"},
    )

    rendered = render_citation_preview(entry, "copernicus-publications")
    rendered_norm = unicodedata.normalize("NFC", rendered)

    assert "für" in rendered_norm
    assert '\\"{u}' not in rendered_norm
