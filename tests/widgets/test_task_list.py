from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from rich.text import Text
from textual.widgets import Button, DataTable, Input, Static

from tskmngr.app import TskmngrApp
from tskmngr.config import Config
from tskmngr.display import Column
from tskmngr.models import Priority, Repeat, Status, Task, Unit
from tskmngr.query import SortKey
from tskmngr.storage import BadFile, load_tasks, save_task
from tskmngr.taskfile import MalformedTaskError
from tskmngr.widgets import saving, task_list
from tskmngr.widgets.confirm_delete import ConfirmDeleteScreen, delete_question
from tskmngr.widgets.task_detail import TaskDetailScreen
from tskmngr.widgets.task_list import (
    TaskListScreen,
    bad_files_warning,
    column_labels,
    shown_columns,
    task_row,
)

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


def test_task_row_shows_subtask_progress_after_the_title() -> None:
    task = make_task(
        "A", "Plan trip", tags=("travel",), notes="- [x] Flights\n- [ ] Pack\n"
    )

    assert task_row(task)[-1].plain == "Plan trip [1/2] #travel"


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

    monkeypatch.setattr(saving, "save_task", fail)

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


# Filter and search (M3.7)


def filter_bar(app: TskmngrApp) -> Input:
    return app.screen.query_one("#filter-input", Input)


def filter_error(app: TskmngrApp) -> str | None:
    """The filter bar's error message, or None while it's hidden."""
    error = app.screen.query_one("#filter-error", Static)
    if not error.has_class("-shown"):
        return None
    content = error.content
    return content.plain if isinstance(content, Text) else str(content)


def shown_ids(app: TskmngrApp) -> list[str]:
    screen = app.screen
    assert isinstance(screen, TaskListScreen)
    return [row[0] for row in table_rows(screen)]


def save_filter_tasks(directory: Path) -> None:
    save_task(
        directory,
        make_task("AAAA", "Buy milk", due=date(2026, 11, 1), tags=("errands",)),
        None,
    )
    save_task(
        directory,
        make_task(
            "BBBB",
            "Pay rent",
            due=date(2026, 11, 2),
            priority=Priority.HIGH,
            notes="Transfer the milk money too.\n",
        ),
        None,
    )
    save_task(
        directory,
        make_task(
            "CCCC",
            "Buy bread",
            due=date(2026, 11, 3),
            status=Status.DONE,
            tags=("errands",),
        ),
        None,
    )


@pytest.mark.asyncio
async def test_filter_bar_is_hidden_until_slash_and_the_table_has_focus(
    tmp_path: Path,
) -> None:
    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        assert not filter_bar(app).display
        assert app.focused is app.screen.query_one("#task-table")

        await pilot.press("slash")

        assert filter_bar(app).display
        assert app.focused is filter_bar(app)


@pytest.mark.asyncio
async def test_the_filter_bar_takes_the_start_of_tags_and_values(
    tmp_path: Path,
) -> None:
    save_filter_tasks(tmp_path)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("slash", *"#err")
        assert shown_ids(app) == ["AAAA", "CCCC"]

        await pilot.press(*" status:d")
        assert shown_ids(app) == ["CCCC"]
        assert filter_error(app) is None

        await pilot.press("ctrl+u", *"priority:hi")
        assert shown_ids(app) == ["BBBB"]


@pytest.mark.asyncio
async def test_the_filter_bar_finds_words_and_tags_with_a_typo(
    tmp_path: Path,
) -> None:
    save_filter_tasks(tmp_path)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        # The title of AAAA and the notes of BBBB.
        await pilot.press("slash", *"mlik")
        assert shown_ids(app) == ["AAAA", "BBBB"]

        await pilot.press(*" #erands")
        assert shown_ids(app) == ["AAAA"]


