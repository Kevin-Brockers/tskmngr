from datetime import UTC, date, datetime, timedelta
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
