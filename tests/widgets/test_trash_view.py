from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from rich.text import Text
from textual.widgets import DataTable, Static

from tskmngr.app import TskmngrApp
from tskmngr.config import Config
from tskmngr.display import TrashColumn
from tskmngr.models import Priority, Repeat, Status, Task, Unit
from tskmngr.storage import BadFile, DeletedTask, delete_task, load_tasks, save_task
from tskmngr.taskfile import MalformedTaskError
from tskmngr.widgets.task_list import TaskListScreen
from tskmngr.widgets.trash_view import (
    TrashTable,
    TrashView,
    bad_trash_warning,
    trash_labels,
    trash_row,
)

CREATED = datetime(2026, 10, 28, 9, 15, tzinfo=UTC)
DELETED = datetime(2026, 10, 30, 12, 0, 5, tzinfo=UTC)


def make_task(task_id: str, title: str, **fields: object) -> Task:
    return Task(id=task_id, title=title, created=CREATED, updated=CREATED, **fields)


def delete(directory: Path, task: Task, when: datetime) -> Path:
    """Save `task`, then delete it at `when`; returns its file in `.trash/`."""
    save_task(directory, task, None)
    [source] = [s for s in load_tasks(directory).tasks if s.task.id == task.id]
    return delete_task(directory, source, now=when)


def trash_view(app: TskmngrApp) -> TrashView:
    return app.screen.query_one(TrashView)


def trash_rows(app: TskmngrApp) -> list[list[str]]:
    table = trash_view(app).query_one("#trash-table", DataTable)
    return [
        [cell.plain for cell in table.get_row_at(i)] for i in range(table.row_count)
    ]


def trash_headers(app: TskmngrApp) -> list[str]:
    table = trash_view(app).query_one("#trash-table", DataTable)
    return [column.label.plain for column in table.columns.values()]


def shown_text(app: TskmngrApp, selector: str) -> str | None:
    """The text of a Static in the view, or None while it's hidden."""
    static = trash_view(app).query_one(selector, Static)
    if not static.has_class("-shown"):
        return None
    content = static.content
    return content.plain if isinstance(content, Text) else str(content)


# Cells and headers


def test_default_columns_are_title_deleted_and_id() -> None:
    assert trash_labels() == ("Title", "Deleted", "ID")


def test_trash_row_has_the_title_with_markers_the_delete_time_and_the_id() -> None:
    task = make_task(
        "AAAA",
        "Water plants",
        tags=("home",),
        repeat=Repeat(1, Unit.WEEKS),
        notes="- [x] Kitchen\n- [ ] Hall\n",
    )
    entry = DeletedTask(Path("AAAA.x.md"), task, DELETED)

    assert [cell.plain for cell in trash_row(entry)] == [
        "Water plants ↻ [1/2] #home",
        "2026-10-30T12:00:05Z",
        "AAAA",
    ]


def test_trash_row_follows_the_columns() -> None:
    task = make_task(
        "AAAA",
        "Read",
        status=Status.DOING,
        priority=Priority.HIGH,
        due=date(2026, 11, 1),
    )
    entry = DeletedTask(Path("AAAA.x.md"), task, DELETED)
    columns = (
        TrashColumn.DELETED,
        TrashColumn.STATUS,
        TrashColumn.PRIORITY,
        TrashColumn.DUE,
        TrashColumn.CREATED,
        TrashColumn.UPDATED,
    )

    assert trash_labels(columns) == (
        "Deleted",
        "Status",
        "Priority",
        "Due",
        "Created",
        "Updated",
    )
    assert [cell.plain for cell in trash_row(entry, columns)] == [
        "2026-10-30T12:00:05Z",
        "doing",
        "high",
        "2026-11-01",
        "2026-10-28T09:15:00Z",
        "2026-10-28T09:15:00Z",
    ]