@pytest.mark.asyncio
async def test_typing_in_the_filter_bar_filters_as_you_type(tmp_path: Path) -> None:
    save_filter_tasks(tmp_path)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("slash", *"milk")
        # The title of AAAA and the notes of BBBB.
        assert shown_ids(app) == ["AAAA", "BBBB"]

        await pilot.press(*" #errands")
        assert shown_ids(app) == ["AAAA"]

        await pilot.press("ctrl+u", *"status:todo status:done #errands")
        assert shown_ids(app) == ["AAAA", "CCCC"]

        await pilot.press("ctrl+u", *"priority:high")
        assert shown_ids(app) == ["BBBB"]
        assert [source.task.id for source in app.screen.tasks] == ["BBBB"]


@pytest.mark.asyncio
async def test_action_keys_are_typed_into_the_filter_bar(tmp_path: Path) -> None:
    save_filter_tasks(tmp_path)
    before = loaded(tmp_path)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("slash", *"sdneoSR")

        assert isinstance(app.screen, TaskListScreen)
        assert filter_bar(app).value == "sdneoSR"
        assert app.screen.sort_key == SortKey.DUE
        assert not app.screen.sort_reverse
    assert loaded(tmp_path) == before


@pytest.mark.asyncio
async def test_no_matches_shows_a_filter_message(tmp_path: Path) -> None:
    save_filter_tasks(tmp_path)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("slash", *"nothing")

        no_tasks = app.screen.query_one("#no-tasks", Static)
        assert shown_ids(app) == []
        assert no_tasks.has_class("-shown")
        assert str(no_tasks.content) == "No tasks match the filter."


@pytest.mark.asyncio
async def test_invalid_words_are_named_and_the_rest_still_filters(
    tmp_path: Path,
) -> None:
    save_filter_tasks(tmp_path)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("slash", *"#errands status:l")

        assert filter_error(app) == "unknown status 'l'; use todo, doing or done"
        assert filter_bar(app).has_class("-invalid")
        assert shown_ids(app) == ["AAAA", "CCCC"]

        await pilot.press(*" priority:")
        assert filter_error(app) == (
            "unknown status 'l'; use todo, doing or done\n"
            "priority: needs a value; use low, normal or high"
        )

        await pilot.press("ctrl+u", *"#errands status:done")

        assert filter_error(app) is None
        assert not filter_bar(app).has_class("-invalid")
        assert shown_ids(app) == ["CCCC"]


@pytest.mark.asyncio
async def test_enter_goes_back_to_the_table_and_keeps_the_filter(
    tmp_path: Path,
) -> None:
    save_filter_tasks(tmp_path)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("slash", *"#errands", "enter")

        assert isinstance(app.screen, TaskListScreen)
        assert app.focused is app.screen.query_one("#task-table")
        assert filter_bar(app).display
        assert shown_ids(app) == ["AAAA", "CCCC"]

        # Now Enter opens the task under the cursor, out of the filtered rows.
        await pilot.press("down", "enter")
        assert isinstance(app.screen, TaskDetailScreen)
        assert app.screen.source.task.id == "CCCC"


