from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from rich.console import Console
from rich.text import Text
from textual.widgets import DataTable, Input, Select, Static, TextArea

from tskmngr.app import TskmngrApp
from tskmngr.models import Priority, Repeat, Status, Task, Unit
from tskmngr.storage import load_tasks, save_task
from tskmngr.widgets import saving, task_form
from tskmngr.widgets.confirm_discard import ConfirmDiscardScreen
from tskmngr.widgets.task_detail import TaskDetailScreen
from tskmngr.widgets.task_form import (
    TaskFormScreen,
    format_tags,
    parse_tags,
    suggest_tag,
    tidy_notes,
)
from tskmngr.widgets.task_list import TaskListScreen

CREATED = datetime(2026, 10, 28, 9, 15, tzinfo=UTC)


def make_task(task_id: str, title: str, **fields: object) -> Task:
    return Task(id=task_id, title=title, created=CREATED, updated=CREATED, **fields)


def rendered(renderable: object) -> str:
    console = Console(width=80, record=True)
    console.print(renderable)
    return console.export_text()


def loaded(directory: Path) -> dict[str, Task]:
    return {source.task.id: source.task for source in load_tasks(directory).tasks}


def error_text(screen: TaskFormScreen, field: str) -> str | None:
    """The error shown under a field, or None while it's hidden."""
    error = screen.query_one(f"#{field}-error", Static)
    if not error.has_class("-shown"):
        return None
    content = error.content
    return content.plain if isinstance(content, Text) else str(content)


def record_notifications(app: TskmngrApp) -> list[str]:
    """Collect the messages of the app's notifications."""
    messages: list[str] = []

    def notify(message: str, **_: object) -> None:
        messages.append(message)

    app.notify = notify  # type: ignore[method-assign]
    return messages


def fill(screen: TaskFormScreen, **values: str) -> None:
    for field, value in values.items():
        screen.query_one(f"#{field}", Input).value = value


def cursor_task_id(app: TskmngrApp) -> str:
    screen = app.screen
    assert isinstance(screen, TaskListScreen)
    table = screen.query_one("#task-table", DataTable)
    return screen.tasks[table.cursor_row].task.id


def test_parse_tags_splits_on_spaces_and_commas() -> None:
    assert parse_tags(" errands, home  Work,,x ") == ["errands", "home", "work", "x"]


def test_parse_tags_merges_duplicates_ignoring_case() -> None:
    assert parse_tags("home Home, home") == ["home"]


def test_parse_tags_of_blank_text_is_empty() -> None:
    assert parse_tags("  ,  ") == []


def test_format_tags_reads_back_with_parse_tags() -> None:
    assert parse_tags(format_tags(("errands", "home"))) == ["errands", "home"]


TAGS = ("errands", "home", "homework", "work")


def test_suggest_tag_completes_the_tag_being_typed() -> None:
    assert suggest_tag("e", TAGS) == "errands"
    assert suggest_tag("work, ho", TAGS) == "work, home"


def test_suggest_tag_takes_the_first_match_alphabetically() -> None:
    assert suggest_tag("h", ("homework", "home")) == "home"


def test_suggest_tag_keeps_the_text_as_typed() -> None:
    assert suggest_tag("Work,  Er", TAGS) == "Work,  Errands"


def test_suggest_tag_skips_tags_already_typed() -> None:
    assert suggest_tag("home ho", TAGS) == "home homework"
    assert suggest_tag("errands, e", TAGS) is None


def test_suggest_tag_suggests_nothing_for_a_whole_tag() -> None:
    assert suggest_tag("home", TAGS) is None


def test_suggest_tag_suggests_nothing_without_a_match() -> None:
    assert suggest_tag("x", TAGS) is None
    assert suggest_tag("e", ()) is None


@pytest.mark.parametrize("text", ["", "home ", "home,", "home, "])
def test_suggest_tag_suggests_nothing_while_no_tag_is_typed(text: str) -> None:
    assert suggest_tag(text, TAGS) is None


def test_tidy_notes_adds_a_final_newline() -> None:
    assert tidy_notes("One\ntwo") == "One\ntwo\n"


