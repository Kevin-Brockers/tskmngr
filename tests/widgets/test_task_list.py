from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from rich.text import Text
from textual.widgets import Button, DataTable, Static

from tskmngr.app import TskmngrApp
from tskmngr.models import Priority, Status, Task
from tskmngr.storage import BadFile, load_tasks, save_task
from tskmngr.taskfile import MalformedTaskError
from tskmngr.widgets import task_list
from tskmngr.widgets.confirm_delete import ConfirmDeleteScreen, delete_question
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


# Quick status change and delete (M3.4)


def record_notifications(app: TskmngrApp) -> list[str]:
    """Collect the messages of the app's notifications."""
    messages: list[str] = []

    def notify(message: str, **_: object) -> None:
        messages.append(message)

    app.notify = notify  # type: ignore[method-assign]
    return messages


def loaded(directory: Path) -> dict[str, Task]:
    return {source.task.id: source.task for source in load_tasks(directory).tasks}


def cursor_task_id(app: TskmngrApp) -> str:
    screen = app.screen
    assert isinstance(screen, TaskListScreen)
    table = screen.query_one("#task-table", DataTable)
    return screen.tasks[table.cursor_row].task.id


def trashed(directory: Path) -> list[str]:
    trash = directory / ".trash"
    return sorted(path.name for path in trash.iterdir()) if trash.is_dir() else []


@pytest.mark.asyncio
async def test_s_cycles_the_status_and_saves_it(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)
    save_task(tmp_path, make_task("BBBB", "Second"), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("down", "s")
        task = loaded(tmp_path)["BBBB"]
        assert task.status == Status.DOING
        assert task.updated > CREATED
        assert table_rows(app.screen)[1][1] == "doing"
        assert cursor_task_id(app) == "BBBB"

        await pilot.press("s")
        assert loaded(tmp_path)["BBBB"].status == Status.DONE

        await pilot.press("s")
        assert loaded(tmp_path)["BBBB"].status == Status.TODO
        # The other task is untouched.
        assert loaded(tmp_path)["AAAA"] == make_task("AAAA", "First")


@pytest.mark.asyncio
async def test_s_keeps_the_cursor_on_the_task_when_it_moves(tmp_path: Path) -> None:
    # Statuses don't change the order, but a task saved meanwhile might.
    save_task(tmp_path, make_task("AAAA", "First", due=date(2026, 11, 2)), None)
    save_task(tmp_path, make_task("BBBB", "Second", due=date(2026, 11, 3)), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        save_task(tmp_path, make_task("CCCC", "Sooner", due=date(2026, 11, 1)), None)
        await pilot.press("down", "s")

        assert [row[0] for row in table_rows(app.screen)] == ["CCCC", "AAAA", "BBBB"]
        assert cursor_task_id(app) == "BBBB"


@pytest.mark.asyncio
async def test_s_keeps_notes_and_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "AAAA.md"
    path.write_text(
        "---\n"
        "title: First\n"
        "status: todo   # keep me\n"
        "custom: value\n"
        "created: 2026-10-28T09:15:00Z\n"
        "updated: 2026-10-28T09:15:00Z\n"
        "---\n"
        "\n"
        "Some notes.\n",
        encoding="utf-8",
    )

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("s")

    text = path.read_text(encoding="utf-8")
    # The comment stays in its column.
    assert "status: doing  # keep me\n" in text
    assert "custom: value\n" in text
    assert text.endswith("---\n\nSome notes.\n")


@pytest.mark.asyncio
async def test_s_and_d_do_nothing_without_tasks(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("s", "d")

        assert isinstance(app.screen, TaskListScreen)
        assert messages == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_s_conflict_is_shown_and_the_task_reloaded_not_overwritten(
    tmp_path: Path,
) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)

    app = TskmngrApp(tmp_path)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        path = tmp_path / "AAAA.md"
        hand_edited = path.read_text(encoding="utf-8").replace("First", "Theirs")
        path.write_text(hand_edited, encoding="utf-8")
        await pilot.press("s")

        assert path.read_text(encoding="utf-8") == hand_edited
        assert messages == [
            (
                "AAAA.md changed on disk since it was loaded. It was reloaded from "
                "disk; the status wasn't changed."
            )
        ]
        assert table_rows(app.screen)[0][1:] == ["todo", "normal", "", "Theirs"]


@pytest.mark.asyncio
async def test_s_on_a_task_deleted_meanwhile_reloads_without_it(
    tmp_path: Path,
) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)
    save_task(tmp_path, make_task("BBBB", "Second"), None)

    app = TskmngrApp(tmp_path)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        (tmp_path / "AAAA.md").unlink()
        await pilot.press("s")

        assert not (tmp_path / "AAAA.md").exists()
        assert messages == [
            (
                "AAAA.md deleted on disk since it was loaded. It was reloaded from "
                "disk; the status wasn't changed."
            )
        ]
        assert [row[0] for row in table_rows(app.screen)] == ["BBBB"]


@pytest.mark.asyncio
async def test_s_write_error_is_shown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)

    def fail(*_: object) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(task_list, "save_task", fail)

    app = TskmngrApp(tmp_path)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("s")

        assert messages == [f"Can't save the task in {tmp_path}: Permission denied"]
        assert table_rows(app.screen)[0][1] == "todo"
    assert loaded(tmp_path)["AAAA"].status == Status.TODO


