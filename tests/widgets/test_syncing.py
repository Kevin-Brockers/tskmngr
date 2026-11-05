from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from textual.pilot import Pilot

from tskmngr.app import TskmngrApp
from tskmngr.config import Config
from tskmngr.gitsync import TasksRepo, open_repo
from tskmngr.models import Task
from tskmngr.storage import load_tasks, save_task
from tskmngr.widgets import external_editor, syncing
from tskmngr.widgets.syncing import Syncer
from tskmngr.widgets.task_detail import TaskDetailScreen
from tskmngr.widgets.task_form import TaskFormScreen
from tskmngr.widgets.task_list import TaskListScreen

# The `git` fixture from conftest.py: runs git in a folder, returns its output.
type Git = Callable[..., str]

CREATED = datetime(2026, 10, 28, 9, 15, tzinfo=UTC)


def make_task(task_id: str, title: str, **fields: object) -> Task:
    return Task(id=task_id, title=title, created=CREATED, updated=CREATED, **fields)


@pytest.fixture
def clone(tmp_path: Path, laid_out: Path) -> TasksRepo:
    """`remote` cloned, the way the CLI does before it starts the TUI.

    The remote has the `tasks/` folder (see `laid_out`), the tasks directory.
    """
    repo = TasksRepo(laid_out.as_uri(), True, tmp_path / "clone")
    open_repo(repo)
    return repo


def elsewhere(tmp_path: Path, remote: Path, git: Git, *tasks: Task) -> Path:
    """Save `tasks` in another clone of `remote` and push them."""
    other = tmp_path / "other"
    if not other.exists():
        git(tmp_path, "clone", "--quiet", str(remote), str(other))
    if not tasks:
        return other
    for task in tasks:
        save_task(other / "tasks", task, None)
    git(other, "add", "--all")
    git(other, "commit", "--quiet", "-m", "elsewhere")
    git(other, "push", "--quiet", "origin", "HEAD:main")
    return other


def synced_app(repo: TasksRepo) -> TskmngrApp:
    # Polling off, so only a sync's pull makes the screens reload.
    return TskmngrApp(config=Config(tasks_repo=repo), poll_interval=0)


type Notes = list[tuple[str, str, str]]


def record_notifications(app: TskmngrApp) -> Notes:
    """Collect the app's notifications as (severity, title, message)."""
    notes: Notes = []

    def notify(
        message: str, *, title: str = "", severity: str = "information", **_: object
    ) -> None:
        notes.append((severity, title, message))

    app.notify = notify  # type: ignore[method-assign]
    return notes


async def settle(app: TskmngrApp, pilot: Pilot) -> None:
    """Wait for the sync jobs, then for the app to handle what they reported."""
    assert app.syncer is not None
    app.syncer.wait()
    for _ in range(3):
        await pilot.pause()


def log(git: Git, directory: Path) -> list[str]:
    """The commit messages, newest first, without `laid_out`'s setup commit."""
    messages = git(directory, "log", "--format=%s").splitlines()
    return messages[:-1] if messages[-1:] == ["setup"] else messages


def titles(app: TskmngrApp) -> list[str]:
    screen = app.screen
    assert isinstance(screen, TaskListScreen)
    return [source.task.title for source in screen.tasks]


@pytest.mark.asyncio
async def test_the_app_syncs_in_full_when_it_starts(
    tmp_path: Path, remote: Path, clone: TasksRepo, git: Git
) -> None:
    elsewhere(tmp_path, remote, git, make_task("AAAA", "From elsewhere"))
    save_task(clone.tasks_directory, make_task("BBBB", "Left over"), None)

    app = synced_app(clone)
    notes = record_notifications(app)
    async with app.run_test() as pilot:
        await settle(app, pilot)

        assert sorted(titles(app)) == ["From elsewhere", "Left over"]
    assert log(git, remote) == ["tskmngr: sync", "elsewhere"]
    # A sync nobody asked for is silent when it works.
    assert notes == []


@pytest.mark.asyncio
async def test_status_changes_are_committed_and_pushed(
    remote: Path, clone: TasksRepo, git: Git
) -> None:
    save_task(clone.tasks_directory, make_task("AAAA", "Buy milk"), None)

    app = synced_app(clone)
    async with app.run_test() as pilot:
        await settle(app, pilot)
        await pilot.press("s")
        await settle(app, pilot)
        await pilot.press("s")
        await settle(app, pilot)

    assert log(git, remote) == [
        "tskmngr: done AAAA Buy milk",
        "tskmngr: edit AAAA Buy milk",
        "tskmngr: sync",
    ]
    assert git(clone.directory, "status", "--porcelain") == ""


