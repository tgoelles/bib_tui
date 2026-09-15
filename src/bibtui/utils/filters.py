"""Saved filter presets ("smart collections") — permanent, user-editable.

Mirrors :mod:`bibtui.utils.config`: TOML on disk, a plain dataclass in
memory, and the same "back up and start fresh" behavior for a corrupt file
so a bad edit never gets silently overwritten. Stored separately from
config.toml (its own file, same directory) so it can be hand-edited or
version-controlled independently of the rest of the app's settings.

A preset is deliberately just a name plus a query string in the same syntax
as the search box (see :mod:`bibtui.widgets.entry_list`) — no separate
filter language to learn, and any query typed into the search box can be
saved verbatim.
"""

import shutil
import tomllib
from dataclasses import dataclass, field

import tomli_w

from bibtui.utils.config import CONFIG_PATH

FILTERS_PATH = CONFIG_PATH.parent / "filters.toml"


@dataclass
class FilterPreset:
    name: str
    query: str


@dataclass
class FilterStore:
    presets: list[FilterPreset] = field(default_factory=list)
    active: str = ""

    def find(self, name: str) -> FilterPreset | None:
        """Look up a preset by name, case-insensitively."""
        target = name.strip().lower()
        for preset in self.presets:
            if preset.name.lower() == target:
                return preset
        return None

    def upsert(self, preset: FilterPreset) -> None:
        """Add *preset*, or replace the existing one with the same name."""
        target = preset.name.strip().lower()
        for i, existing in enumerate(self.presets):
            if existing.name.lower() == target:
                self.presets[i] = preset
                return
        self.presets.append(preset)

    def remove(self, name: str) -> None:
        """Remove the preset named *name*, if any. Clears ``active`` if it matches."""
        target = name.strip().lower()
        self.presets = [p for p in self.presets if p.name.lower() != target]
        if self.active.lower() == target:
            self.active = ""


def _backup_corrupt_filters() -> None:
    """Move an unparseable filters file aside so it is never silently overwritten."""
    backup = FILTERS_PATH.with_suffix(FILTERS_PATH.suffix + ".corrupt")
    try:
        shutil.move(str(FILTERS_PATH), str(backup))
    except OSError:
        pass


def load_filters() -> FilterStore:
    if not FILTERS_PATH.exists():
        return FilterStore()
    try:
        with open(FILTERS_PATH, "rb") as f:
            data = tomllib.load(f)
    except OSError:
        return FilterStore()
    except tomllib.TOMLDecodeError:
        _backup_corrupt_filters()
        return FilterStore()

    presets: list[FilterPreset] = []
    for raw in data.get("filter", []):
        if not isinstance(raw, dict):
            continue
        name = raw.get("name", "")
        query = raw.get("query", "")
        if not isinstance(name, str) or not isinstance(query, str):
            continue
        name = name.strip()
        if not name or not query:
            continue
        presets.append(FilterPreset(name=name, query=query))

    active = data.get("active", "")
    if not isinstance(active, str):
        active = ""

    return FilterStore(presets=presets, active=active)


def save_filters(store: FilterStore) -> None:
    FILTERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "active": store.active,
        "filter": [
            {"name": preset.name, "query": preset.query} for preset in store.presets
        ],
    }
    with open(FILTERS_PATH, "wb") as f:
        tomli_w.dump(data, f)
