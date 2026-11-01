from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from rich.text import Text
from textual.widgets import DataTable, Static

from tskmngr.app import TskmngrApp
from tskmngr.models import Priority, Status, Task
from tskmngr.storage import BadFile, save_task
from tskmngr.taskfile import MalformedTaskError
from tskmngr.widgets.task_list import TaskListScreen, bad_files_warning, task_row

CREATED = datetime(2026, 10, 28, 9, 15, tzinfo=UTC)


def make_task(task_id: str, title: str, **fields: object) -> Task:
    return Task(id=task_id, title=title, created=CREATED, updated=CREATED, **fields)


def table_rows(screen: TaskListScreen) -> list[list[str]]:
    table = screen.query_one("#task-table", DataTable)
    return [
        [cell.plain for cell in table.get_row_at(i)] for i in range(table.row_count)
    ]


def warning_text(screen: TaskListScreen) -> str | None:
    """The warning panel's text, or None while it's hidden."""
    warning = screen.query_one("#load-warning", Static)
    if not warning.has_class("-shown"):
        return None
    content = warning.content
    return content.plain if isinstance(content, Text) else str(content)


def test_task_row_has_id_status_priority_due_and_title_with_tags() -> None:
    task = make_task(
        "01JB3K7Q2X",
        "Buy milk",
        status=Status.DOING,
        priority=Priority.HIGH,
        due=date(2026, 11, 1),
        tags=("errands", "shop"),
    )

    assert [cell.plain for cell in task_row(task)] == [
        "01JB3K7Q2X",
        "doing",
        "high",
        "2026-11-01",
        "Buy milk #errands #shop",
    ]


def test_task_row_leaves_due_empty_without_a_due_date() -> None:
    assert task_row(make_task("A", "Read"))[3].plain == ""


def test_bad_files_warning_keeps_full_path_outside_the_directory(
    tmp_path: Path,
) -> None:
    error = MalformedTaskError("missing", field="title")
    inside = BadFile(tmp_path / "tasks" / "IN.md", error)
    outside = BadFile(tmp_path / "elsewhere" / "OUT.md", error)

    assert bad_files_warning(tmp_path / "tasks", [inside, outside]).plain == (
        "2 task files couldn't be loaded:\n"
        "  IN.md: title: missing\n"
        f"  {tmp_path / 'elsewhere' / 'OUT.md'}: title: missing"
    )


@pytest.mark.asyncio
async def test_header_shows_the_tasks_directory(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path)
    async with app.run_test():
        assert app.screen.sub_title == str(tmp_path)


@pytest.mark.asyncio
async def test_lists_all_tasks_done_included_soonest_due_first(
    tmp_path: Path,
) -> None:
    save_task(tmp_path, make_task("AAAA", "No due date"), None)
    save_task(tmp_path, make_task("BBBB", "Later", due=date(2026, 11, 9)), None)
    save_task(
        tmp_path,
        make_task("CCCC", "Soon, done", due=date(2026, 11, 2), status=Status.DONE),
        None,
    )

    app = TskmngrApp(tmp_path)
    async with app.run_test():
        screen = app.screen
        assert [row[0] for row in table_rows(screen)] == ["CCCC", "BBBB", "AAAA"]
        assert [source.task.id for source in screen.tasks] == ["CCCC", "BBBB", "AAAA"]
        assert warning_text(screen) is None
        assert not screen.query_one("#no-tasks").has_class("-shown")


@pytest.mark.asyncio
async def test_rows_are_keyed_by_task_id(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "One"), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test():
        table = app.screen.query_one("#task-table", DataTable)
        assert table.get_row("AAAA")[4].plain == "One"


@pytest.mark.asyncio
async def test_titles_are_shown_as_written_not_as_markup(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "[bold]Not bold[/bold]"), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test():
        assert table_rows(app.screen)[0][4] == "[bold]Not bold[/bold]"


@pytest.mark.asyncio
async def test_empty_directory_shows_no_tasks_message(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path / "missing")
    async with app.run_test():
        screen = app.screen
        assert table_rows(screen) == []
        assert screen.query_one("#no-tasks").has_class("-shown")
        assert warning_text(screen) is None


@pytest.mark.asyncio
async def test_malformed_files_are_named_in_a_warning(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "Fine"), None)
    (tmp_path / "BAD1.md").write_text("---\ntitle: 1.10\n---\n", encoding="utf-8")
    (tmp_path / "BAD2.md").write_text("no frontmatter\n", encoding="utf-8")

    app = TskmngrApp(tmp_path)
    async with app.run_test():
        screen = app.screen
        text = warning_text(screen)
        assert text is not None
        lines = text.splitlines()
        assert lines[0] == "2 task files couldn't be loaded:"
        # Named relative to the tasks directory, which the header shows.
        assert lines[1].startswith("  BAD1.md: line 2: title: ")
        assert "quotes" in lines[1]
        assert lines[2].startswith("  BAD2.md: ")
        # The good task is still listed, and the bad files are left alone.
        assert [row[0] for row in table_rows(screen)] == ["AAAA"]
        assert screen.query_one("#load-warning").display
    assert (tmp_path / "BAD1.md").read_text(encoding="utf-8") == (
        "---\ntitle: 1.10\n---\n"
    )


@pytest.mark.asyncio
async def test_one_malformed_file_is_a_singular_warning(tmp_path: Path) -> None:
    (tmp_path / "BAD1.md").write_text("no frontmatter\n", encoding="utf-8")

    app = TskmngrApp(tmp_path)
    async with app.run_test():
        text = warning_text(app.screen)
        assert text is not None
        assert text.splitlines()[0] == "1 task file couldn't be loaded:"
        assert app.screen.query_one("#no-tasks").has_class("-shown")


@pytest.mark.asyncio
async def test_directory_read_error_is_shown_as_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(directory: Path) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr("tskmngr.widgets.task_list.load_tasks", fail)

    app = TskmngrApp(tmp_path)
    async with app.run_test():
        assert warning_text(app.screen) == (
            f"Can't read the tasks in {tmp_path}: Permission denied"
        )
        assert table_rows(app.screen) == []
        assert app.screen.query_one("#no-tasks").has_class("-shown")


@pytest.mark.asyncio
async def test_load_reloads_from_disk(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        screen = app.screen
        assert table_rows(screen) == []
        save_task(tmp_path, make_task("AAAA", "Added later"), None)
        (tmp_path / "BAD1.md").write_text("no frontmatter\n", encoding="utf-8")

        screen.load()
        await pilot.pause()

        assert [row[0] for row in table_rows(screen)] == ["AAAA"]
        assert not screen.query_one("#no-tasks").has_class("-shown")
        assert warning_text(screen) is not None

        (tmp_path / "BAD1.md").unlink()
        screen.load()
        await pilot.pause()

        assert warning_text(screen) is None
