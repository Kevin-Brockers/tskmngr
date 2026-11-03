import io
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from tskmngr import cli, models
from tskmngr.app import TskmngrApp
from tskmngr.models import Priority, Status, Task
from tskmngr.storage import load_tasks, save_task
from tskmngr.taskfile import TaskFile

CREATED = datetime(2026, 10, 28, 9, 15, tzinfo=UTC)


@pytest.fixture
def tasks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty tasks directory that the CLI uses via `TSKMNGR_DIR`."""
    directory = tmp_path / "tasks"
    monkeypatch.setenv("TSKMNGR_DIR", str(directory))
    return directory


def load_all(directory: Path) -> list[TaskFile]:
    result = load_tasks(directory)
    assert result.bad_files == []
    return result.tasks


def usage_error(argv: list[str], capsys: pytest.CaptureFixture[str]) -> str:
    """Run the CLI, check it exits with argparse's usage error and return stderr."""
    with pytest.raises(SystemExit) as exit_info:
        cli.main(argv)
    assert exit_info.value.code == 2
    return capsys.readouterr().err


def test_main_without_arguments_runs_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[TskmngrApp] = []
    monkeypatch.setattr(TskmngrApp, "run", lambda self: started.append(self))

    assert cli.main([]) == 0

    assert len(started) == 1


def test_unknown_command_is_a_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert "invalid choice: 'nope'" in usage_error(["nope"], capsys)


def test_add_saves_a_task_with_defaults_and_prints_its_id(
    tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["add", "Buy milk"]) == 0

    [source] = load_all(tasks)
    task = source.task
    assert capsys.readouterr().out == f"{task.id}\n"
    assert task.title == "Buy milk"
    assert task.status is Status.TODO
    assert task.priority is Priority.NORMAL
    assert task.due is None
    assert task.tags == ()
    assert task.notes == ""
    assert task.created == task.updated


def test_add_with_priority_due_date_and_tags(tasks: Path) -> None:
    argv = ["add", "Buy milk", "--priority", "high", "--due", "2026-11-01"]
    assert cli.main([*argv, "--tag", "Errands", "--tag", "home"]) == 0

    [source] = load_all(tasks)
    assert source.task.priority is Priority.HIGH
    assert source.task.due == date(2026, 11, 1)
    assert source.task.tags == ("errands", "home")


def test_add_short_options(tasks: Path) -> None:
    assert (
        cli.main(["add", "Buy milk", "-p", "low", "-d", "2026-11-01", "-t", "a"]) == 0
    )

    [source] = load_all(tasks)
    assert source.task.priority is Priority.LOW
    assert source.task.due == date(2026, 11, 1)
    assert source.task.tags == ("a",)


def test_add_writes_the_documented_file_format(tasks: Path) -> None:
    cli.main(["add", "Buy milk", "--due", "2026-11-01", "--tag", "errands"])

    [path] = tasks.iterdir()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\ntitle: Buy milk\nstatus: todo\npriority: normal\n")
    assert "due: 2026-11-01\ntags: [errands]\n" in text


