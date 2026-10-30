"""Tests for the arXiv API lookup (network mocked)."""

from unittest.mock import MagicMock, patch

import pytest

from bibtui.bib.arxiv import fetch_by_arxiv_id

_FEED = b"""<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns:arxiv="http://arxiv.org/schemas/atom" xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/hep-th/9711200v3</id>
    <title>The Large N Limit of Superconformal
      Field Theories and Supergravity</title>
    <summary>  We show that the large $N$ limit.  </summary>
    <published>1997-11-27T23:53:13Z</published>
    <arxiv:primary_category term="hep-th"/>
    <arxiv:journal_ref>Adv.Theor.Math.Phys.2:231-252,1998</arxiv:journal_ref>
    <author><name>Juan M. Maldacena</name></author>
  </entry>
</feed>"""

_EMPTY_FEED = b"""<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>arXiv Query</title></feed>"""


@pytest.fixture(autouse=True)
def _no_throttle(monkeypatch):
    monkeypatch.setattr("bibtui.bib.arxiv._throttle", lambda: None)


def _response(content: bytes) -> MagicMock:
    resp = MagicMock()
    resp.content = content
    return resp


def test_fetch_by_arxiv_id_builds_misc_entry() -> None:
    with patch("bibtui.bib.arxiv.httpx.get", return_value=_response(_FEED)):
        entry = fetch_by_arxiv_id("hep-th/9711200")

    assert entry.entry_type == "misc"
    assert entry.key == "Maldacena1997"
    assert entry.title == (
        "The Large N Limit of Superconformal Field Theories and Supergravity"
    )
    assert entry.author == "Maldacena, Juan M."
    assert entry.year == "1997"
    assert entry.doi == "10.48550/arXiv.hep-th/9711200"
    assert entry.url == "https://arxiv.org/abs/hep-th/9711200"
    assert entry.abstract == "We show that the large $N$ limit."
    assert entry.raw_fields["eprint"] == "hep-th/9711200"
    assert entry.raw_fields["archiveprefix"] == "arXiv"
    assert entry.raw_fields["primaryclass"] == "hep-th"
    assert entry.raw_fields["note"] == "Adv.Theor.Math.Phys.2:231-252,1998"


def test_fetch_by_arxiv_id_unknown_raises_lookup_error() -> None:
    with patch("bibtui.bib.arxiv.httpx.get", return_value=_response(_EMPTY_FEED)):
        with pytest.raises(LookupError):
            fetch_by_arxiv_id("9999.99999")
