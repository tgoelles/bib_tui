from dataclasses import dataclass, field

from bibtui.bib.authors import first_surname

READ_STATES: list[str] = ["", "to-read", "skimmed", "read"]

# Standard Unicode — readable without nerd fonts, pretty with them
READ_STATE_ICONS: dict[str, str] = {
    "": " ",
    "to-read": "○",
    "skimmed": "◑",
    "read": "●",
}

# JabRef priority: prio1=high, prio2=medium, prio3=low
PRIORITIES: list[int] = [0, 1, 2, 3]
PRIORITY_ICONS: dict[int, str] = {0: " ", 1: "↑", 2: "→", 3: "↓"}
PRIORITY_LABELS: dict[int, str] = {0: "unset", 1: "high", 2: "medium", 3: "low"}

ENTRY_TYPES: dict[str, dict[str, list[str]]] = {
    "article": {
        "required": ["author", "title", "journal", "year"],
        "optional": [
            "volume",
            "number",
            "pages",
            "month",
            "doi",
            "abstract",
            "keywords",
        ],
    },
    "book": {
        "required": ["author", "title", "publisher", "year"],
        "optional": [
            "editor",
            "volume",
            "series",
            "address",
            "edition",
            "month",
            "doi",
        ],
    },
    "inproceedings": {
        "required": ["author", "title", "booktitle", "year"],
        "optional": [
            "editor",
            "volume",
            "series",
            "pages",
            "address",
            "month",
            "organization",
            "publisher",
            "doi",
        ],
    },
    "incollection": {
        "required": ["author", "title", "booktitle", "publisher", "year"],
        "optional": [
            "editor",
            "volume",
            "series",
            "chapter",
            "pages",
            "address",
            "edition",
            "month",
            "doi",
        ],
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

# Common BibTeX / biblatex field names offered as quick picks when the user
# adds a custom field to a new entry. Not exhaustive and not type-specific —
# just a curated shortlist; the user can always type any field name instead.
COMMON_FIELDS: list[str] = [
    "note",
    "month",
    "number",
    "volume",
    "pages",
    "address",
    "publisher",
    "series",
    "edition",
    "editor",
    "organization",
    "institution",
    "school",
    "booktitle",
    "chapter",
    "howpublished",
    "type",
    "isbn",
    "issn",
    "url",
    "doi",
    "language",
    "annote",
    "crossref",
    "urldate",
    "eprint",
]


@dataclass
class BibEntry:
    key: str
    entry_type: str
    title: str = ""
    author: str = ""
    year: str = ""
    journal: str = ""
    doi: str = ""
    url: str = ""
    abstract: str = ""
    keywords: str = ""
    comment: str = ""
    rating: int = 0
    read_state: str = ""  # one of READ_STATES
    priority: int = 0  # 0=unset, 1=high, 2=medium, 3=low (JabRef prio1/prio2/prio3)
    file: str = ""
    raw_fields: dict[str, str] = field(default_factory=dict)

    @property
    def url_icon(self) -> str:
        # A plain Unicode arrow, not an emoji-presentation glyph like 🔗 —
        # every other status icon in the table (state, priority, PDF) is a
        # plain symbol that renders in any monospace terminal font; 🔗
        # requires color-emoji glyph support many terminals lack, where it
        # renders as nothing at all rather than a visible fallback box.
        return "↗" if self.url else " "

    @property
    def authors_short(self) -> str:
        """Return the first author's surname (LaTeX decoded) or 'Unknown'."""
        return first_surname(self.author) or "Unknown"

    @property
    def title_short(self) -> str:
        if len(self.title) <= 60:
            return self.title
        return self.title[:57] + "..."

    @property
    def read_state_icon(self) -> str:
        return READ_STATE_ICONS.get(self.read_state, " ")

    def cycle_read_state(self) -> None:
        idx = (
            READ_STATES.index(self.read_state) if self.read_state in READ_STATES else 0
        )
        self.read_state = READ_STATES[(idx + 1) % len(READ_STATES)]

    @property
    def priority_icon(self) -> str:
        return PRIORITY_ICONS.get(self.priority, " ")

    @property
    def priority_label(self) -> str:
        return PRIORITY_LABELS.get(self.priority, "unset")

    def cycle_priority(self) -> None:
        self.priority = (self.priority + 1) % 4

    @property
    def keywords_list(self) -> list[str]:
        return [k.strip() for k in self.keywords.split(",") if k.strip()]

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
        if name == "url":
            return self.url
        if name == "abstract":
            return self.abstract
        if name == "keywords":
            return self.keywords
        if name == "rating":
            return str(self.rating)
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
        elif name == "url":
            self.url = value
        elif name == "abstract":
            self.abstract = value
        elif name == "keywords":
            self.keywords = value
        elif name == "rating":
            try:
                self.rating = max(0, min(5, int(value)))
            except ValueError:
                pass
        elif name == "file":
            self.file = value
        else:
            self.raw_fields[name] = value
