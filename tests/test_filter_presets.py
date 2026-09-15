"""Pilot-based tests for saved filter presets: EntryList, FilterPresetModal,
and the `f` app action end to end — modeled on test_pdf_actions_modal.py.
"""

from textual.widgets import ListView

from bibtui.app import BibTuiApp
from bibtui.utils.filters import FilterPreset, FilterStore, load_filters, save_filters
from bibtui.widgets.entry_list import EntryList
from bibtui.widgets.modals import FilterEditModal, FilterPresetModal

BIB = "tests/bib_examples/MyCollection.bib"

# FILTERS_PATH is isolated per test by the autouse fixture in conftest.py.


# ---------------------------------------------------------------------------
# EntryList: preset + search layering
# ---------------------------------------------------------------------------


async def test_set_preset_narrows_table() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        el = app.query_one(EntryList)
        total = len(el.filtered_entries)

        el.set_preset("Project X", "y:2020")
        await pilot.pause()
        narrowed = len(el.filtered_entries)

        assert 0 < narrowed < total


async def test_search_refines_within_active_preset() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        el = app.query_one(EntryList)
        el.set_preset("Project X", "y:2020")
        await pilot.pause()
        within_preset = len(el.filtered_entries)

        search = app.query_one("#search-input")
        search.value = "climate"
        await pilot.pause()
        refined = len(el.filtered_entries)

        assert refined <= within_preset


async def test_esc_clears_search_but_keeps_preset() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        el = app.query_one(EntryList)
        el.set_preset("Project X", "y:2020")
        await pilot.pause()

        search = app.query_one("#search-input")
        search.value = "smith"
        search.focus()
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

        assert el.active_preset[0] == "Project X"
        assert el.search_query == ""


async def test_preset_bar_shows_name_query_and_counts() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        el = app.query_one(EntryList)
        total = len(el.filtered_entries)
        el.set_preset("Project X", "y:2020")
        await pilot.pause()

        bar = app.query_one("#preset-bar")
        assert bar.display is True
        text = str(bar.render())
        assert "Project X" in text
        assert "y:2020" in text
        assert f"{len(el.filtered_entries)} / {total}" in text


async def test_preset_bar_hidden_when_no_preset() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        bar = app.query_one("#preset-bar")
        assert bar.display is False


async def test_clearing_preset_restores_all_entries() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        el = app.query_one(EntryList)
        total = len(el.filtered_entries)
        el.set_preset("Project X", "y:2020")
        await pilot.pause()
        el.set_preset("", "")
        await pilot.pause()

        assert len(el.filtered_entries) == total
        assert app.query_one("#preset-bar").display is False


async def test_refresh_entries_keeps_preset_applied() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        el = app.query_one(EntryList)
        el.set_preset("Project X", "y:2020")
        await pilot.pause()
        narrowed = len(el.filtered_entries)

        el.refresh_entries(el._all_entries)
        await pilot.pause()

        assert el.active_preset[0] == "Project X"
        assert len(el.filtered_entries) == narrowed


async def test_set_columns_keeps_preset_applied() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        el = app.query_one(EntryList)
        el.set_preset("Project X", "y:2020")
        await pilot.pause()
        narrowed = len(el.filtered_entries)

        el.set_columns(["title", "year"])
        await pilot.pause()

        assert el.active_preset[0] == "Project X"
        assert len(el.filtered_entries) == narrowed


# ---------------------------------------------------------------------------
# App wiring: `f`, restore-on-start, persistence
# ---------------------------------------------------------------------------


async def test_f_opens_filter_preset_modal() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        assert isinstance(app.screen, FilterPresetModal)