@pytest.mark.asyncio
async def test_enter_in_a_blank_filter_bar_hides_it(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("slash", "space", "enter")

        assert isinstance(app.screen, TaskListScreen)
        assert not filter_bar(app).display
        assert app.focused is app.screen.query_one("#task-table")


@pytest.mark.asyncio
async def test_slash_edits_the_current_filter(tmp_path: Path) -> None:
    save_filter_tasks(tmp_path)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("slash", *"buy", "enter", "slash", *" #errands")

        assert filter_bar(app).value == "buy #errands"
        assert shown_ids(app) == ["AAAA", "CCCC"]


@pytest.mark.asyncio
@pytest.mark.parametrize("from_table", [False, True])
async def test_escape_clears_the_filter_and_hides_the_bar(
    tmp_path: Path, from_table: bool
) -> None:
    save_filter_tasks(tmp_path)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("slash", *"#errands status:x")
        if from_table:
            await pilot.press("enter")
        await pilot.press("escape")

        assert not filter_bar(app).display
        assert filter_bar(app).value == ""
        assert filter_error(app) is None
        assert app.focused is app.screen.query_one("#task-table")
        assert shown_ids(app) == ["AAAA", "BBBB", "CCCC"]


@pytest.mark.asyncio
async def test_escape_without_a_filter_does_nothing(tmp_path: Path) -> None:
    save_filter_tasks(tmp_path)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("down", "escape")

        assert isinstance(app.screen, TaskListScreen)
        assert shown_ids(app) == ["AAAA", "BBBB", "CCCC"]
        assert cursor_task_id(app) == "BBBB"


@pytest.mark.asyncio
async def test_clear_filter_is_in_the_footer_only_while_the_bar_is_shown(
    tmp_path: Path,
) -> None:
    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        screen = app.screen
        assert not screen.check_action("clear_filter", ())

        await pilot.press("slash")
        assert screen.check_action("clear_filter", ())

        await pilot.press("escape")
        assert not screen.check_action("clear_filter", ())


@pytest.mark.asyncio
async def test_filter_keeps_the_cursor_on_a_task_that_still_matches(
    tmp_path: Path,
) -> None:
    save_filter_tasks(tmp_path)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("down", "down", "slash", *"buy")
        assert shown_ids(app) == ["AAAA", "CCCC"]
        assert cursor_task_id(app) == "CCCC"

        # CCCC doesn't match any more, so the cursor goes to the top.
        await pilot.press(*" milk")
        assert cursor_task_id(app) == "AAAA"


@pytest.mark.asyncio
async def test_filter_stays_applied_when_the_list_is_reloaded(
    tmp_path: Path,
) -> None:
    save_filter_tasks(tmp_path)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("slash", *"#errands", "enter")
        save_task(tmp_path, make_task("DDDD", "New errand", tags=("errands",)), None)
        app.screen.load()
        await pilot.pause()

        assert shown_ids(app) == ["AAAA", "CCCC", "DDDD"]


@pytest.mark.asyncio
async def test_task_that_stops_matching_leaves_the_cursor_on_its_row(
    tmp_path: Path,
) -> None:
    save_task(tmp_path, make_task("AAAA", "One", due=date(2026, 11, 1)), None)
    save_task(tmp_path, make_task("BBBB", "Two", due=date(2026, 11, 2)), None)
    save_task(tmp_path, make_task("CCCC", "Three", due=date(2026, 11, 3)), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("slash", *"status:todo", "enter", "down", "s")

        # BBBB is doing now, so it's hidden and CCCC takes its row.
        assert loaded(tmp_path)["BBBB"].status == Status.DOING
        assert shown_ids(app) == ["AAAA", "CCCC"]
        assert cursor_task_id(app) == "CCCC"

        # On the last row, the cursor moves up to the new last row.
        await pilot.press("s")
        assert shown_ids(app) == ["AAAA"]
        assert cursor_task_id(app) == "AAAA"


@pytest.mark.asyncio
async def test_saving_a_task_the_filter_hides_says_so(tmp_path: Path) -> None:
    save_filter_tasks(tmp_path)

    app = TskmngrApp(tmp_path)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("slash", *"#errands", "enter")
        screen = app.screen
        assert isinstance(screen, TaskListScreen)

        # As if saved from the form: one task the filter hides, one it shows.
        save_task(tmp_path, make_task("DDDD", "Untagged"), None)
        screen._form_closed("DDDD")
        save_task(tmp_path, make_task("EEEE", "Tagged", tags=("errands",)), None)
        screen._form_closed("EEEE")
        # A task deleted meanwhile isn't hidden by the filter.
        screen._form_closed("GONE")

        assert messages == [
            "Saved DDDD, but the filter hides it. Press Escape to clear the filter."
        ]
        assert cursor_task_id(app) == "EEEE"


# Sorting (M3.8)


def save_sort_tasks(directory: Path) -> None:
    """Three tasks in a different order for every sort key.

    Due: BBBB, AAAA, CCCC (no due date). Priority: BBBB, CCCC, AAAA.
    Created: AAAA, CCCC, BBBB. Updated: CCCC, AAAA, BBBB.
    """
    for task_id, due, priority, created, updated in [
        ("AAAA", date(2026, 11, 3), Priority.LOW, (10, 1), (10, 10)),
        ("BBBB", date(2026, 11, 1), Priority.HIGH, (10, 3), (10, 20)),
        ("CCCC", None, Priority.NORMAL, (10, 2), (10, 5)),
    ]:
        task = Task(
            id=task_id,
            title=f"Task {task_id}",
            due=due,
            priority=priority,
            created=datetime(2026, *created, 9, 0, tzinfo=UTC),
            updated=datetime(2026, *updated, 9, 0, tzinfo=UTC),
        )
        save_task(directory, task, None)


def header_labels(app: TskmngrApp) -> list[str]:
    table = app.screen.query_one("#task-table", DataTable)
    return [column.label.plain for column in table.columns.values()]


@pytest.mark.parametrize(
    ("sort_key", "reverse", "labels"),
    [
        (SortKey.DUE, False, ["ID", "Status", "Priority", "Due ▲", "Title"]),
        (SortKey.DUE, True, ["ID", "Status", "Priority", "Due ▼", "Title"]),
        (SortKey.PRIORITY, False, ["ID", "Status", "Priority ▼", "Due", "Title"]),
        (SortKey.PRIORITY, True, ["ID", "Status", "Priority ▲", "Due", "Title"]),
        (
            SortKey.CREATED,
            False,
            ["ID", "Status", "Priority", "Due", "Title", "Created ▲"],
        ),
        (
            SortKey.UPDATED,
            True,
            ["ID", "Status", "Priority", "Due", "Title", "Updated ▼"],
        ),
    ],
)
def test_column_labels_mark_the_sorted_column(
    sort_key: SortKey, reverse: bool, labels: list[str]
) -> None:
    assert list(column_labels(sort_key, reverse)) == labels


def test_task_row_adds_the_sorted_time_last() -> None:
    task = replace(
        make_task("A", "Read"), updated=datetime(2026, 10, 30, 12, 0, 5, tzinfo=UTC)
    )

    assert [cell.plain for cell in task_row(task, SortKey.CREATED)] == [
        "A",
        "todo",
        "normal",
        "",
        "Read",
        "2026-10-28T09:15:00Z",
    ]
    assert task_row(task, SortKey.UPDATED)[-1].plain == "2026-10-30T12:00:05Z"
    assert len(task_row(task, SortKey.PRIORITY)) == 5


@pytest.mark.asyncio
async def test_capital_s_steps_through_the_sort_keys(tmp_path: Path) -> None:
    save_sort_tasks(tmp_path)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        assert shown_ids(app) == ["BBBB", "AAAA", "CCCC"]
        assert header_labels(app) == ["ID", "Status", "Priority", "Due ▲", "Title"]

        await pilot.press("S")
        assert shown_ids(app) == ["BBBB", "CCCC", "AAAA"]
        assert header_labels(app) == ["ID", "Status", "Priority ▼", "Due", "Title"]

        await pilot.press("S")
        assert shown_ids(app) == ["AAAA", "CCCC", "BBBB"]
        assert header_labels(app)[-1] == "Created ▲"
        assert table_rows(app.screen)[0][-1] == "2026-10-01T09:00:00Z"

        await pilot.press("S")
        assert shown_ids(app) == ["CCCC", "AAAA", "BBBB"]
        assert header_labels(app)[-1] == "Updated ▲"
        assert table_rows(app.screen)[0][-1] == "2026-10-05T09:00:00Z"

        await pilot.press("S")
        assert shown_ids(app) == ["BBBB", "AAAA", "CCCC"]
        assert header_labels(app) == ["ID", "Status", "Priority", "Due ▲", "Title"]
        assert len(table_rows(app.screen)[0]) == 5


@pytest.mark.asyncio
async def test_capital_r_reverses_and_undated_tasks_stay_last(
    tmp_path: Path,
) -> None:
    save_sort_tasks(tmp_path)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("R")
        assert shown_ids(app) == ["AAAA", "BBBB", "CCCC"]
        assert header_labels(app)[3] == "Due ▼"

        await pilot.press("R")
        assert shown_ids(app) == ["BBBB", "AAAA", "CCCC"]
        assert header_labels(app)[3] == "Due ▲"

        await pilot.press("S", "R")
        assert shown_ids(app) == ["AAAA", "CCCC", "BBBB"]
        assert header_labels(app)[2] == "Priority ▲"

        # The next key starts in its default direction again.
        await pilot.press("S")
        assert shown_ids(app) == ["AAAA", "CCCC", "BBBB"]
        assert header_labels(app)[-1] == "Created ▲"
        assert not app.screen.sort_reverse


@pytest.mark.asyncio
async def test_sorting_keeps_the_cursor_on_the_same_task(tmp_path: Path) -> None:
    save_sort_tasks(tmp_path)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("down")
        assert cursor_task_id(app) == "AAAA"

        await pilot.press("S")
        assert shown_ids(app) == ["BBBB", "CCCC", "AAAA"]
        assert cursor_task_id(app) == "AAAA"

        await pilot.press("R")
        assert cursor_task_id(app) == "AAAA"
        assert app.screen.query_one("#task-table", DataTable).cursor_row == 0


@pytest.mark.asyncio
async def test_sort_is_kept_on_reload_and_applies_to_the_filtered_list(
    tmp_path: Path,
) -> None:
    save_sort_tasks(tmp_path)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("S", "slash", *"status:todo", "enter")
        save_task(
            tmp_path,
            make_task("DDDD", "Urgent", priority=Priority.HIGH, status=Status.DONE),
            None,
        )
        save_task(tmp_path, make_task("EEEE", "Low", priority=Priority.LOW), None)
        app.screen.load()
        await pilot.pause()

        # DDDD is done, so the filter hides it; EEEE ties with AAAA on priority
        # and was created later.
        assert shown_ids(app) == ["BBBB", "CCCC", "AAAA", "EEEE"]
        assert header_labels(app)[2] == "Priority ▼"


@pytest.mark.asyncio
async def test_sorting_an_empty_list_changes_the_headers(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("S", "S", "R")

        assert header_labels(app)[-1] == "Created ▼"
        assert app.screen.query_one("#no-tasks").has_class("-shown")


# Column order (M6.1)


def test_shown_columns_are_the_configured_ones_in_their_order() -> None:
    columns = (Column.TITLE, Column.UPDATED, Column.ID)

    assert shown_columns(SortKey.DUE, columns) == columns
    assert shown_columns(SortKey.UPDATED, columns) == columns


@pytest.mark.parametrize(
    ("columns", "shown"),
    [
        (
            (Column.DUE, Column.TITLE, Column.ID),
            (Column.DUE, Column.TITLE, Column.ID, Column.CREATED),
        ),
        ((Column.ID, Column.DUE), (Column.ID, Column.DUE, Column.CREATED)),
        ((Column.TITLE,), (Column.TITLE, Column.CREATED)),
    ],
)
def test_sorting_by_a_hidden_time_adds_it_last(
    columns: tuple[Column, ...], shown: tuple[Column, ...]
) -> None:
    assert shown_columns(SortKey.CREATED, columns) == shown


def test_sorting_by_a_hidden_due_or_priority_leaves_it_hidden() -> None:
    columns = (Column.ID, Column.TITLE)

    assert shown_columns(SortKey.DUE, columns) == columns
    assert shown_columns(SortKey.PRIORITY, columns) == columns
    assert column_labels(SortKey.DUE, False, columns) == ("ID", "Title")


def test_column_labels_follow_the_columns_and_mark_the_sorted_one() -> None:
    columns = (Column.TITLE, Column.CREATED, Column.DUE, Column.STATUS)

    assert column_labels(SortKey.CREATED, True, columns) == (
        "Title",
        "Created ▼",
        "Due",
        "Status",
    )
    assert column_labels(SortKey.UPDATED, False, columns) == (
        "Title",
        "Created",
        "Due",
        "Status",
        "Updated ▲",
    )


def test_task_row_follows_the_columns() -> None:
    task = replace(
        make_task("A", "Read", tags=("books",), priority=Priority.HIGH),
        updated=datetime(2026, 10, 30, 12, 0, 5, tzinfo=UTC),
    )
    columns = (Column.UPDATED, Column.TITLE, Column.PRIORITY, Column.CREATED)

    assert [cell.plain for cell in task_row(task, SortKey.DUE, columns)] == [
        "2026-10-30T12:00:05Z",
        "Read #books",
        "high",
        "2026-10-28T09:15:00Z",
    ]


@pytest.mark.asyncio
async def test_the_table_has_the_configured_columns(tmp_path: Path) -> None:
    save_sort_tasks(tmp_path)
    config = Config(columns=(Column.TITLE, Column.DUE, Column.ID))

    app = TskmngrApp(tmp_path, config=config, poll_interval=0)
    async with app.run_test() as pilot:
        assert header_labels(app) == ["Title", "Due ▲", "ID"]
        assert table_rows(app.screen)[0] == ["Task BBBB", "2026-11-01", "BBBB"]

        # Created isn't configured, so it's shown only while sorting by it,
        # at the far right.
        await pilot.press("S", "S")
        assert header_labels(app) == ["Title", "Due", "ID", "Created ▲"]
        assert table_rows(app.screen)[0] == [
            "Task AAAA",
            "2026-11-03",
            "AAAA",
            "2026-10-01T09:00:00Z",
        ]

        await pilot.press("S")
        assert header_labels(app) == ["Title", "Due", "ID", "Updated ▲"]

        await pilot.press("S")
        assert header_labels(app) == ["Title", "Due ▲", "ID"]


@pytest.mark.asyncio
async def test_a_configured_time_column_stays_in_its_place(tmp_path: Path) -> None:
    save_sort_tasks(tmp_path)
    config = Config(columns=(Column.ID, Column.TITLE, Column.CREATED))

    app = TskmngrApp(tmp_path, config=config, poll_interval=0)
    async with app.run_test() as pilot:
        assert header_labels(app) == ["ID", "Title", "Created"]

        await pilot.press("S", "S")
        assert header_labels(app) == ["ID", "Title", "Created ▲"]


@pytest.mark.asyncio
async def test_actions_work_with_the_id_column_hidden(tmp_path: Path) -> None:
    save_sort_tasks(tmp_path)
    config = Config(columns=(Column.TITLE,))

    app = TskmngrApp(tmp_path, config=config, poll_interval=0)
    async with app.run_test() as pilot:
        await pilot.press("down", "s")

        assert loaded(tmp_path)["AAAA"].status is Status.DOING
        assert cursor_task_id(app) == "AAAA"
        assert table_rows(app.screen) == [["Task BBBB"], ["Task AAAA"], ["Task CCCC"]]


# Task files changed on disk


@pytest.mark.asyncio
async def test_files_changed_or_added_on_disk_are_reloaded_keeping_the_cursor(
    tmp_path: Path,
) -> None:
    save_task(tmp_path, make_task("AAAA", "First", due=date(2026, 11, 2)), None)
    save_task(tmp_path, make_task("BBBB", "Second", due=date(2026, 11, 3)), None)

    app = TskmngrApp(tmp_path, poll_interval=0)
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, TaskListScreen)
        await pilot.press("down")

        path = tmp_path / "AAAA.md"
        path.write_text(path.read_text(encoding="utf-8").replace("First", "Renamed"))
        save_task(tmp_path, make_task("CCCC", "Third", due=date(2026, 11, 1)), None)
        assert app.check_tasks_dir()
        await pilot.pause()

        rows = table_rows(screen)
        assert [row[0] for row in rows] == ["CCCC", "AAAA", "BBBB"]
        assert rows[1][4] == "Renamed"
        table = screen.query_one("#task-table", DataTable)
        assert screen.tasks[table.cursor_row].task.id == "BBBB"


@pytest.mark.asyncio
async def test_files_removed_on_disk_leave_the_list(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "First", due=date(2026, 11, 2)), None)
    save_task(tmp_path, make_task("BBBB", "Second", due=date(2026, 11, 3)), None)

    app = TskmngrApp(tmp_path, poll_interval=0)
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, TaskListScreen)
        await pilot.press("down")

        (tmp_path / "BBBB.md").unlink()
        assert app.check_tasks_dir()
        await pilot.pause()

        assert [row[0] for row in table_rows(screen)] == ["AAAA"]
        assert screen.query_one("#task-table", DataTable).cursor_row == 0


