from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from rich.console import Console
from rich.text import Text
from textual.widgets import DataTable, Input, Select, Static

from tskmngr.app import TskmngrApp
from tskmngr.models import Priority, Status, Task
from tskmngr.storage import load_tasks, save_task
from tskmngr.widgets import task_form
from tskmngr.widgets.task_detail import TaskDetailScreen
from tskmngr.widgets.task_form import TaskFormScreen, format_tags, parse_tags
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
async def test_enter_moves_to_the_next_field_and_saves_from_the_last(
    tmp_path: Path,
) -> None:
    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("n", *"Task", "enter")
        screen = app.screen
        assert isinstance(screen, TaskFormScreen)
        assert screen.query_one("#status", Select).has_focus
        assert loaded(tmp_path) == {}

        screen.query_one("#tags", Input).focus()
        await pilot.press(*"home", "enter")

        assert isinstance(app.screen, TaskListScreen)
        (task,) = loaded(tmp_path).values()
        assert task.tags == ("home",)


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
async def test_escape_cancels_without_saving(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("n", *"Task", "escape")

        assert isinstance(app.screen, TaskListScreen)
        assert loaded(tmp_path) == {}


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

    monkeypatch.setattr(task_form, "save_task", fail)

    app = TskmngrApp(tmp_path)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("n", *"Task", "ctrl+s")

        assert isinstance(app.screen, TaskFormScreen)
        assert app.screen.query_one("#title", Input).value == "Task"
        assert messages == [f"Can't save the task in {tmp_path}: Permission denied"]