@pytest.mark.asyncio
async def test_a_new_task_from_the_form_is_committed_as_added(
    remote: Path, clone: TasksRepo, git: Git
) -> None:
    app = synced_app(clone)
    async with app.run_test() as pilot:
        await settle(app, pilot)
        await pilot.press("n", *"Buy milk")
        assert isinstance(app.screen, TaskFormScreen)
        await pilot.press("ctrl+s")
        await settle(app, pilot)

    [source] = load_tasks(clone.tasks_directory).tasks
    assert log(git, remote) == [f"tskmngr: add {source.task.id} Buy milk"]


@pytest.mark.asyncio
async def test_an_edit_in_the_form_is_committed(
    remote: Path, clone: TasksRepo, git: Git
) -> None:
    save_task(clone.tasks_directory, make_task("AAAA", "Buy milk"), None)

    app = synced_app(clone)
    async with app.run_test() as pilot:
        await settle(app, pilot)
        # The title starts selected, so typing replaces it.
        await pilot.press("e", *"Buy oat milk", "ctrl+s")
        await settle(app, pilot)

    assert log(git, remote)[0] == "tskmngr: edit AAAA Buy oat milk"


@pytest.mark.asyncio
async def test_a_delete_is_committed(remote: Path, clone: TasksRepo, git: Git) -> None:
    save_task(clone.tasks_directory, make_task("AAAA", "Buy milk"), None)

    app = synced_app(clone)
    async with app.run_test() as pilot:
        await settle(app, pilot)
        await pilot.press("d", "y")
        await settle(app, pilot)

    assert log(git, remote)[0] == "tskmngr: delete AAAA Buy milk"
    assert git(remote, "ls-tree", "--name-only", "HEAD:tasks") == ".gitkeep\n.trash"


@pytest.mark.asyncio
async def test_checking_the_last_subtask_is_committed_as_done(
    remote: Path, clone: TasksRepo, git: Git
) -> None:
    save_task(
        clone.tasks_directory, make_task("AAAA", "Trip", notes="- [ ] Pack\n"), None
    )

    app = synced_app(clone)
    async with app.run_test() as pilot:
        await settle(app, pilot)
        await pilot.press("enter")
        assert isinstance(app.screen, TaskDetailScreen)
        await pilot.press("space")
        await settle(app, pilot)

    assert log(git, remote)[0] == "tskmngr: done AAAA Trip"


@pytest.mark.asyncio
async def test_an_edit_in_the_editor_is_committed(
    remote: Path, clone: TasksRepo, git: Git, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_task(clone.tasks_directory, make_task("AAAA", "Buy milk"), None)

    def run_editor(command: list[str], path: Path) -> int:
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("Buy milk", "Buy oat milk"), encoding="utf-8")
        return 0

    monkeypatch.setenv("EDITOR", "fake-editor")
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.setattr(external_editor, "run_editor", run_editor)
    app = synced_app(clone)
    app.suspend = lambda: _nothing()  # type: ignore[method-assign]
    async with app.run_test() as pilot:
        await settle(app, pilot)
        await pilot.press("o")
        await settle(app, pilot)

    assert log(git, remote)[0] == "tskmngr: edit AAAA Buy oat milk"


class _nothing:
    """A stand-in for `App.suspend`, which needs a real terminal."""

    def __enter__(self) -> None:
        return None

    def __exit__(self, *args: object) -> None:
        return None


@pytest.mark.asyncio
async def test_the_sync_key_pulls_and_confirms(
    tmp_path: Path, remote: Path, clone: TasksRepo, git: Git
) -> None:
    app = synced_app(clone)
    notes = record_notifications(app)
    async with app.run_test() as pilot:
        await settle(app, pilot)
        elsewhere(tmp_path, remote, git, make_task("AAAA", "From elsewhere"))

        await pilot.press("y")
        await settle(app, pilot)

        assert titles(app) == ["From elsewhere"]
    assert notes == [("information", "Synced", f"Synced with {remote.as_uri()}.")]