@pytest.mark.asyncio
async def test_a_file_broken_and_fixed_on_disk_comes_and_goes_in_the_warning(
    tmp_path: Path,
) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)
    path = tmp_path / "AAAA.md"
    good = path.read_text(encoding="utf-8")

    app = TskmngrApp(tmp_path, poll_interval=0)
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, TaskListScreen)

        path.write_text("no frontmatter\n", encoding="utf-8")
        assert app.check_tasks_dir()
        await pilot.pause()

        text = warning_text(screen)
        assert text is not None
        assert text.splitlines()[0] == "1 task file couldn't be loaded:"
        assert table_rows(screen) == []

        path.write_text(good, encoding="utf-8")
        assert app.check_tasks_dir()
        await pilot.pause()

        assert warning_text(screen) is None
        assert [row[0] for row in table_rows(screen)] == ["AAAA"]


# Recurring tasks


def test_task_row_marks_a_repeating_task_after_the_title() -> None:
    task = make_task(
        "A",
        "Water plants",
        repeat=Repeat(1, Unit.WEEKS),
        tags=("home",),
        notes="- [x] Kitchen\n- [ ] Office\n",
    )

    assert task_row(task)[-1].plain == "Water plants ↻ [1/2] #home"


@pytest.mark.asyncio
async def test_s_to_done_adds_the_next_occurrence_of_a_repeating_task(
    tmp_path: Path,
) -> None:
    save_task(
        tmp_path,
        make_task(
            "AAAA",
            "Water plants",
            status=Status.DOING,
            due=date(2099, 3, 1),
            repeat=Repeat(1, Unit.WEEKS),
        ),
        None,
    )

    app = TskmngrApp(tmp_path)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("s")

        tasks = loaded(tmp_path)
        done = tasks.pop("AAAA")
        [following] = tasks.values()
        assert done.status is Status.DONE
        assert done.repeat is None
        assert following.due == date(2099, 3, 8)
        assert following.repeat == Repeat(1, Unit.WEEKS)
        assert messages == [f"Next occurrence: {following.id}, due 2099-03-08"]
        # Both are listed, and the cursor stays on the task that was changed.
        assert {row[0] for row in table_rows(app.screen)} == {"AAAA", following.id}
        assert cursor_task_id(app) == "AAAA"


@pytest.mark.asyncio
async def test_s_to_todo_or_doing_adds_no_occurrence(tmp_path: Path) -> None:
    save_task(
        tmp_path, make_task("AAAA", "Water plants", repeat=Repeat(1, Unit.WEEKS)), None
    )

    app = TskmngrApp(tmp_path)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("s")

        assert list(loaded(tmp_path)) == ["AAAA"]
        assert loaded(tmp_path)["AAAA"].status is Status.DOING
        assert messages == []


@pytest.mark.asyncio
async def test_s_shows_a_next_due_date_that_cant_be_computed(tmp_path: Path) -> None:
    task = make_task(
        "AAAA",
        "Water plants",
        status=Status.DOING,
        due=date(9999, 12, 1),
        repeat=Repeat(1, Unit.MONTHS),
    )
    save_task(tmp_path, task, None)

    app = TskmngrApp(tmp_path)
    messages = record_notifications(app)
    async with app.run_test() as pilot:
        await pilot.press("s")

        assert messages == [
            (
                "Can't add the next occurrence: the next occurrence of monthly "
                "would be after the year 9999. The status wasn't changed."
            )
        ]
        assert loaded(tmp_path) == {"AAAA": task}