def test_bad_trash_warning_names_files_from_the_tasks_directory(
    tmp_path: Path,
) -> None:
    bad = [
        BadFile(tmp_path / ".trash" / "junk.md", MalformedTaskError("bad name")),
        BadFile(Path("/elsewhere/b.md"), MalformedTaskError("missing", field="title")),
    ]

    assert bad_trash_warning(tmp_path, bad).plain == (
        "2 files in .trash/ couldn't be loaded:\n"
        "  .trash/junk.md: bad name\n"
        "  /elsewhere/b.md: title: missing"
    )
    assert bad_trash_warning(tmp_path, bad[:1]).plain.startswith(
        "1 file in .trash/ couldn't be loaded:"
    )


# The view in the task list screen


@pytest.mark.asyncio
async def test_the_view_lists_deleted_tasks_newest_first(tmp_path: Path) -> None:
    delete(tmp_path, make_task("AAAA", "Old idea"), DELETED)
    delete(tmp_path, make_task("BBBB", "Draft"), datetime(2026, 11, 2, tzinfo=UTC))
    save_task(tmp_path, make_task("CCCC", "Kept"), None)

    app = TskmngrApp(tmp_path, poll_interval=0)
    async with app.run_test():
        assert trash_view(app).border_title == "Deleted tasks"
        assert trash_headers(app) == ["Title", "Deleted", "ID"]
        assert trash_rows(app) == [
            ["Draft", "2026-11-02T00:00:00Z", "BBBB"],
            ["Old idea", "2026-10-30T12:00:05Z", "AAAA"],
        ]
        assert shown_text(app, "#no-deleted-tasks") is None
        assert shown_text(app, "#trash-warning") is None
        # The deleted tasks aren't in the task list.
        assert [source.task.id for source in app.screen.tasks] == ["CCCC"]


@pytest.mark.asyncio
async def test_an_empty_trash_says_so(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path / "missing", poll_interval=0)
    async with app.run_test():
        assert trash_rows(app) == []
        assert shown_text(app, "#no-deleted-tasks") == "No deleted tasks."


@pytest.mark.asyncio
async def test_files_in_the_trash_that_cant_be_loaded_are_named(
    tmp_path: Path,
) -> None:
    delete(tmp_path, make_task("AAAA", "Old idea"), DELETED)
    (tmp_path / ".trash" / "junk.md").write_text("---\ntitle: x\n---\n")

    app = TskmngrApp(tmp_path, poll_interval=0)
    async with app.run_test():
        assert shown_text(app, "#trash-warning") == (
            "1 file in .trash/ couldn't be loaded:\n"
            "  .trash/junk.md: name isn't <id>.<delete time>.md"
        )
        assert [row[2] for row in trash_rows(app)] == ["AAAA"]


@pytest.mark.asyncio
async def test_a_trash_that_cant_be_read_is_shown_as_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(directory: Path) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr("tskmngr.widgets.trash_view.load_trash", fail)

    app = TskmngrApp(tmp_path, poll_interval=0)
    async with app.run_test():
        assert shown_text(app, "#trash-warning") == (
            f"Can't read the deleted tasks in {tmp_path / '.trash'}: Permission denied"
        )
        assert shown_text(app, "#no-deleted-tasks") is None


@pytest.mark.asyncio
async def test_the_view_takes_the_bottom_quarter_of_the_screen(
    tmp_path: Path,
) -> None:
    app = TskmngrApp(tmp_path, poll_interval=0)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        view = trash_view(app).region
        table = app.screen.query_one("#task-table", DataTable).region
        footer = app.screen.query_one("Footer").region

        assert view.height == 10
        assert view.bottom == footer.y
        assert table.bottom <= view.y


@pytest.mark.asyncio
async def test_t_hides_and_shows_the_view_and_the_list_takes_its_place(
    tmp_path: Path,
) -> None:
    app = TskmngrApp(tmp_path, poll_interval=0)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, TaskListScreen)
        table = screen.query_one("#task-table", DataTable)
        with_view = table.region.height
        assert screen.show_trash
        assert trash_view(app).display

        await pilot.press("t")
        await pilot.pause()
        assert not screen.show_trash
        assert not trash_view(app).display
        assert table.region.height > with_view

        await pilot.press("t")
        await pilot.pause()
        assert screen.show_trash
        assert trash_view(app).display
        assert table.region.height == with_view