@pytest.mark.asyncio
async def test_without_tasks_repo_there_is_no_sync_key(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path, poll_interval=0)
    async with app.run_test() as pilot:
        screen = app.screen
        assert app.syncer is None
        assert screen.check_action("sync", ()) is False

        await pilot.press("y")

        assert app.screen is screen


@pytest.mark.asyncio
async def test_the_sync_key_is_shown_with_tasks_repo(clone: TasksRepo) -> None:
    app = synced_app(clone)
    async with app.run_test() as pilot:
        await settle(app, pilot)
        assert isinstance(app.syncer, Syncer)
        assert app.screen.check_action("sync", ()) is True


@pytest.mark.asyncio
async def test_a_failed_push_is_a_warning_and_catches_up(
    tmp_path: Path, remote: Path, clone: TasksRepo, git: Git
) -> None:
    save_task(clone.tasks_directory, make_task("AAAA", "Buy milk"), None)

    app = synced_app(clone)
    notes = record_notifications(app)
    async with app.run_test() as pilot:
        await settle(app, pilot)
        remote.rename(tmp_path / "away.git")
        await pilot.press("s")
        await settle(app, pilot)

        [(severity, title, message)] = notes
        assert (severity, title) == ("warning", "Not synced")
        assert message.startswith("can't push to origin: ")
        assert message.endswith(". It's synced next time.")

        (tmp_path / "away.git").rename(remote)
        await pilot.press("y")
        await settle(app, pilot)

    assert log(git, remote)[0] == "tskmngr: edit AAAA Buy milk"


@pytest.mark.asyncio
async def test_a_conflict_is_shown_and_overwrites_nothing(
    tmp_path: Path, remote: Path, clone: TasksRepo, git: Git
) -> None:
    save_task(clone.tasks_directory, make_task("AAAA", "Buy milk"), None)
    app = synced_app(clone)
    async with app.run_test() as pilot:
        await settle(app, pilot)
    other = elsewhere(tmp_path, remote, git)
    git(other, "pull", "--quiet")
    (other / "tasks" / "AAAA.md").write_text(
        (other / "tasks" / "AAAA.md")
        .read_text(encoding="utf-8")
        .replace("milk", "oat milk"),
        encoding="utf-8",
    )
    git(other, "commit", "--quiet", "-am", "there")
    git(other, "push", "--quiet", "origin", "HEAD:main")
    path = clone.tasks_directory / "AAAA.md"
    path.write_text(path.read_text(encoding="utf-8").replace("milk", "soy milk"))

    app = synced_app(clone)
    notes = record_notifications(app)
    async with app.run_test() as pilot:
        await settle(app, pilot)

        [(severity, title, message)] = notes
        assert (severity, title) == ("error", "Sync conflict")
        assert "changed both here and there: AAAA" in message
        assert "synced next time" not in message
        assert titles(app) == ["Buy soy milk"]


@pytest.mark.asyncio
async def test_a_local_repository_without_upstream_only_commits(
    tmp_path: Path, git: Git
) -> None:
    git(tmp_path, "init", "--quiet", "repo")
    repo = TasksRepo(str(tmp_path / "repo"), False, tmp_path / "repo")
    save_task(repo.tasks_directory, make_task("AAAA", "Buy milk"), None)

    app = synced_app(repo)
    notes = record_notifications(app)
    async with app.run_test() as pilot:
        await settle(app, pilot)
        await pilot.press("y")
        await settle(app, pilot)

    assert notes == [
        (
            "information",
            "Synced",
            (
                f"{repo.directory} has no upstream branch, so the changes are "
                "only committed."
            ),
        )
    ]
    assert log(git, repo.directory) == ["tskmngr: sync"]


@pytest.mark.asyncio
async def test_an_unexpected_error_is_shown_and_later_syncs_still_run(
    clone: TasksRepo, git: Git, remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def broken(repo: TasksRepo) -> None:
        calls.append("pull")
        if len(calls) == 1:
            raise ValueError("boom")

    monkeypatch.setattr(syncing, "pull", broken)
    app = synced_app(clone)
    notes = record_notifications(app)
    async with app.run_test() as pilot:
        await settle(app, pilot)
        await pilot.press("y")
        await settle(app, pilot)

    assert notes == [
        ("warning", "Not synced", "unexpected error: boom. It's synced next time."),
        ("information", "Synced", f"Synced with {remote.as_uri()}."),
    ]
