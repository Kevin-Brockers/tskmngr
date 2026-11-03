from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from rich.console import Console
from textual.widgets import DataTable, Input, Markdown

from tskmngr.app import TskmngrApp
from tskmngr.models import Task
from tskmngr.storage import save_task
from tskmngr.taskfile import TaskFile, render
from tskmngr.widgets.task_detail import TaskDetailScreen, fields_table
from tskmngr.widgets.task_form import TaskFormScreen
from tskmngr.widgets.task_list import TaskListScreen

CREATED = datetime(2026, 10, 28, 9, 15, tzinfo=UTC)


def make_task(task_id: str, title: str, **fields: object) -> Task:
    return Task(id=task_id, title=title, created=CREATED, updated=CREATED, **fields)


def rendered(renderable: object) -> str:
    console = Console(width=80, record=True)
    console.print(renderable)
    return console.export_text()


def test_fields_table_shows_titles_as_written_not_as_markup() -> None:
    text = rendered(fields_table(make_task("A", "[bold]Not bold[/bold]")))

    assert "[bold]Not bold[/bold]" in text


@pytest.mark.asyncio
async def test_enter_opens_the_task_under_the_cursor(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "First", due=date(2026, 11, 2)), None)
    save_task(tmp_path, make_task("BBBB", "Second", due=date(2026, 11, 3)), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("down", "enter")

        screen = app.screen
        assert isinstance(screen, TaskDetailScreen)
        assert screen.source.task.id == "BBBB"
        assert screen.sub_title == str(tmp_path / "BBBB.md")
        assert "Second" in rendered(screen.query_one("#fields").content)


@pytest.mark.asyncio
async def test_clicking_the_highlighted_row_opens_its_task(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "First", due=date(2026, 11, 2)), None)
    save_task(tmp_path, make_task("BBBB", "Second", due=date(2026, 11, 3)), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        # Line 0 is the column header, so y=2 is the second task. Like any
        # DataTable, the first click moves the cursor, the second selects.
        await pilot.click("#task-table", offset=(2, 2))
        assert isinstance(app.screen, TaskListScreen)

        await pilot.click("#task-table", offset=(2, 2))

        assert isinstance(app.screen, TaskDetailScreen)
        assert app.screen.source.task.id == "BBBB"


@pytest.mark.asyncio
async def test_enter_does_nothing_without_tasks(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("enter")

        assert isinstance(app.screen, TaskListScreen)


@pytest.mark.asyncio
async def test_escape_goes_back_to_the_list(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)
    save_task(tmp_path, make_task("BBBB", "Second"), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("down", "enter")
        assert isinstance(app.screen, TaskDetailScreen)

        await pilot.press("escape")

        assert isinstance(app.screen, TaskListScreen)
        # The cursor stays on the task that was open.
        assert app.screen.query_one("#task-table", DataTable).cursor_row == 1


@pytest.mark.asyncio
async def test_notes_are_rendered_as_markdown(tmp_path: Path) -> None:
    task = make_task("AAAA", "Read", notes="# Heading\n\nSome **bold** text.\n")

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await app.push_screen(TaskDetailScreen(tmp_path, TaskFile(task, render(task))))
        await pilot.pause()

        notes = app.screen.query_one("#notes", Markdown)
        assert notes.display
        assert notes.source == "# Heading\n\nSome **bold** text.\n"
        assert len(notes.children) == 2  # the heading and the paragraph
        assert not app.screen.query_one("#no-notes").display


@pytest.mark.asyncio
async def test_a_task_without_notes_says_so(tmp_path: Path) -> None:
    task = make_task("AAAA", "Read", notes="\n  \n")

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await app.push_screen(TaskDetailScreen(tmp_path, TaskFile(task, render(task))))
        await pilot.pause()

        assert not app.screen.query_one("#notes").display
        assert app.screen.query_one("#no-notes").display


def test_bindings_have_stable_ids() -> None:
    list_ids = {binding.id for binding in TaskListScreen.BINDINGS}
    detail_ids = {binding.id for binding in TaskDetailScreen.BINDINGS}

    assert list_ids == {
        "task_list.open",
        "task_list.new",
        "task_list.edit",
        "task_list.cycle_status",
        "task_list.delete",
        "task_list.external_editor",
        "task_list.sort",
        "task_list.reverse_sort",
        "task_list.filter",
        "task_list.clear_filter",
    }
    assert detail_ids == {
        "task_detail.close",
        "task_detail.edit",
        "task_detail.external_editor",
    }


def record_notifications(app: TskmngrApp) -> list[str]:
    """Collect the messages of the app's notifications."""
    messages: list[str] = []

    def notify(message: str, **_: object) -> None:
        messages.append(message)

    app.notify = notify  # type: ignore[method-assign]
    return messages


def rename_on_disk(directory: Path, task_id: str, old: str, new: str) -> None:
    path = directory / f"{task_id}.md"
    path.write_text(path.read_text(encoding="utf-8").replace(old, new))


@pytest.mark.asyncio
async def test_a_task_changed_on_disk_is_shown_again(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)

    app = TskmngrApp(tmp_path, poll_interval=0)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        screen = app.screen
        assert isinstance(screen, TaskDetailScreen)

        path = tmp_path / "AAAA.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace("First", "Renamed")
            + "\nNew *notes*.\n"
        )
        assert app.check_tasks_dir()
        await pilot.pause()

        assert app.screen is screen
        assert screen.source.task.title == "Renamed"
        assert "Renamed" in rendered(screen.query_one("#fields").content)
        assert screen.query_one("#notes", Markdown).display


@pytest.mark.asyncio
async def test_other_files_changing_on_disk_leave_the_task_as_shown(
    tmp_path: Path,
) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)

    app = TskmngrApp(tmp_path, poll_interval=0)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        screen = app.screen
        assert isinstance(screen, TaskDetailScreen)
        source = screen.source

        save_task(tmp_path, make_task("BBBB", "Second"), None)
        assert app.check_tasks_dir()
        await pilot.pause()

        assert app.screen is screen
        assert screen.source is source


@pytest.mark.asyncio
async def test_a_task_deleted_on_disk_closes_the_detail_screen(
    tmp_path: Path,
) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)
    save_task(tmp_path, make_task("BBBB", "Second"), None)

    app = TskmngrApp(tmp_path, poll_interval=0)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        assert isinstance(app.screen, TaskDetailScreen)

        (tmp_path / "AAAA.md").unlink()
        assert app.check_tasks_dir()
        await pilot.pause()

        assert messages == ["AAAA.md is gone."]
        assert isinstance(app.screen, TaskListScreen)
        assert [source.task.id for source in app.screen.tasks] == ["BBBB"]