def test_delete_question_names_the_task_as_written() -> None:
    task = make_task("AAAA", "[b]Not bold[/b]")

    assert delete_question(task).plain == (
        "Delete task AAAA '[b]Not bold[/b]'?\n"
        "Its file is moved to .trash/ in the tasks directory."
    )


def test_confirm_delete_bindings_have_stable_ids() -> None:
    ids = {binding.id for binding in ConfirmDeleteScreen.BINDINGS}

    assert ids == {"confirm_delete.yes", "confirm_delete.no"}


@pytest.mark.asyncio
async def test_d_asks_about_the_task_under_the_cursor_with_no_focused(
    tmp_path: Path,
) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)
    save_task(tmp_path, make_task("BBBB", "Second"), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("down", "d")

        screen = app.screen
        assert isinstance(screen, ConfirmDeleteScreen)
        assert screen.task_to_delete.id == "BBBB"
        assert app.focused is screen.query_one("#no", Button)


@pytest.mark.asyncio
@pytest.mark.parametrize("keys", [("n",), ("escape",), ("enter",)])
async def test_answering_no_deletes_nothing(
    tmp_path: Path, keys: tuple[str, ...]
) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)

    app = TskmngrApp(tmp_path)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("d", *keys)

        assert isinstance(app.screen, TaskListScreen)
        assert messages == []
        assert [row[0] for row in table_rows(app.screen)] == ["AAAA"]
    assert (tmp_path / "AAAA.md").exists()
    assert trashed(tmp_path) == []


@pytest.mark.asyncio
async def test_y_moves_the_file_to_trash_and_selects_the_next_task(
    tmp_path: Path,
) -> None:
    for task_id, day in (("AAAA", 1), ("BBBB", 2), ("CCCC", 3)):
        save_task(tmp_path, make_task(task_id, task_id, due=date(2026, 11, day)), None)

    app = TskmngrApp(tmp_path)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("down", "d", "y")

        assert isinstance(app.screen, TaskListScreen)
        assert [row[0] for row in table_rows(app.screen)] == ["AAAA", "CCCC"]
        assert cursor_task_id(app) == "CCCC"
        [name] = trashed(tmp_path)
        assert name.startswith("BBBB.") and name.endswith("Z.md")
        assert messages == [f"Moved BBBB to .trash/{name}"]
    assert not (tmp_path / "BBBB.md").exists()


@pytest.mark.asyncio
async def test_deleting_the_last_row_selects_the_one_before(tmp_path: Path) -> None:
    for task_id, day in (("AAAA", 1), ("BBBB", 2), ("CCCC", 3)):
        save_task(tmp_path, make_task(task_id, task_id, due=date(2026, 11, day)), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("down", "down", "d", "y")

        assert [row[0] for row in table_rows(app.screen)] == ["AAAA", "BBBB"]
        assert cursor_task_id(app) == "BBBB"


@pytest.mark.asyncio
async def test_deleting_the_only_task_shows_no_tasks(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("d", "y")

        assert table_rows(app.screen) == []
        assert app.screen.query_one("#no-tasks").has_class("-shown")


@pytest.mark.asyncio
async def test_clicking_yes_deletes(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("d")
        await pilot.click("#yes")

        assert isinstance(app.screen, TaskListScreen)
        assert table_rows(app.screen) == []
    assert len(trashed(tmp_path)) == 1


@pytest.mark.asyncio
async def test_delete_conflict_is_shown_and_nothing_deleted(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)

    app = TskmngrApp(tmp_path)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("d")
        path = tmp_path / "AAAA.md"
        hand_edited = path.read_text(encoding="utf-8").replace("First", "Theirs")
        path.write_text(hand_edited, encoding="utf-8")
        await pilot.press("y")

        assert path.read_text(encoding="utf-8") == hand_edited
        assert trashed(tmp_path) == []
        assert messages == [
            (
                "AAAA.md changed on disk since it was loaded. It was reloaded from "
                "disk; nothing was deleted."
            )
        ]
        assert table_rows(app.screen)[0][4] == "Theirs"


@pytest.mark.asyncio
async def test_delete_error_is_shown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)

    def fail(*_: object, **__: object) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(task_list, "delete_task", fail)

    app = TskmngrApp(tmp_path)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("d", "y")

        assert messages == [f"Can't delete the task in {tmp_path}: Permission denied"]
        assert [row[0] for row in table_rows(app.screen)] == ["AAAA"]
    assert (tmp_path / "AAAA.md").exists()
