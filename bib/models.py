from __future__ import annotations
from dataclasses import dataclass, field


ENTRY_TYPES: dict[str, dict[str, list[str]]] = {
    "article": {
        "required": ["author", "title", "journal", "year"],
        "optional": ["volume", "number", "pages", "month", "doi", "abstract", "keywords"],
    },
    "book": {
        "required": ["author", "title", "publisher", "year"],
        "optional": ["editor", "volume", "series", "address", "edition", "month", "doi"],
    },
    "inproceedings": {
        "required": ["author", "title", "booktitle", "year"],
        "optional": ["editor", "volume", "series", "pages", "address", "month", "organization", "publisher", "doi"],
    },
    "incollection": {
        "required": ["author", "title", "booktitle", "publisher", "year"],
        "optional": ["editor", "volume", "series", "chapter", "pages", "address", "edition", "month", "doi"],
    },
    "phdthesis": {
        "required": ["author", "title", "school", "year"],
        "optional": ["address", "month", "doi"],
    },
    "mastersthesis": {
        "required": ["author", "title", "school", "year"],
        "optional": ["address", "month"],
    },
    "techreport": {
        "required": ["author", "title", "institution", "year"],
        "optional": ["type", "number", "address", "month", "doi"],
    },
    "misc": {
        "required": [],
        "optional": ["author", "title", "year", "month", "url", "doi"],
    },
}


@dataclass
class BibEntry:
    key: str
    entry_type: str
    title: str = ""
    author: str = ""
    year: str = ""
    journal: str = ""
    doi: str = ""
    abstract: str = ""
    keywords: str = ""
    rating: int = 0
    tags: list[str] = field(default_factory=list)
    file: str = ""
    raw_fields: dict[str, str] = field(default_factory=dict)

    @property
    def authors_short(self) -> str:
        """Return first author surname or 'Unknown'."""
        if not self.author:
            return "Unknown"
        parts = self.author.split(" and ")
        first = parts[0].strip()
        if "," in first:
            return first.split(",")[0].strip()
        words = first.split()
        return words[-1] if words else first

    @property
    def title_short(self, max_len: int = 60) -> str:
        if len(self.title) <= 60:
            return self.title
        return self.title[:57] + "..."

    @property
    def rating_stars(self) -> str:
        if self.rating == 0:
            return ""
        return "★" * self.rating

    def get_field(self, name: str) -> str:
        if name == "title":
            return self.title
        if name == "author":
            return self.author
        if name == "year":
            return self.year
        if name == "journal":
            return self.journal
        if name == "doi":
            return self.doi
        if name == "abstract":
            return self.abstract
        if name == "keywords":
            return self.keywords
        if name == "rating":
            return str(self.rating)
        if name == "tags":
            return ", ".join(self.tags)
        if name == "file":
            return self.file
        return self.raw_fields.get(name, "")

    def set_field(self, name: str, value: str) -> None:
        if name == "title":
            self.title = value
        elif name == "author":
            self.author = value
        elif name == "year":
            self.year = value
        elif name == "journal":
            self.journal = value
        elif name == "doi":
            self.doi = value
        elif name == "abstract":
            self.abstract = value
        elif name == "keywords":
            self.keywords = value
        elif name == "rating":
            try:
                self.rating = max(0, min(5, int(value)))
            except ValueError:
                pass
        elif name == "tags":
            self.tags = [t.strip() for t in value.split(",") if t.strip()]
        elif name == "file":
            self.file = value
        else:
            self.raw_fields[name] = value