def test_tidy_notes_adds_the_given_newline() -> None:
    assert tidy_notes("One\r\ntwo", "\r\n") == "One\r\ntwo\r\n"


def test_tidy_notes_keeps_notes_that_end_with_a_newline() -> None:
    assert tidy_notes("One\n\n") == "One\n\n"
    assert tidy_notes("One\r\n", "\n") == "One\r\n"


def test_tidy_notes_of_whitespace_is_no_notes() -> None:
    assert tidy_notes(" \n\t\n") == ""
    assert tidy_notes("") == ""


def test_bindings_have_stable_ids() -> None:
    ids = {binding.id for binding in TaskFormScreen.BINDINGS}

    assert ids == {"task_form.save", "task_form.cancel"}


@pytest.mark.asyncio
async def test_n_opens_an_empty_form_with_defaults(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("n")

        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        assert screen.sub_title == "New task"
        assert screen.query_one("#title", Input).has_focus
        assert screen.query_one("#title", Input).value == ""
        assert screen.query_one("#status", Select).value == Status.TODO
        assert screen.query_one("#priority", Select).value == Priority.NORMAL
        assert screen.query_one("#due", Input).value == ""
        assert screen.query_one("#tags", Input).value == ""
        assert screen.query_one("#notes", TextArea).text == ""


@pytest.mark.asyncio
async def test_saving_a_new_task_writes_it_and_selects_it(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "First", due=date(2026, 11, 2)), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("n")
        await pilot.press(*"Buy milk")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        fill(screen, due="2026-11-01", tags="Errands, home")
        screen.query_one("#priority", Select).value = Priority.HIGH
        await pilot.press("ctrl+s")

        assert isinstance(app.screen, TaskListScreen)
        tasks = loaded(tmp_path)
        assert len(tasks) == 2
        (new,) = (task for task in tasks.values() if task.id != "AAAA")
        assert new.title == "Buy milk"
        assert new.status == Status.TODO
        assert new.priority == Priority.HIGH
        assert new.due == date(2026, 11, 1)
        assert new.tags == ("errands", "home")
        assert new.notes == ""
        # Due sooner than "First", so it's on top, and the cursor is on it.
        assert cursor_task_id(app) == new.id


@pytest.mark.asyncio
async def test_status_and_priority_are_picked_with_the_keyboard(
    tmp_path: Path,
) -> None:
    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("n", *"Task", "tab")
        # Open the status menu, move from "todo" to "doing", pick it.
        await pilot.press("enter", "down", "enter", "tab")
        await pilot.press("enter", "down", "enter")
        await pilot.press("ctrl+s")

        (task,) = loaded(tmp_path).values()
        assert task.status == Status.DOING
        assert task.priority == Priority.HIGH


@pytest.mark.asyncio
async def test_enter_moves_to_the_next_field_up_to_the_notes(
    tmp_path: Path,
) -> None:
    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("n", *"Task", "enter")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        assert screen.query_one("#status", Select).has_focus

        screen.query_one("#tags", Input).focus()
        await pilot.press(*"home", "enter")

        notes = screen.query_one("#notes", TextArea)
        assert notes.has_focus
        # In the notes, Enter starts a new line and doesn't save.
        await pilot.press(*"One", "enter", *"two", "enter")
        assert app.screen is screen
        assert notes.text == "One\ntwo\n"
        assert loaded(tmp_path) == {}

        await pilot.press("ctrl+s")

        assert isinstance(app.screen, TaskListScreen)
        (task,) = loaded(tmp_path).values()
        assert task.tags == ("home",)
        assert task.notes == "One\ntwo\n"


@pytest.mark.asyncio
async def test_tab_moves_out_of_the_notes(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("n")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        notes = screen.query_one("#notes", TextArea)
        notes.focus()
        await pilot.press("tab")

        assert not notes.has_focus
        assert notes.text == ""


@pytest.mark.asyncio
async def test_invalid_fields_are_shown_and_nothing_is_saved(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("n")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        fill(screen, title="   ", due="2026-13-01")
        screen.query_one("#tags", Input).focus()
        await pilot.press("ctrl+s")

        assert app.screen is screen
        assert loaded(tmp_path) == {}
        assert error_text(screen, "title") == "Must not be blank"
        assert error_text(screen, "due") == (
            "Expected a date like 2026-11-01, got '2026-13-01'"
        )
        assert error_text(screen, "tags") is None
        # The first field with a problem gets the focus.
        assert screen.query_one("#title", Input).has_focus


@pytest.mark.asyncio
async def test_errors_go_away_once_fixed(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("n")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        fill(screen, due="tomorrow")
        await pilot.press("ctrl+s")
        assert error_text(screen, "title") is not None

        fill(screen, title="Task")
        await pilot.press("ctrl+s")

        assert error_text(screen, "title") is None
        assert error_text(screen, "due") is not None
        assert app.screen is screen


@pytest.mark.asyncio
async def test_escape_without_changes_closes_at_once(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("n", "escape")

        assert isinstance(app.screen, TaskListScreen)
        assert loaded(tmp_path) == {}


@pytest.mark.asyncio
async def test_escape_with_changes_asks_and_y_discards(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("n", *"Task", "escape")

        assert isinstance(app.screen, ConfirmDiscardScreen)

        await pilot.press("y")

        assert isinstance(app.screen, TaskListScreen)
        assert loaded(tmp_path) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["n", "escape", "enter"])
async def test_declining_to_discard_keeps_editing(tmp_path: Path, key: str) -> None:
    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("n", *"Task")
        form = app.screen
        assert isinstance(form, TaskFormScreen)
        notes = form.query_one("#notes", TextArea)
        notes.focus()
        await pilot.press(*"Some notes", "escape")
        assert isinstance(app.screen, ConfirmDiscardScreen)

        # Enter presses the focused button, which is "No".
        await pilot.press(key)

        assert app.screen is form
        assert form.query_one("#title", Input).value == "Task"
        assert notes.text == "Some notes"
        assert notes.has_focus
        assert loaded(tmp_path) == {}


@pytest.mark.asyncio
async def test_changing_only_the_notes_asks_before_discarding(
    tmp_path: Path,
) -> None:
    save_task(tmp_path, make_task("AAAA", "First", notes="Old.\n"), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("e")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        screen.query_one("#notes", TextArea).text = "New.\n"
        await pilot.press("escape")

        assert isinstance(app.screen, ConfirmDiscardScreen)


@pytest.mark.asyncio
async def test_a_change_undone_by_hand_closes_at_once(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("e")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        fill(screen, title="Other")
        fill(screen, title="First")
        await pilot.press("escape")

        assert isinstance(app.screen, TaskListScreen)


@pytest.mark.asyncio
async def test_e_on_the_list_edits_the_task_under_the_cursor(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "First", due=date(2026, 11, 2)), None)
    second = make_task(
        "BBBB",
        "Second",
        status=Status.DOING,
        priority=Priority.LOW,
        due=date(2026, 11, 3),
        tags=("home", "work"),
    )
    save_task(tmp_path, second, None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("down", "e")

        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        assert screen.sub_title == f"Edit {tmp_path / 'BBBB.md'}"
        assert screen.query_one("#title", Input).value == "Second"
        assert screen.query_one("#status", Select).value == Status.DOING
        assert screen.query_one("#priority", Select).value == Priority.LOW
        assert screen.query_one("#due", Input).value == "2026-11-03"
        assert screen.query_one("#tags", Input).value == "home, work"
        assert screen.query_one("#notes", TextArea).text == ""


@pytest.mark.asyncio
async def test_the_form_shows_the_notes_of_the_task(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "First", notes="Line one\n\n- item\n"), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("e")

        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        assert screen.query_one("#notes", TextArea).text == "Line one\n\n- item\n"


@pytest.mark.asyncio
async def test_e_does_nothing_without_tasks(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("e")

        assert isinstance(app.screen, TaskListScreen)


@pytest.mark.asyncio
async def test_saving_an_edit_keeps_notes_and_unknown_keys(tmp_path: Path) -> None:
    (tmp_path / "AAAA.md").write_text(
        "---\n"
        "title: First\n"
        "estimate: 2h  # my own key\n"
        "due: 2026-11-02\n"
        "created: 2026-10-28T09:15:00Z\n"
        "updated: 2026-10-28T09:15:00Z\n"
        "---\n"
        "\n"
        "Some notes.\n",
        encoding="utf-8",
    )

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("e")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        fill(screen, title="Renamed", due="", tags="new")
        await pilot.press("ctrl+s")

        assert isinstance(app.screen, TaskListScreen)
        task = loaded(tmp_path)["AAAA"]
        assert task.title == "Renamed"
        assert task.due is None
        assert task.tags == ("new",)
        assert task.notes == "Some notes.\n"
        assert task.created == CREATED
        assert task.updated > CREATED
        text = (tmp_path / "AAAA.md").read_text(encoding="utf-8")
        assert "estimate: 2h  # my own key\n" in text
        assert cursor_task_id(app) == "AAAA"


@pytest.mark.asyncio
async def test_saving_edited_notes_keeps_the_frontmatter(tmp_path: Path) -> None:
    frontmatter = (
        "---\n"
        "title: First\n"
        "estimate: 2h  # my own key\n"
        "created: 2026-10-28T09:15:00Z\n"
        "updated: 2026-10-28T09:15:00Z\n"
        "---\n"
    )
    (tmp_path / "AAAA.md").write_text(frontmatter + "\nOld notes.\n", encoding="utf-8")

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("e")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        screen.query_one("#notes", TextArea).text = "New notes,\n**bold**"
        await pilot.press("ctrl+s")

        assert isinstance(app.screen, TaskListScreen)
        task = loaded(tmp_path)["AAAA"]
        # The final newline is added.
        assert task.notes == "New notes,\n**bold**\n"
        assert task.updated > CREATED
        text = (tmp_path / "AAAA.md").read_text(encoding="utf-8")
        assert "estimate: 2h  # my own key\n" in text
        assert text.endswith("---\n\nNew notes,\n**bold**\n")


@pytest.mark.asyncio
async def test_edited_notes_keep_the_files_line_endings(tmp_path: Path) -> None:
    path = tmp_path / "AAAA.md"
    path.write_bytes(
        b"---\r\n"
        b"title: First\r\n"
        b"created: 2026-10-28T09:15:00Z\r\n"
        b"updated: 2026-10-28T09:15:00Z\r\n"
        b"---\r\n"
        b"\r\n"
        b"One\r\n"
    )

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("e")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        notes = screen.query_one("#notes", TextArea)
        notes.focus()
        notes.move_cursor(notes.document.end)
        await pilot.press(*"Two")
        await pilot.press("ctrl+s")

        assert isinstance(app.screen, TaskListScreen)
        assert loaded(tmp_path)["AAAA"].notes == "One\r\nTwo\r\n"
        assert path.read_bytes().endswith(b"One\r\nTwo\r\n")


@pytest.mark.asyncio
async def test_untouched_notes_are_kept_byte_for_byte(tmp_path: Path) -> None:
    # Mixed line endings and no final newline: the text area would change both.
    notes = "One\r\ntwo\nthree"
    path = tmp_path / "AAAA.md"
    path.write_bytes(
        b"---\n"
        b"title: First\n"
        b"created: 2026-10-28T09:15:00Z\n"
        b"updated: 2026-10-28T09:15:00Z\n"
        b"---\n"
        b"\n" + notes.encode()
    )

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("e")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        fill(screen, title="Renamed")
        await pilot.press("ctrl+s")

        assert isinstance(app.screen, TaskListScreen)
        assert loaded(tmp_path)["AAAA"].title == "Renamed"
        assert path.read_bytes().endswith(b"---\n\n" + notes.encode())


@pytest.mark.asyncio
async def test_clearing_the_notes_removes_them(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "First", notes="Old notes.\n"), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("e")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        screen.query_one("#notes", TextArea).text = "  \n\n"
        await pilot.press("ctrl+s")

        assert loaded(tmp_path)["AAAA"].notes == ""
        text = (tmp_path / "AAAA.md").read_text(encoding="utf-8")
        assert text.endswith("---\n")


@pytest.mark.asyncio
async def test_saving_without_changes_leaves_the_file_alone(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "First", tags=("home",)), None)
    before = (tmp_path / "AAAA.md").read_bytes()

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("e", "ctrl+s")

        assert isinstance(app.screen, TaskListScreen)
        assert (tmp_path / "AAAA.md").read_bytes() == before


@pytest.mark.asyncio
async def test_e_on_the_detail_screen_edits_and_shows_the_result(
    tmp_path: Path,
) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("enter", "e")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        fill(screen, title="Renamed")
        await pilot.press("ctrl+s")

        detail = app.screen
        assert isinstance(detail, TaskDetailScreen)
        assert detail.source.task.title == "Renamed"
        assert "Renamed" in rendered(detail.query_one("#fields", Static).content)
        assert not detail.query_one("#notes").display

        await pilot.press("e")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        screen.query_one("#notes", TextArea).text = "Some **notes**."
        await pilot.press("ctrl+s")

        assert app.screen is detail
        assert detail.source.task.notes == "Some **notes**.\n"
        assert detail.query_one("#notes").display
        assert not detail.query_one("#no-notes").display

        await pilot.press("escape")

        assert isinstance(app.screen, TaskListScreen)
        assert app.screen.tasks[0].task.title == "Renamed"


@pytest.mark.asyncio
async def test_cancelling_from_the_detail_screen_stays_there(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("enter", "e", "escape")

        assert isinstance(app.screen, TaskDetailScreen)


@pytest.mark.asyncio
async def test_a_conflict_is_shown_and_the_task_reloaded_not_overwritten(
    tmp_path: Path,
) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)

    app = TskmngrApp(tmp_path)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("e")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        fill(screen, title="Mine")
        # Someone edits the file by hand meanwhile.
        path = tmp_path / "AAAA.md"
        hand_edited = path.read_text(encoding="utf-8").replace("First", "Theirs")
        path.write_text(hand_edited, encoding="utf-8")
        await pilot.press("ctrl+s")

        assert path.read_text(encoding="utf-8") == hand_edited
        assert messages == [
            (
                "AAAA.md changed on disk since it was loaded. It was reloaded "
                "from disk; your changes weren't saved."
            )
        ]
        list_screen = app.screen
        assert isinstance(list_screen, TaskListScreen)
        assert list_screen.tasks[0].task.title == "Theirs"


@pytest.mark.asyncio
async def test_a_task_deleted_meanwhile_closes_the_detail_screen(
    tmp_path: Path,
) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)
    save_task(tmp_path, make_task("BBBB", "Second"), None)

    app = TskmngrApp(tmp_path)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("enter", "e")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        fill(screen, title="Mine")
        (tmp_path / "AAAA.md").unlink()
        await pilot.press("ctrl+s")

        assert not (tmp_path / "AAAA.md").exists()
        assert messages == [
            (
                "AAAA.md deleted on disk since it was loaded. It was reloaded "
                "from disk; your changes weren't saved."
            ),
            "AAAA.md is gone.",
        ]
        list_screen = app.screen
        assert isinstance(list_screen, TaskListScreen)
        assert [source.task.id for source in list_screen.tasks] == ["BBBB"]


@pytest.mark.asyncio
async def test_a_task_made_malformed_meanwhile_is_reported(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)

    app = TskmngrApp(tmp_path)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("enter", "e")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        fill(screen, title="Mine")
        (tmp_path / "AAAA.md").write_text("no frontmatter\n", encoding="utf-8")
        await pilot.press("ctrl+s")

        assert (tmp_path / "AAAA.md").read_text(encoding="utf-8") == (
            "no frontmatter\n"
        )
        assert len(messages) == 2
        assert messages[0].startswith("AAAA.md changed on disk")
        assert messages[1] == (
            "Can't load AAAA.md: line 1: must start with a '---' line followed "
            "by the frontmatter"
        )
        assert isinstance(app.screen, TaskListScreen)


@pytest.mark.asyncio
async def test_a_write_error_keeps_the_form_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*_: object) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(saving, "save_task", fail)

    app = TskmngrApp(tmp_path)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("n", *"Task", "ctrl+s")

        assert isinstance(app.screen, TaskFormScreen)
        assert app.screen.query_one("#title", Input).value == "Task"
        assert messages == [f"Can't save the task in {tmp_path}: Permission denied"]


# Task files changed on disk while the form is open

KEPT = (
    "Your changes are kept here, but saving them will be refused so the file "
    "isn't overwritten."
)


@pytest.mark.asyncio
async def test_a_task_changed_on_disk_keeps_the_input_and_shows_the_conflict(
    tmp_path: Path,
) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)
    path = tmp_path / "AAAA.md"

    app = TskmngrApp(tmp_path, poll_interval=0)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("e")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        fill(screen, title="Mine")

        path.write_text(path.read_text(encoding="utf-8").replace("First", "Theirs"))
        assert app.check_tasks_dir()
        await pilot.pause()

        assert app.screen is screen
        assert screen.query_one("#title", Input).value == "Mine"
        assert messages == [f"AAAA.md changed on disk since it was loaded. {KEPT}"]

        # Shown once, however often the file changes after that.
        hand_edited = path.read_text(encoding="utf-8").replace("Theirs", "Again")
        path.write_text(hand_edited, encoding="utf-8")
        assert app.check_tasks_dir()
        await pilot.pause()
        assert len(messages) == 1

        # Saving runs into the conflict and leaves the file alone.
        await pilot.press("ctrl+s")

        assert path.read_text(encoding="utf-8") == hand_edited
        assert messages[1] == (
            "AAAA.md changed on disk since it was loaded. It was reloaded "
            "from disk; your changes weren't saved."
        )
        assert isinstance(app.screen, TaskListScreen)
        assert app.screen.tasks[0].task.title == "Again"


@pytest.mark.asyncio
async def test_a_task_deleted_on_disk_shows_the_conflict(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)

    app = TskmngrApp(tmp_path, poll_interval=0)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("e")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        fill(screen, title="Mine")

        (tmp_path / "AAAA.md").unlink()
        assert app.check_tasks_dir()
        await pilot.pause()

        assert app.screen is screen
        assert screen.query_one("#title", Input).value == "Mine"
        assert messages == [f"AAAA.md deleted on disk since it was loaded. {KEPT}"]


@pytest.mark.asyncio
async def test_other_files_changing_on_disk_leave_the_form_alone(
    tmp_path: Path,
) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)

    app = TskmngrApp(tmp_path, poll_interval=0)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("e")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        fill(screen, title="Mine")

        save_task(tmp_path, make_task("BBBB", "Second"), None)
        assert app.check_tasks_dir()
        await pilot.pause()
        assert messages == []

        await pilot.press("ctrl+s")

        assert messages == []
        assert loaded(tmp_path)["AAAA"].title == "Mine"


@pytest.mark.asyncio
async def test_a_new_task_form_ignores_changes_on_disk(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path, poll_interval=0)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("n")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        fill(screen, title="New")

        save_task(tmp_path, make_task("AAAA", "First"), None)
        assert app.check_tasks_dir()
        await pilot.pause()
        assert messages == []

        await pilot.press("ctrl+s")

        assert sorted(task.title for task in loaded(tmp_path).values()) == [
            "First",
            "New",
        ]


@pytest.mark.asyncio
async def test_a_file_that_cant_be_checked_shows_nothing_yet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(directory: Path, source: object) -> None:
        raise PermissionError(13, "Permission denied")

    save_task(tmp_path, make_task("AAAA", "First"), None)

    app = TskmngrApp(tmp_path, poll_interval=0)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("e")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        monkeypatch.setattr(task_form, "check_unchanged", fail)

        save_task(tmp_path, make_task("BBBB", "Second"), None)
        assert app.check_tasks_dir()
        await pilot.pause()

        assert app.screen is screen
        assert messages == []


# Repeat rules


@pytest.mark.asyncio
async def test_the_form_shows_the_repeat_rule_in_its_shortest_form(
    tmp_path: Path,
) -> None:
    (tmp_path / "AAAA.md").write_text(
        "---\ntitle: Water plants\nrepeat: Every 2  Weeks\n---\n", encoding="utf-8"
    )

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("e")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)

        assert screen.query_one("#repeat", Input).value == "every 2 weeks"
        # Unchanged, so saving leaves the file as written.
        await pilot.press("ctrl+s")

    assert "repeat: Every 2  Weeks\n" in (tmp_path / "AAAA.md").read_text()


@pytest.mark.asyncio
async def test_a_new_task_form_has_an_empty_repeat_field(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("n")

        assert app.screen.query_one("#repeat", Input).value == ""


@pytest.mark.asyncio
async def test_setting_a_repeat_rule_saves_it(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "Water plants"), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("e")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        fill(screen, repeat="  Every 3 days ")
        await pilot.press("ctrl+s")

        assert isinstance(app.screen, TaskListScreen)
    task = loaded(tmp_path)["AAAA"]
    assert task.repeat == Repeat(3, Unit.DAYS)
    assert task.updated > CREATED


@pytest.mark.asyncio
async def test_an_invalid_repeat_rule_is_shown_and_nothing_is_saved(
    tmp_path: Path,
) -> None:
    save_task(tmp_path, make_task("AAAA", "Water plants"), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("e")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        fill(screen, repeat="fortnightly")
        await pilot.press("ctrl+s")

        assert app.screen is screen
        assert error_text(screen, "repeat") == (
            "Expected daily, weekly, monthly, yearly or every N days, weeks, months "
            "or years, got 'fortnightly'"
        )
        assert screen.focused is screen.query_one("#repeat")
    assert loaded(tmp_path)["AAAA"].repeat is None


@pytest.mark.asyncio
async def test_clearing_the_rule_removes_repeat_and_repeat_from(tmp_path: Path) -> None:
    task = make_task(
        "AAAA",
        "Pay rent",
        repeat=Repeat(1, Unit.MONTHS),
        repeat_from=date(2026, 1, 31),
    )
    save_task(tmp_path, task, None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("e")
        fill(app.screen, repeat="")
        await pilot.press("ctrl+s")

    assert "repeat" not in (tmp_path / "AAAA.md").read_text()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rule", "repeat_from"),
    [("Monthly", date(2026, 1, 31)), ("every 2 months", None)],
)
async def test_repeat_from_is_kept_only_with_the_same_rule(
    tmp_path: Path, rule: str, repeat_from: date | None
) -> None:
    task = make_task(
        "AAAA",
        "Pay rent",
        repeat=Repeat(1, Unit.MONTHS),
        repeat_from=date(2026, 1, 31),
    )
    save_task(tmp_path, task, None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("e")
        fill(app.screen, repeat=rule, title="Pay the rent")
        await pilot.press("ctrl+s")

    assert loaded(tmp_path)["AAAA"].repeat_from == repeat_from


@pytest.mark.asyncio
async def test_changing_only_the_rule_asks_before_discarding(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "Water plants"), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("e")
        fill(app.screen, repeat="weekly")
        await pilot.press("escape")

        assert isinstance(app.screen, ConfirmDiscardScreen)


@pytest.mark.asyncio
async def test_saving_a_repeating_task_as_done_adds_the_next_occurrence(
    tmp_path: Path,
) -> None:
    task = make_task(
        "AAAA", "Water plants", due=date(2099, 3, 1), repeat=Repeat(1, Unit.WEEKS)
    )
    save_task(tmp_path, task, None)

    app = TskmngrApp(tmp_path)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("e")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        screen.query_one("#status", Select).value = Status.DONE
        fill(screen, title="Water all plants")
        await pilot.press("ctrl+s")

        assert isinstance(app.screen, TaskListScreen)
        tasks = loaded(tmp_path)
        done = tasks.pop("AAAA")
        [following] = tasks.values()
        assert done.status is Status.DONE
        assert done.repeat is None
        assert following.title == "Water all plants"
        assert following.due == date(2099, 3, 8)
        assert messages == [f"Next occurrence: {following.id}, due 2099-03-08"]
        assert cursor_task_id(app) == "AAAA"


@pytest.mark.asyncio
async def test_a_new_task_saved_as_done_with_a_rule_adds_the_next_occurrence(
    tmp_path: Path,
) -> None:
    app = TskmngrApp(tmp_path)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("n")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        fill(screen, title="Water plants", due="2099-03-01", repeat="weekly")
        screen.query_one("#status", Select).value = Status.DONE
        await pilot.press("ctrl+s")

        tasks = loaded(tmp_path)
        assert len(tasks) == 2
        done = next(t for t in tasks.values() if t.status is Status.DONE)
        following = next(t for t in tasks.values() if t.status is Status.TODO)
        assert done.repeat is None
        assert done.due == date(2099, 3, 1)
        assert following.repeat == Repeat(1, Unit.WEEKS)
        assert following.due == date(2099, 3, 8)
        assert messages == [f"Next occurrence: {following.id}, due 2099-03-08"]


@pytest.mark.asyncio
async def test_saving_a_done_repeating_task_again_adds_nothing(tmp_path: Path) -> None:
    task = make_task(
        "AAAA", "Water plants", status=Status.DONE, repeat=Repeat(1, Unit.WEEKS)
    )
    save_task(tmp_path, task, None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("e")
        fill(app.screen, title="Water all plants")
        await pilot.press("ctrl+s")

    assert list(loaded(tmp_path)) == ["AAAA"]


@pytest.mark.asyncio
async def test_a_next_due_date_that_cant_be_computed_keeps_the_form_open(
    tmp_path: Path,
) -> None:
    task = make_task(
        "AAAA", "Water plants", due=date(9999, 12, 1), repeat=Repeat(1, Unit.MONTHS)
    )
    save_task(tmp_path, task, None)

    app = TskmngrApp(tmp_path)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("e")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        screen.query_one("#status", Select).value = Status.DONE
        await pilot.press("ctrl+s")

        assert app.screen is screen
        assert messages == [
            (
                "Can't add the next occurrence: the next occurrence of monthly "
                "would be after the year 9999"
            )
        ]
    assert loaded(tmp_path) == {"AAAA": task}


@pytest.mark.asyncio
async def test_the_new_task_form_suggests_existing_tags(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "First", tags=("errands", "home")), None)
    save_task(tmp_path, make_task("BBBB", "Second", tags=("work",)), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("n", *"Task")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        tags = screen.query_one("#tags", Input)
        tags.focus()
        await pilot.press("E")
        await pilot.pause()
        await pilot.press("right")
        assert tags.value == "Errands"

        await pilot.press(*", w")
        await pilot.pause()
        await pilot.press("right")
        assert tags.value == "Errands, work"

        await pilot.press("ctrl+s")

        assert isinstance(app.screen, TaskListScreen)
        (new,) = (t for t in loaded(tmp_path).values() if t.title == "Task")
        assert new.tags == ("errands", "work")


@pytest.mark.asyncio
async def test_right_without_a_suggestion_only_moves_the_cursor(
    tmp_path: Path,
) -> None:
    save_task(tmp_path, make_task("AAAA", "First", tags=("home",)), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("n")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        tags = screen.query_one("#tags", Input)
        tags.focus()
        await pilot.press(*"home")
        await pilot.pause()
        await pilot.press("right")
        assert tags.value == "home"

        await pilot.press(*" x")
        await pilot.pause()
        await pilot.press("right")
        assert tags.value == "home x"


@pytest.mark.asyncio
async def test_the_edit_form_suggests_tags_from_the_list_and_the_detail_view(
    tmp_path: Path,
) -> None:
    save_task(tmp_path, make_task("AAAA", "First", tags=("home",)), None)
    save_task(tmp_path, make_task("BBBB", "Second", tags=("work",)), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        for keys in (("e",), ("enter", "e")):
            await pilot.press(*keys)
            screen = app.screen
            assert isinstance(screen, TaskFormScreen)
            tags = screen.query_one("#tags", Input)
            assert tags.value == "home"
            tags.focus()
            await pilot.press("end", *" w")
            await pilot.pause()
            await pilot.press("right")
            assert tags.value == "home work"
            await pilot.press("escape", "y")
            if keys[0] == "enter":
                await pilot.press("escape")
            assert isinstance(app.screen, TaskListScreen)


@pytest.mark.asyncio
async def test_unreadable_tasks_leave_nothing_to_suggest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_task(tmp_path, make_task("AAAA", "First", tags=("home",)), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:

        def fail(directory: Path) -> object:
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(task_form, "load_tasks", fail)
        await pilot.press("n")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        tags = screen.query_one("#tags", Input)
        tags.focus()
        await pilot.press("h")
        await pilot.pause()
        await pilot.press("right")
        assert tags.value == "h"