@pytest.mark.asyncio
async def test_the_view_can_start_hidden(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path, poll_interval=0)
    async with app.run_test() as pilot:
        await app.push_screen(TaskListScreen(tmp_path, show_trash=False))
        await pilot.pause()

        assert not trash_view(app).display


@pytest.mark.asyncio
async def test_the_columns_come_from_the_config(tmp_path: Path) -> None:
    delete(tmp_path, make_task("AAAA", "Old idea", priority=Priority.HIGH), DELETED)
    config = Config(
        trash_columns=(TrashColumn.ID, TrashColumn.PRIORITY, TrashColumn.DELETED)
    )

    app = TskmngrApp(tmp_path, config=config, poll_interval=0)
    async with app.run_test():
        assert trash_headers(app) == ["ID", "Priority", "Deleted"]
        assert trash_rows(app) == [["AAAA", "high", "2026-10-30T12:00:05Z"]]


@pytest.mark.asyncio
async def test_the_config_can_start_the_view_hidden(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path, config=Config(show_trash=False), poll_interval=0)
    async with app.run_test() as pilot:
        assert not trash_view(app).display

        await pilot.press("t")
        await pilot.pause()

        assert trash_view(app).display


@pytest.mark.asyncio
async def test_t_is_typed_into_the_filter_bar(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path, poll_interval=0)
    async with app.run_test() as pilot:
        await pilot.press("slash", "t")

        assert app.screen.query_one("#filter-input").value == "t"
        assert trash_view(app).display


@pytest.mark.asyncio
async def test_the_view_never_takes_focus_so_keys_act_on_the_list(
    tmp_path: Path,
) -> None:
    save_task(tmp_path, make_task("AAAA", "Kept"), None)
    delete(tmp_path, make_task("BBBB", "Old idea"), DELETED)

    app = TskmngrApp(tmp_path, poll_interval=0)
    async with app.run_test() as pilot:
        table = trash_view(app).query_one(TrashTable)
        assert not table.can_focus
        await pilot.press("tab", "tab", "tab")
        assert app.focused is not table

        await pilot.press("s")
        assert load_tasks(tmp_path).tasks[0].task.status is Status.DOING


@pytest.mark.asyncio
async def test_deleting_from_the_list_adds_the_task_to_the_view(
    tmp_path: Path,
) -> None:
    save_task(tmp_path, make_task("AAAA", "Buy milk"), None)

    app = TskmngrApp(tmp_path, poll_interval=0)
    async with app.run_test() as pilot:
        assert trash_rows(app) == []

        await pilot.press("d", "y")
        await pilot.pause()

        assert [row[0] for row in trash_rows(app)] == ["Buy milk"]
        assert [row[2] for row in trash_rows(app)] == ["AAAA"]


@pytest.mark.asyncio
async def test_files_changed_in_the_trash_on_disk_are_reloaded(
    tmp_path: Path,
) -> None:
    trashed = delete(tmp_path, make_task("AAAA", "Old idea"), DELETED)

    app = TskmngrApp(tmp_path, poll_interval=0)
    async with app.run_test() as pilot:
        assert len(trash_rows(app)) == 1

        # Moved there by hand, not through the app: only `.trash/` changes.
        (tmp_path / ".trash" / "BBBB.2026-11-01T08-00-00Z.md").write_text(
            "---\ntitle: Moved\n---\n"
        )
        assert app.check_tasks_dir()
        await pilot.pause()
        assert [row[0] for row in trash_rows(app)] == ["Moved", "Old idea"]

        # Restoring by hand moves it out again.
        trashed.rename(tmp_path / "AAAA.md")
        assert app.check_tasks_dir()
        await pilot.pause()
        assert [row[0] for row in trash_rows(app)] == ["Moved"]
        assert [source.task.id for source in app.screen.tasks] == ["AAAA"]