def test_add_twice_creates_two_tasks(
    tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(["add", "First"])
    cli.main(["add", "Second"])

    ids = capsys.readouterr().out.split()
    assert sorted(ids) == sorted(source.task.id for source in load_all(tasks))
    assert len(set(ids)) == 2


def test_add_avoids_the_ids_of_malformed_files(
    tasks: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tasks.mkdir()
    (tasks / "BROKEN.md").write_text("not a task", encoding="utf-8")
    seen: list[set[str]] = []

    def fake_new_id(existing: set[str]) -> str:
        seen.append(set(existing))
        return "NEWTASK001"

    monkeypatch.setattr(models, "new_id", fake_new_id)

    assert cli.main(["add", "Buy milk"]) == 0

    assert seen == [{"BROKEN"}]


@pytest.mark.parametrize(
    "due", ["1.11.2026", "2026-11-1", "20261101", "2026-W44-7", "2026-02-30", ""]
)
def test_add_rejects_a_due_date_not_in_iso_format(
    tasks: Path, due: str, capsys: pytest.CaptureFixture[str]
) -> None:
    err = usage_error(["add", "Buy milk", "--due", due], capsys)

    assert f"expected a date like 2026-11-01, got {due!r}" in err
    assert not tasks.exists()


def test_add_rejects_an_unknown_priority(
    tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    err = usage_error(["add", "Buy milk", "--priority", "urgent"], capsys)

    assert "invalid choice: 'urgent'" in err
    assert not tasks.exists()


def test_add_requires_a_title(tasks: Path, capsys: pytest.CaptureFixture[str]) -> None:
    err = usage_error(["add"], capsys)

    assert "the following arguments are required: title" in err


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["  "], "title: must not be blank"),
        (["Two\nlines"], "title: must be a single line"),
        (["Buy milk", "--tag", "two words"], "tags: tag 'two words' contains"),
        (["Buy milk", "-t", "a", "-t", "A"], "tags: duplicate tag 'a'"),
        (["Buy milk", "--tag", ""], "tags: a tag must not be empty"),
    ],
)
def test_add_reports_invalid_fields_as_usage_errors(
    tasks: Path, argv: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    err = usage_error(["add", *argv], capsys)

    assert err.startswith("usage: tskmngr add")
    assert f"tskmngr add: error: {message}" in err
    assert not tasks.exists()


def test_add_reports_a_tasks_directory_that_cant_be_created(
    tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tasks.write_text("a file, not a directory", encoding="utf-8")

    assert cli.main(["add", "Buy milk"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith(f"tskmngr: error: can't save the task in {tasks}: ")
    assert tasks.read_text(encoding="utf-8") == "a file, not a directory"


def test_add_reports_a_tasks_directory_that_cant_be_read(
    tasks: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # chmod can't take away read access when the tests run as root.
    def unreadable(directory: Path) -> object:
        raise PermissionError(13, "Permission denied", str(directory))

    monkeypatch.setattr(cli, "load_tasks", unreadable)

    assert cli.main(["add", "Buy milk"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        f"tskmngr: error: can't read the tasks in {tasks}: Permission denied\n"
    )
    assert not tasks.exists()


def test_add_never_overwrites_an_existing_file(
    tasks: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Another process creating the same ID between loading and saving.
    tasks.mkdir()
    path = tasks / "NEWTASK001.md"
    monkeypatch.setattr(models, "new_id", lambda existing: "NEWTASK001")
    original_save = cli.save_task

    def save_after_race(*args: object) -> object:
        path.write_text("someone else's task", encoding="utf-8")
        return original_save(*args)

    monkeypatch.setattr(cli, "save_task", save_after_race)

    assert cli.main(["add", "Buy milk"]) == 1

    err = capsys.readouterr().err
    assert err == f"tskmngr: error: can't save the task: {path}: already exists\n"
    assert path.read_text(encoding="utf-8") == "someone else's task"


def add_task(directory: Path, task_id: str, title: str, **fields: object) -> Task:
    """Save a task with fixed timestamps; `minutes` offsets its created time."""
    created = CREATED + timedelta(minutes=fields.pop("minutes", 0))
    task = Task(id=task_id, title=title, created=created, updated=created, **fields)
    save_task(directory, task, None)
    return task


def list_ids(argv: list[str], capsys: pytest.CaptureFixture[str]) -> list[str]:
    """Run `tskmngr list` and return the listed IDs in order."""
    assert cli.main(["list", *argv]) == 0
    lines = capsys.readouterr().out.splitlines()
    if lines == ["No tasks."]:
        return []
    assert lines[0].startswith("ID ")
    return [line.split()[0] for line in lines[1:]]


@pytest.fixture
def mixed(tasks: Path) -> Path:
    """Tasks with different statuses, priorities, due dates and tags."""
    add_task(tasks, "TODO000001", "Buy milk", tags=("errands",), minutes=1)
    add_task(
        tasks,
        "DOING00002",
        "Write report",
        status=Status.DOING,
        priority=Priority.HIGH,
        due=date(2026, 11, 5),
        tags=("work",),
        minutes=2,
    )
    add_task(
        tasks,
        "DONE000003",
        "Pay rent",
        status=Status.DONE,
        due=date(2026, 11, 1),
        tags=("home", "errands"),
        minutes=3,
    )
    add_task(
        tasks,
        "TODO000004",
        "Call the store about milk",
        priority=Priority.LOW,
        due=date(2026, 11, 2),
        notes="Ask about the **delivery**.",
        tags=("errands", "phone"),
        minutes=4,
    )
    return tasks


def test_list_prints_aligned_columns(
    tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    add_task(
        tasks,
        "6ACV1F0HMW",
        "Buy milk",
        priority=Priority.HIGH,
        due=date(2026, 11, 1),
        tags=("errands", "home"),
    )
    add_task(tasks, "Q7N2K0XB3D", "Write report", status=Status.DOING)

    assert cli.main(["list"]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == (
        "ID          STATUS  PRIORITY  DUE         TITLE\n"
        "6ACV1F0HMW  todo    high      2026-11-01  Buy milk #errands #home\n"
        "Q7N2K0XB3D  doing   normal                Write report\n"
    )


def test_list_widens_columns_for_long_values(
    tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    add_task(tasks, "shopping-list", "Hand-made file")

    cli.main(["list"])

    assert capsys.readouterr().out == (
        "ID             STATUS  PRIORITY  DUE  TITLE\n"
        "shopping-list  todo    normal         Hand-made file\n"
    )


def test_list_without_tasks(tasks: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["list"]) == 0

    assert capsys.readouterr() == ("No tasks.\n", "")
    assert not tasks.exists()


def test_list_hides_done_tasks_and_sorts_by_due_date(
    mixed: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert list_ids([], capsys) == ["TODO000004", "DOING00002", "TODO000001"]


def test_list_all_includes_done_tasks(
    mixed: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    expected = ["DONE000003", "TODO000004", "DOING00002", "TODO000001"]
    assert list_ids(["--all"], capsys) == expected
    assert list_ids(["-a"], capsys) == expected


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["--status", "done"], ["DONE000003"]),
        (["-s", "doing"], ["DOING00002"]),
        (["-s", "todo", "-s", "done"], ["DONE000003", "TODO000004", "TODO000001"]),
    ],
)
def test_list_by_status(
    mixed: Path,
    argv: list[str],
    expected: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert list_ids(argv, capsys) == expected


def test_list_status_and_all_are_exclusive(
    mixed: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    err = usage_error(["list", "--all", "--status", "done"], capsys)

    assert "not allowed with argument" in err


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["--priority", "high"], ["DOING00002"]),
        (["-p", "low", "-p", "high"], ["TODO000004", "DOING00002"]),
        (["--tag", "errands"], ["TODO000004", "TODO000001"]),
        (["-t", "errands", "-t", "Phone"], ["TODO000004"]),
        (["-a", "-t", "errands", "-p", "normal"], ["DONE000003", "TODO000001"]),
    ],
)
def test_list_by_priority_and_tags(
    mixed: Path,
    argv: list[str],
    expected: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert list_ids(argv, capsys) == expected


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["milk"], ["TODO000004", "TODO000001"]),
        (["MILK", "store"], ["TODO000004"]),
        (["delivery"], ["TODO000004"]),
        (["milk", "-t", "errands", "store"], ["TODO000004"]),
        (["-t", "errands", "milk", "--sort", "created", "buy"], ["TODO000001"]),
        (["--", "-p"], []),
        (["rent"], []),
    ],
)
def test_list_searches_title_and_notes(
    mixed: Path,
    argv: list[str],
    expected: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert list_ids(argv, capsys) == expected


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["--sort", "priority"], ["DOING00002", "TODO000001", "TODO000004"]),
        (["--sort", "created"], ["TODO000001", "DOING00002", "TODO000004"]),
        (["--sort", "updated", "-r"], ["TODO000004", "DOING00002", "TODO000001"]),
        (["--reverse"], ["DOING00002", "TODO000004", "TODO000001"]),
    ],
)
def test_list_sorts(
    mixed: Path,
    argv: list[str],
    expected: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert list_ids(argv, capsys) == expected


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--status", "open"], "invalid choice: 'open'"),
        (["--priority", "urgent"], "invalid choice: 'urgent'"),
        (["--sort", "title"], "invalid choice: 'title'"),
        (["milk", "--bogus"], "unrecognized arguments: --bogus"),
    ],
)
def test_list_usage_errors(
    tasks: Path, argv: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    err = usage_error(["list", *argv], capsys)

    assert err.startswith("usage: tskmngr list")
    assert message in err


def test_add_still_rejects_extra_arguments(
    tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    err = usage_error(["add", "Buy", "milk"], capsys)

    assert err.startswith("usage: tskmngr add")
    assert "unrecognized arguments: milk" in err
    assert not tasks.exists()


def test_list_reports_malformed_files_on_stderr(
    mixed: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = mixed / "BROKEN.md"
    broken.write_text("---\nstatus: todo\n---\n", encoding="utf-8")

    assert cli.main(["list", "-s", "done"]) == 0

    captured = capsys.readouterr()
    assert captured.err == f"tskmngr: warning: can't load {broken}: title: missing\n"
    assert captured.out.splitlines()[1].startswith("DONE000003 ")
    assert broken.read_text(encoding="utf-8") == "---\nstatus: todo\n---\n"


def test_list_reports_a_tasks_directory_that_cant_be_read(
    tasks: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def unreadable(directory: Path) -> object:
        raise PermissionError(13, "Permission denied", str(directory))

    monkeypatch.setattr(cli, "load_tasks", unreadable)

    assert cli.main(["list"]) == 1

    assert capsys.readouterr() == (
        "",
        f"tskmngr: error: can't read the tasks in {tasks}: Permission denied\n",
    )


# show, edit and done


def read(directory: Path, task_id: str) -> str:
    return (directory / f"{task_id}.md").read_text(encoding="utf-8")


def test_show_prints_all_fields_and_the_notes(
    tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    add_task(
        tasks,
        "6ACV1F0HMW",
        "Buy milk",
        status=Status.DOING,
        priority=Priority.HIGH,
        due=date(2026, 11, 1),
        tags=("errands", "home"),
        notes="Get **oat** milk.\n\n- two litres\n",
    )

    assert cli.main(["show", "6ac"]) == 0

    assert capsys.readouterr() == (
        (
            "ID:        6ACV1F0HMW\n"
            "Title:     Buy milk\n"
            "Status:    doing\n"
            "Priority:  high\n"
            "Due:       2026-11-01\n"
            "Tags:      errands, home\n"
            "Created:   2026-10-28T09:15:00Z\n"
            "Updated:   2026-10-28T09:15:00Z\n"
            "\n"
            "Get **oat** milk.\n"
            "\n"
            "- two litres\n"
        ),
        "",
    )


def test_show_without_due_date_tags_or_notes(
    tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk")

    assert cli.main(["show", "6ACV1F0HMW"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[4:6] == ["Due:       -", "Tags:      -"]
    assert lines[-1].startswith("Updated:")


def test_show_keeps_a_timezone_other_than_utc(
    tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    berlin = timezone(timedelta(hours=1))
    task = Task(
        id="6ACV1F0HMW",
        title="Buy milk",
        created=datetime(2026, 10, 28, 10, 15, tzinfo=berlin),
        updated=CREATED,
    )
    save_task(tasks, task, None)

    assert cli.main(["show", "6"]) == 0

    assert "Created:   2026-10-28T10:15:00+01:00\n" in capsys.readouterr().out


def test_show_unknown_prefix(tasks: Path, capsys: pytest.CaptureFixture[str]) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk")

    assert cli.main(["show", "XYZ"]) == 1

    assert capsys.readouterr() == (
        "",
        "tskmngr: error: no task with ID prefix 'XYZ'\n",
    )


def test_show_ambiguous_prefix_lists_the_candidates(
    tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk")
    add_task(tasks, "6AQ0000000", "Write report")

    assert cli.main(["show", "6a"]) == 1

    assert capsys.readouterr().err == (
        "tskmngr: error: ID prefix '6a' matches 2 tasks: 6ACV1F0HMW, 6AQ0000000\n"
    )


def test_show_blank_prefix_is_a_usage_error(
    tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert "ID prefix must not be blank" in usage_error(["show", " "], capsys)


@pytest.mark.parametrize("command", ["show", "edit", "done", "delete"])
def test_commands_require_an_id(
    command: str, tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert "the following arguments are required: ID" in usage_error([command], capsys)


@pytest.mark.parametrize(
    "argv",
    [["show"], ["edit", "--title", "New"], ["done"], ["delete", "--yes"]],
    ids=lambda a: a[0],
)
def test_commands_report_a_malformed_file_matching_the_prefix(
    argv: list[str], tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk")
    broken = tasks / "7BROKEN000.md"
    broken.write_text("---\nstatus: todo\n---\n", encoding="utf-8")

    assert cli.main([argv[0], "7b", *argv[1:]]) == 1

    assert capsys.readouterr() == (
        "",
        f"tskmngr: error: can't load {broken}: title: missing\n",
    )
    assert broken.read_text(encoding="utf-8") == "---\nstatus: todo\n---\n"


def test_malformed_files_make_a_prefix_ambiguous(
    tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk")
    (tasks / "6ABROKEN00.md").write_text("not a task", encoding="utf-8")

    assert cli.main(["done", "6a"]) == 1

    assert capsys.readouterr().err == (
        "tskmngr: error: ID prefix '6a' matches 2 tasks: 6ABROKEN00, 6ACV1F0HMW\n"
    )
    assert load_tasks(tasks).tasks[0].task.status is Status.TODO


def test_done_marks_the_task_done_and_updates_the_timestamp(
    tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk", status=Status.DOING)

    assert cli.main(["done", "6ACV"]) == 0

    assert capsys.readouterr() == ("", "")
    [source] = load_all(tasks)
    assert source.task.status is Status.DONE
    assert source.task.created == CREATED
    assert source.task.updated > CREATED
    assert source.task.updated.utcoffset() == timedelta(0)
    assert source.task.updated.microsecond == 0
    assert f"updated: {source.task.updated:%Y-%m-%dT%H:%M:%S}Z\n" in source.text


def test_done_on_a_done_task_leaves_the_file_alone(
    tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk", status=Status.DONE)
    before = read(tasks, "6ACV1F0HMW")

    assert cli.main(["done", "6"]) == 0

    assert capsys.readouterr() == ("", "")
    assert read(tasks, "6ACV1F0HMW") == before


def test_done_keeps_unknown_keys_and_comments(tasks: Path) -> None:
    tasks.mkdir()
    path = tasks / "6ACV1F0HMW.md"
    path.write_text(
        "---\n"
        "title: Buy milk  # from the fridge list\n"
        "status: todo\n"
        "estimate: 10min\n"
        "---\n"
        "\n"
        "Notes.\n",
        encoding="utf-8",
    )

    assert cli.main(["done", "6"]) == 0

    text = path.read_text(encoding="utf-8")
    assert "title: Buy milk  # from the fridge list\n" in text
    assert "status: done\n" in text
    assert "estimate: 10min\n" in text
    assert text.endswith("---\n\nNotes.\n")


def test_done_reports_a_conflict_and_keeps_the_other_change(
    tasks: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The file is edited by hand between loading and saving.
    add_task(tasks, "6ACV1F0HMW", "Buy milk")
    path = tasks / "6ACV1F0HMW.md"
    original_save = cli.save_task

    def save_after_edit(*args: object) -> object:
        path.write_text("---\ntitle: Edited\n---\n", encoding="utf-8")
        return original_save(*args)

    monkeypatch.setattr(cli, "save_task", save_after_edit)

    assert cli.main(["done", "6"]) == 1

    assert capsys.readouterr().err == (
        f"tskmngr: error: can't save the task: {path}: "
        "changed on disk since it was loaded\n"
    )
    assert path.read_text(encoding="utf-8") == "---\ntitle: Edited\n---\n"


def test_edit_changes_only_the_given_fields(
    tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    add_task(
        tasks,
        "6ACV1F0HMW",
        "Buy milk",
        due=date(2026, 11, 1),
        tags=("errands",),
        notes="Oat milk.",
    )

    assert cli.main(["edit", "6", "--title", "Buy oat milk", "-p", "high"]) == 0

    assert capsys.readouterr() == ("", "")
    [source] = load_all(tasks)
    task = source.task
    assert task.title == "Buy oat milk"
    assert task.priority is Priority.HIGH
    assert task.status is Status.TODO
    assert task.due == date(2026, 11, 1)
    assert task.tags == ("errands",)
    assert task.notes == "Oat milk."
    assert task.created == CREATED
    assert task.updated > CREATED


def test_edit_status_and_due_date(tasks: Path) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk")

    assert cli.main(["edit", "6", "-s", "doing", "-d", "2026-11-03"]) == 0

    [source] = load_all(tasks)
    assert source.task.status is Status.DOING
    assert source.task.due == date(2026, 11, 3)


def test_edit_removes_the_due_date(tasks: Path) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk", due=date(2026, 11, 1))

    assert cli.main(["edit", "6", "--no-due"]) == 0

    [source] = load_all(tasks)
    assert source.task.due is None
    assert "due:" not in source.text


def test_edit_due_and_no_due_are_exclusive(
    tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    err = usage_error(["edit", "6", "-d", "2026-11-01", "--no-due"], capsys)

    assert "not allowed with argument" in err


def test_edit_rejects_a_due_date_not_in_iso_format(
    tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk")
    before = read(tasks, "6ACV1F0HMW")

    assert "expected a date like 2026-11-01" in usage_error(
        ["edit", "6", "-d", "1.11.2026"], capsys
    )
    assert read(tasks, "6ACV1F0HMW") == before


def test_edit_adds_and_removes_tags(tasks: Path) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk", tags=("errands", "home"))

    argv = ["edit", "6", "-t", "Shop", "--tag", "urgent", "--untag", "HOME"]
    assert cli.main(argv) == 0

    [source] = load_all(tasks)
    assert source.task.tags == ("errands", "shop", "urgent")


def test_edit_adding_a_tag_the_task_has_changes_nothing(tasks: Path) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk", tags=("errands",))
    before = read(tasks, "6ACV1F0HMW")

    assert cli.main(["edit", "6", "-t", "Errands", "-t", "errands"]) == 0

    assert read(tasks, "6ACV1F0HMW") == before


def test_edit_removing_a_missing_tag_is_an_error(
    tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk", tags=("errands",))
    before = read(tasks, "6ACV1F0HMW")

    assert cli.main(["edit", "6", "--title", "New", "--untag", "Home"]) == 1

    assert capsys.readouterr().err == (
        "tskmngr: error: task 6ACV1F0HMW has no tag 'home'\n"
    )
    assert read(tasks, "6ACV1F0HMW") == before


def test_edit_clear_tags_then_add(tasks: Path) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk", tags=("errands", "home"))

    assert cli.main(["edit", "6", "--clear-tags", "-t", "work"]) == 0

    [source] = load_all(tasks)
    assert source.task.tags == ("work",)


def test_edit_clear_tags_and_untag_are_exclusive(
    tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    err = usage_error(["edit", "6", "--clear-tags", "--untag", "home"], capsys)

    assert "not allowed with argument" in err


def test_edit_cant_add_and_remove_the_same_tag(
    tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    err = usage_error(["edit", "6", "-t", "home", "--untag", "Home"], capsys)

    assert "can't both add and remove tag 'home'" in err


def test_edit_without_changes_is_a_usage_error(
    tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    err = usage_error(["edit", "6"], capsys)

    assert err.startswith("usage: tskmngr edit")
    assert "nothing to change" in err


def test_edit_to_the_same_values_leaves_the_file_alone(tasks: Path) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk", priority=Priority.HIGH)
    before = read(tasks, "6ACV1F0HMW")

    assert cli.main(["edit", "6", "--title", "Buy milk", "-p", "high"]) == 0

    assert read(tasks, "6ACV1F0HMW") == before


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--title", " "], "title: must not be blank"),
        (["-t", "two words"], "tags: tag 'two words' contains whitespace"),
    ],
)
def test_edit_reports_invalid_fields_as_usage_errors(
    argv: list[str], message: str, tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk")
    before = read(tasks, "6ACV1F0HMW")

    assert message in usage_error(["edit", "6", *argv], capsys)
    assert read(tasks, "6ACV1F0HMW") == before


def test_edit_reports_a_task_file_that_cant_be_saved(
    tasks: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk")

    def unwritable(*args: object) -> object:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(cli, "save_task", unwritable)

    assert cli.main(["edit", "6", "--title", "New"]) == 1

    assert capsys.readouterr().err == (
        f"tskmngr: error: can't save the task in {tasks}: Permission denied\n"
    )


# delete


class FakeTerminal(io.StringIO):
    """Stdin attached to a terminal, with the user's typed input."""

    def isatty(self) -> bool:
        return True


class InterruptedTerminal(FakeTerminal):
    """A terminal where the user presses Ctrl-C at the prompt."""

    def readline(self, size: int | None = -1) -> str:
        raise KeyboardInterrupt


def trash(directory: Path) -> list[Path]:
    return sorted((directory / ".trash").iterdir())


def test_delete_yes_moves_the_file_to_the_trash(
    tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk")
    before = read(tasks, "6ACV1F0HMW")

    assert cli.main(["delete", "6ac", "--yes"]) == 0

    [trashed] = trash(tasks)
    assert capsys.readouterr() == (f"Moved 6ACV1F0HMW to {trashed}\n", "")
    assert trashed.name.startswith("6ACV1F0HMW.")
    assert trashed.read_text(encoding="utf-8") == before
    assert load_all(tasks) == []


def test_delete_short_yes_option(tasks: Path) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk")

    assert cli.main(["delete", "6", "-y"]) == 0

    assert load_all(tasks) == []


def test_delete_keeps_the_other_tasks(tasks: Path) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk")
    add_task(tasks, "7BCD000000", "Write report")

    assert cli.main(["delete", "6", "--yes"]) == 0

    assert [source.task.id for source in load_all(tasks)] == ["7BCD000000"]


def test_delete_refuses_without_yes_when_stdin_is_not_a_terminal(
    tasks: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk")
    # Even a "y" on stdin isn't read: a script can't confirm without --yes.
    monkeypatch.setattr("sys.stdin", io.StringIO("y\n"))

    assert cli.main(["delete", "6"]) == 1

    assert capsys.readouterr() == (
        "",
        (
            "tskmngr: error: not deleting task 6ACV1F0HMW without confirmation; "
            "stdin isn't a terminal, so pass --yes\n"
        ),
    )
    assert [source.task.id for source in load_all(tasks)] == ["6ACV1F0HMW"]
    assert not (tasks / ".trash").exists()


@pytest.mark.parametrize("answer", ["y\n", "Y\n", "yes\n", " YES \n"])
def test_delete_asks_on_a_terminal_and_deletes_on_yes(
    answer: str,
    tasks: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk")
    monkeypatch.setattr("sys.stdin", FakeTerminal(answer))

    assert cli.main(["delete", "6"]) == 0

    [trashed] = trash(tasks)
    assert capsys.readouterr() == (
        f"Moved 6ACV1F0HMW to {trashed}\n",
        "Delete task 6ACV1F0HMW 'Buy milk'? [y/N] ",
    )
    assert load_all(tasks) == []


@pytest.mark.parametrize("answer", ["\n", "n\n", "no\n", "yy\n", "sure\n"])
def test_delete_on_a_terminal_keeps_the_task_unless_confirmed(
    answer: str,
    tasks: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk")
    monkeypatch.setattr("sys.stdin", FakeTerminal(answer))

    assert cli.main(["delete", "6"]) == 1

    assert capsys.readouterr() == (
        "",
        "Delete task 6ACV1F0HMW 'Buy milk'? [y/N] Not deleted.\n",
    )
    assert [source.task.id for source in load_all(tasks)] == ["6ACV1F0HMW"]
    assert not (tasks / ".trash").exists()


@pytest.mark.parametrize(
    "stdin",
    [FakeTerminal(""), InterruptedTerminal()],
    ids=["end of input", "ctrl-c"],
)
def test_delete_on_a_terminal_keeps_the_task_without_an_answer(
    stdin: FakeTerminal,
    tasks: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk")
    monkeypatch.setattr("sys.stdin", stdin)

    assert cli.main(["delete", "6"]) == 1

    # A newline ends the prompt line, since the user didn't press Enter.
    assert capsys.readouterr() == (
        "",
        "Delete task 6ACV1F0HMW 'Buy milk'? [y/N] \nNot deleted.\n",
    )
    assert [source.task.id for source in load_all(tasks)] == ["6ACV1F0HMW"]


def test_delete_unknown_prefix_doesnt_ask(
    tasks: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk")
    monkeypatch.setattr("sys.stdin", FakeTerminal("y\n"))

    assert cli.main(["delete", "XYZ"]) == 1

    assert capsys.readouterr() == (
        "",
        "tskmngr: error: no task with ID prefix 'XYZ'\n",
    )
    assert [source.task.id for source in load_all(tasks)] == ["6ACV1F0HMW"]


def test_delete_ambiguous_prefix_deletes_nothing(
    tasks: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk")
    add_task(tasks, "6AQ0000000", "Write report")

    assert cli.main(["delete", "6a", "--yes"]) == 1

    assert capsys.readouterr().err == (
        "tskmngr: error: ID prefix '6a' matches 2 tasks: 6ACV1F0HMW, 6AQ0000000\n"
    )
    assert len(load_all(tasks)) == 2


def test_delete_keeps_earlier_deletes_of_the_same_id(tasks: Path) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk")
    assert cli.main(["delete", "6", "--yes"]) == 0
    add_task(tasks, "6ACV1F0HMW", "Buy milk again")

    assert cli.main(["delete", "6", "--yes"]) == 0

    assert len(trash(tasks)) == 2


def test_delete_reports_a_conflict_and_keeps_the_edited_file(
    tasks: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The file is edited by hand while the user is asked to confirm.
    add_task(tasks, "6ACV1F0HMW", "Buy milk")
    path = tasks / "6ACV1F0HMW.md"

    class EditingTerminal(FakeTerminal):
        def readline(self, size: int | None = -1) -> str:
            path.write_text("---\ntitle: Edited\n---\n", encoding="utf-8")
            return "y\n"

    monkeypatch.setattr("sys.stdin", EditingTerminal())

    assert cli.main(["delete", "6"]) == 1

    assert capsys.readouterr().err.endswith(
        f"tskmngr: error: can't delete the task: {path}: "
        "changed on disk since it was loaded\n"
    )
    assert path.read_text(encoding="utf-8") == "---\ntitle: Edited\n---\n"
    assert not (tasks / ".trash").exists()


def test_delete_reports_a_trash_that_cant_be_written(
    tasks: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    add_task(tasks, "6ACV1F0HMW", "Buy milk")

    def unwritable(*args: object, **kwargs: object) -> object:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(cli, "delete_task", unwritable)

    assert cli.main(["delete", "6", "--yes"]) == 1

    assert capsys.readouterr().err == (
        f"tskmngr: error: can't delete the task in {tasks}: Permission denied\n"
    )
    assert [source.task.id for source in load_all(tasks)] == ["6ACV1F0HMW"]


# The config file


@pytest.fixture
def config_file(no_user_config: Path) -> Path:
    """Where the CLI looks for its config file in tests; it doesn't exist yet."""
    return no_user_config


def write_config(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


@pytest.mark.parametrize(
    ("config", "argv", "expected"),
    [
        ('{"sort": "priority"}', [], ["DOING00002", "TODO000001", "TODO000004"]),
        (
            '{"sort": "priority", "reverse": true}',
            [],
            ["TODO000004", "TODO000001", "DOING00002"],
        ),
        # --reverse flips the configured order.
        (
            '{"sort": "priority", "reverse": true}',
            ["-r"],
            ["DOING00002", "TODO000001", "TODO000004"],
        ),
        # --sort replaces the configured sort, its reverse included.
        (
            '{"sort": "priority", "reverse": true}',
            ["--sort", "created"],
            ["TODO000001", "DOING00002", "TODO000004"],
        ),
        ('{"reverse": true}', [], ["DOING00002", "TODO000004", "TODO000001"]),
    ],
)
def test_list_sorts_as_the_config_file_says(
    mixed: Path,
    config_file: Path,
    config: str,
    argv: list[str],
    expected: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_config(config_file, config)

    assert list_ids(argv, capsys) == expected


def test_commands_use_the_tasks_dir_from_the_config_file(
    tmp_path: Path,
    config_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("TSKMNGR_DIR", raising=False)
    write_config(config_file, '{"tasks_dir": "my-tasks"}')

    assert cli.main(["add", "Buy milk"]) == 0

    [source] = load_all(config_file.parent / "my-tasks")
    assert capsys.readouterr().out == f"{source.task.id}\n"


def test_tskmngr_dir_comes_before_the_config_file(
    tasks: Path, tmp_path: Path, config_file: Path
) -> None:
    write_config(config_file, f'{{"tasks_dir": "{tmp_path / "unused"}"}}')

    assert cli.main(["add", "Buy milk"]) == 0

    assert len(load_all(tasks)) == 1
    assert not (tmp_path / "unused").exists()


@pytest.mark.parametrize("argv", [["list"], ["add", "Buy milk"], []])
def test_a_broken_config_file_stops_every_command(
    tasks: Path,
    config_file: Path,
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(TskmngrApp, "run", lambda self: pytest.fail("TUI started"))
    write_config(config_file, '{"sort": "size"}')

    assert cli.main(argv) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        f"tskmngr: error: config file {config_file}: sort: expected one of due, "
        "priority, created, updated, got the text 'size'\n"
    )
    assert not tasks.exists()


def test_an_unknown_theme_stops_the_tui(
    config_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(TskmngrApp, "run", lambda self: pytest.fail("TUI started"))
    write_config(config_file, '{"theme": "neon"}')

    assert cli.main([]) == 1

    err = capsys.readouterr().err
    assert err.startswith(
        f"tskmngr: error: config file {config_file}: theme: unknown theme 'neon'; "
        "the themes are "
    )
    assert "textual-dark" in err


def test_the_tui_gets_the_config(
    tmp_path: Path, config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: list[TskmngrApp] = []
    monkeypatch.setattr(TskmngrApp, "run", lambda self: started.append(self))
    monkeypatch.delenv("TSKMNGR_DIR", raising=False)
    write_config(config_file, f'{{"tasks_dir": "{tmp_path}", "theme": "nord"}}')

    assert cli.main([]) == 0

    [app] = started
    assert app.directory == tmp_path
    assert app.theme == "nord"
    assert app.config.path == config_file


def test_help_works_with_a_broken_config_file(
    config_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_config(config_file, "not json")

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--help"])

    assert exit_info.value.code == 0
    assert "usage: tskmngr" in capsys.readouterr().out