async def test_active_preset_row_highlighted_on_open() -> None:
    app = BibTuiApp(BIB)
    app._filter_store = FilterStore(
        presets=[
            FilterPreset(name="Project X", query="y:2020"),
            FilterPreset(name="To read", query="r:to-read"),
        ],
        active="To read",
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_filter_presets()
        await pilot.pause()
        lv = app.screen.query_one(ListView)
        assert lv.index == 2  # row 0 = All entries, 1 = Project X, 2 = To read


async def test_all_entries_row_highlighted_on_open_when_no_active_preset() -> None:
    app = BibTuiApp(BIB)
    app._filter_store = FilterStore(
        presets=[FilterPreset(name="Project X", query="y:2020")], active=""
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_filter_presets()
        await pilot.pause()
        lv = app.screen.query_one(ListView)
        assert lv.index == 0


async def test_choosing_preset_activates_it_and_persists() -> None:
    app = BibTuiApp(BIB)
    app._filter_store = FilterStore(
        presets=[FilterPreset(name="Project X", query="y:2020")]
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        await pilot.press("1")
        await pilot.pause()

        el = app.query_one(EntryList)
        assert el.active_preset == ("Project X", "y:2020")
        assert app._filter_store.active == "Project X"
        assert load_filters().active == "Project X"


async def test_choosing_all_entries_clears_preset() -> None:
    app = BibTuiApp(BIB)
    app._filter_store = FilterStore(
        presets=[FilterPreset(name="Project X", query="y:2020")], active="Project X"
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        el = app.query_one(EntryList)
        el.set_preset("Project X", "y:2020")
        await pilot.pause()

        await pilot.press("f")
        await pilot.pause()
        await pilot.press("0")
        await pilot.pause()

        assert el.active_preset == ("", "")
        assert app._filter_store.active == ""


async def test_active_preset_restored_on_start() -> None:
    save_filters(
        FilterStore(
            presets=[FilterPreset(name="Project X", query="y:2020")],
            active="Project X",
        )
    )

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        el = app.query_one(EntryList)
        assert el.active_preset == ("Project X", "y:2020")
        assert app.sub_title == "Filter: Project X"


async def test_unknown_active_preset_is_ignored_on_start() -> None:
    save_filters(FilterStore(presets=[], active="Ghost"))

    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        el = app.query_one(EntryList)
        assert el.active_preset == ("", "")
        assert app._filter_store.active == ""


# ---------------------------------------------------------------------------
# Header title/subtitle indicator
# ---------------------------------------------------------------------------


async def test_header_subtitle_blank_with_no_active_filter() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "MyCollection.bib" in app.title
        assert app.sub_title == ""


async def test_header_subtitle_shows_active_filter_after_choosing() -> None:
    app = BibTuiApp(BIB)
    app._filter_store = FilterStore(
        presets=[FilterPreset(name="Project X", query="y:2020")]
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        await pilot.press("1")
        await pilot.pause()
        assert app.sub_title == "Filter: Project X"


async def test_header_subtitle_clears_when_preset_cleared() -> None:
    app = BibTuiApp(BIB)
    app._filter_store = FilterStore(
        presets=[FilterPreset(name="Project X", query="y:2020")], active="Project X"
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        el = app.query_one(EntryList)
        el.set_preset("Project X", "y:2020")
        app._update_title()
        await pilot.pause()
        assert app.sub_title == "Filter: Project X"

        await pilot.press("f")
        await pilot.pause()
        await pilot.press("0")
        await pilot.pause()
        assert app.sub_title == ""


# ---------------------------------------------------------------------------
# FilterPresetModal: save current search, edit, delete
# ---------------------------------------------------------------------------


async def test_save_current_search_prefills_edit_modal() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        search = app.query_one("#search-input")
        search.value = "y:2020"
        await pilot.pause()

        app.action_filter_presets()
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()

        assert isinstance(app.screen, FilterEditModal)
        query_input = app.screen.query_one("#filter-query")
        assert query_input.value == "y:2020"


async def test_save_current_search_adds_preset_and_persists() -> None:
    app = BibTuiApp(BIB)
    async with app.run_test() as pilot:
        await pilot.pause()
        search = app.query_one("#search-input")
        search.value = "y:2020"
        await pilot.pause()

        app.action_filter_presets()
        await pilot.pause()
        preset_modal = app.screen
        await pilot.press("w")
        await pilot.pause()

        edit_modal = app.screen
        edit_modal.query_one("#filter-name").value = "Project X"
        await pilot.press("ctrl+s")
        await pilot.pause()

        assert app.screen is preset_modal
        assert preset_modal._store.find("Project X").query == "y:2020"
        assert load_filters().find("Project X") is not None


async def test_delete_highlighted_preset_removes_it() -> None:
    app = BibTuiApp(BIB)
    app._filter_store = FilterStore(
        presets=[FilterPreset(name="Project X", query="y:2020")], active="Project X"
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_filter_presets()
        await pilot.pause()
        preset_modal = app.screen
        preset_modal.query_one("ListView").index = 1  # highlight "Project X"

        # Exercise the confirmed-delete path directly rather than driving the
        # separate ConfirmModal's own UI (covered by its own tests).
        preset_modal._on_delete_confirmed(True, "Project X")
        await pilot.pause()

        assert preset_modal._store.presets == []
        assert preset_modal._store.active == ""
        assert load_filters().presets == []


async def test_deleting_active_preset_resets_live_view_to_all_entries() -> None:
    app = BibTuiApp(BIB)
    app._filter_store = FilterStore(
        presets=[FilterPreset(name="Project X", query="y:2020")], active="Project X"
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        el = app.query_one(EntryList)
        el.set_preset("Project X", "y:2020")
        app._update_title()
        await pilot.pause()
        total = len(el._all_entries)
        assert len(el.filtered_entries) < total
        assert app.sub_title == "Filter: Project X"

        app.action_filter_presets()
        await pilot.pause()
        preset_modal = app.screen
        preset_modal.query_one(ListView).index = 1
        preset_modal._on_delete_confirmed(True, "Project X")
        await pilot.pause()

        assert el.active_preset == ("", "")
        assert len(el.filtered_entries) == total
        assert app.sub_title == ""
        assert preset_modal.query_one(ListView).index == 0


async def test_deleting_non_active_preset_also_resets_to_all_entries() -> None:
    app = BibTuiApp(BIB)
    app._filter_store = FilterStore(
        presets=[
            FilterPreset(name="Project X", query="y:2020"),
            FilterPreset(name="To read", query="r:to-read"),
        ],
        active="To read",
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        el = app.query_one(EntryList)
        el.set_preset("To read", "r:to-read")
        await pilot.pause()

        app.action_filter_presets()
        await pilot.pause()
        preset_modal = app.screen
        preset_modal.query_one(ListView).index = 1  # "Project X", not active
        preset_modal._on_delete_confirmed(True, "Project X")
        await pilot.pause()

        assert el.active_preset == ("", "")
        assert preset_modal.query_one(ListView).index == 0


async def test_deleting_all_entries_row_is_refused_with_a_notice() -> None:
    app = BibTuiApp(BIB)
    app._filter_store = FilterStore(
        presets=[FilterPreset(name="Project X", query="y:2020")]
    )
    notifications: list[tuple[str, str | None]] = []
    async with app.run_test() as pilot:
        await pilot.pause()
        app.notify = lambda message, **kwargs: notifications.append(
            (message, kwargs.get("severity"))
        )

        app.action_filter_presets()
        await pilot.pause()
        preset_modal = app.screen
        preset_modal.query_one(ListView).index = 0  # "All entries"
        await pilot.press("d")
        await pilot.pause()

        assert app.screen is preset_modal  # no ConfirmModal was pushed
        assert preset_modal._store.find("Project X") is not None
        assert len(notifications) == 1
        assert "All entries" in notifications[0][0]
        assert notifications[0][1] == "warning"


async def test_edit_highlighted_preset_updates_name_and_query() -> None:
    app = BibTuiApp(BIB)
    app._filter_store = FilterStore(
        presets=[FilterPreset(name="Project X", query="y:2020")], active="Project X"
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_filter_presets()
        await pilot.pause()
        preset_modal = app.screen

        preset_modal._on_edit_done("Project X", ("Project X", "y:2010-"))
        await pilot.pause()

        updated = preset_modal._store.find("Project X")
        assert updated is not None
        assert updated.query == "y:2010-"
        assert preset_modal._store.active == "Project X"
        assert load_filters().find("Project X").query == "y:2010-"