@pytest.mark.asyncio
async def test_under_the_form_the_task_is_reloaded_once_back_on_top(
    tmp_path: Path,
) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)

    app = TskmngrApp(tmp_path, poll_interval=0)
    record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        detail = app.screen
        assert isinstance(detail, TaskDetailScreen)
        await pilot.press("e")
        form = app.screen
        assert isinstance(form, TaskFormScreen)

        rename_on_disk(tmp_path, "AAAA", "First", "Theirs")
        assert app.check_tasks_dir()
        await pilot.pause()

        # The form stays, as typed; the detail screen waits underneath.
        assert app.screen is form
        assert form.query_one("#title", Input).value == "First"
        assert detail.source.task.title == "First"

        await pilot.press("escape")

        assert app.screen is detail
        assert detail.source.task.title == "Theirs"
        assert "Theirs" in rendered(detail.query_one("#fields").content)


@pytest.mark.asyncio
async def test_a_task_deleted_under_the_form_closes_the_detail_screen_after(
    tmp_path: Path,
) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)
    save_task(tmp_path, make_task("BBBB", "Second"), None)

    app = TskmngrApp(tmp_path, poll_interval=0)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("enter", "e")
        form = app.screen
        assert isinstance(form, TaskFormScreen)

        (tmp_path / "AAAA.md").unlink()
        assert app.check_tasks_dir()
        await pilot.pause()

        assert app.screen is form
        await pilot.press("escape")

        assert isinstance(app.screen, TaskListScreen)
        assert [source.task.id for source in app.screen.tasks] == ["BBBB"]
        assert messages[-1] == "AAAA.md is gone."
