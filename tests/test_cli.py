from datetime import date
from pathlib import Path

import pytest

from tskmngr import cli, models
from tskmngr.app import TskmngrApp
from tskmngr.models import Priority, Status
from tskmngr.storage import load_tasks
from tskmngr.taskfile import TaskFile


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
