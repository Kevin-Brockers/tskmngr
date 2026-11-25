from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest
from textual.widgets import Static

from tskmngr.app import TskmngrApp
from tskmngr.config import Config, config_path
from tskmngr.editor import Editor
from tskmngr.models import Task
from tskmngr.storage import save_task
from tskmngr.widgets import external_editor
from tskmngr.widgets.task_detail import TaskDetailScreen
from tskmngr.widgets.task_list import TaskListScreen

CREATED = datetime(2026, 10, 28, 9, 15, tzinfo=UTC)


def make_task(task_id: str, title: str, **fields: object) -> Task:
    return Task(id=task_id, title=title, created=CREATED, updated=CREATED, **fields)


@dataclass
class Recorder:
    """What happened: suspends, editor runs and notifications.

    `bin` is the only folder on `PATH`, with a fake `vim` and `nano` in it.
    """

    bin: Path
    events: list[str] = field(default_factory=list)
    runs: list[tuple[list[str], Path]] = field(default_factory=list)
    notifications: list[tuple[str, str]] = field(default_factory=list)


@pytest.fixture
def recorder(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Recorder:
    folder = tmp_path_factory.mktemp("bin")
    for editor in Editor:
        program = folder / editor.value
        program.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        program.chmod(0o755)
    monkeypatch.setenv("PATH", str(folder))
    # Not read any more: the config's `editor` picks the editor.
    monkeypatch.setenv("VISUAL", "fake-editor --wait")
    monkeypatch.setenv("EDITOR", "fake-editor --wait")
    return Recorder(folder)


def vim(recorder: Recorder) -> list[str]:
    """The command the default editor, vim, runs as."""
    return [str(recorder.bin / "vim")]


def install(
    app: TskmngrApp,
    recorder: Recorder,
    monkeypatch: pytest.MonkeyPatch,
    edit: Callable[[Path], int] = lambda path: 0,
) -> None:
    """Fake the terminal hand-over and the editor, and record notifications."""

    # Like `App.suspend`, this doesn't resume when an exception passes through.
    @contextmanager
    def suspend() -> Iterator[None]:
        recorder.events.append("suspend")
        yield
        recorder.events.append("resume")

    def run_editor(command: list[str], path: Path) -> int:
        recorder.events.append("editor")
        recorder.runs.append((command, path))
        return edit(path)

    def notify(message: str, *, severity: str = "information", **_: object) -> None:
        recorder.notifications.append((severity, message))

    app.suspend = suspend  # type: ignore[method-assign]
    app.notify = notify  # type: ignore[method-assign]
    monkeypatch.setattr(external_editor, "run_editor", run_editor)


def retitle(title: str) -> Callable[[Path], int]:
    """A fake editor that changes the task's title, keeping the rest."""

    def edit(path: Path) -> int:
        text = path.read_text(encoding="utf-8")
        old = next(line for line in text.splitlines() if line.startswith("title:"))
        path.write_text(text.replace(old, f"title: {title}"), encoding="utf-8")
        return 0

    return edit


def list_titles(app: TskmngrApp) -> list[str]:
    screen = app.screen
    assert isinstance(screen, TaskListScreen)
    return [source.task.title for source in screen.tasks]


@pytest.mark.asyncio
async def test_o_on_the_list_opens_the_task_under_the_cursor_and_reloads(
    tmp_path: Path, recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)
    save_task(tmp_path, make_task("BBBB", "Second"), None)
    path = tmp_path / "BBBB.md"

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        install(app, recorder, monkeypatch, retitle("Edited"))
        await pilot.press("down", "o")

        assert recorder.events == ["suspend", "editor", "resume"]
        assert recorder.runs == [(vim(recorder), path)]
        assert recorder.notifications == []
        assert list_titles(app) == ["First", "Edited"]
        assert app.screen.tasks[1].text == path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_o_on_the_detail_screen_opens_the_task_and_shows_it_again(
    tmp_path: Path, recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_task(tmp_path, make_task("AAAA", "First", notes="Old notes.\n"), None)

    def edit(path: Path) -> int:
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("Old notes.", "New notes."), encoding="utf-8")
        return 0

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        install(app, recorder, monkeypatch, edit)
        await pilot.press("enter", "o")
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, TaskDetailScreen)
        assert recorder.runs == [(vim(recorder), tmp_path / "AAAA.md")]
        assert screen.source.task.notes == "New notes.\n"

        await pilot.press("escape")

        # The list reloads too.
        assert app.screen.tasks[0].task.notes == "New notes.\n"


@pytest.mark.asyncio
async def test_the_file_is_never_written_by_the_app(
    tmp_path: Path, recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)
    path = tmp_path / "AAAA.md"
    # A hand edit the app wouldn't make itself: `updated` isn't changed.
    edited = path.read_text(encoding="utf-8").replace("First", "Edited  # by hand")

    def edit(path: Path) -> int:
        path.write_text(edited, encoding="utf-8")
        return 0

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        install(app, recorder, monkeypatch, edit)
        await pilot.press("o", "enter", "o")
        await pilot.pause()

        assert app.screen.source.task.title == "Edited"
        assert app.screen.source.task.updated == CREATED
    assert path.read_text(encoding="utf-8") == edited


@pytest.mark.asyncio
async def test_a_file_left_malformed_is_reported_not_overwritten(
    tmp_path: Path, recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)
    broken = "---\ntitle: [unclosed\n---\n"

    def edit(path: Path) -> int:
        path.write_text(broken, encoding="utf-8")
        return 0

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        install(app, recorder, monkeypatch, edit)
        await pilot.press("enter", "o")
        await pilot.pause()

        # The detail screen closes back to the list, which names the file.
        screen = app.screen
        assert isinstance(screen, TaskListScreen)
        assert [(s, m.split(":")[0]) for s, m in recorder.notifications] == [
            ("error", "Can't load AAAA.md")
        ]
        assert screen.tasks == []
        assert [bad.path.name for bad in screen.bad_files] == ["AAAA.md"]
        assert screen.query_one("#load-warning", Static).has_class("-shown")
    assert (tmp_path / "AAAA.md").read_text(encoding="utf-8") == broken


@pytest.mark.asyncio
async def test_o_opens_the_editor_the_config_names(
    tmp_path: Path, recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)

    app = TskmngrApp(tmp_path, config=Config(editor=Editor.NANO))
    async with app.run_test() as pilot:
        install(app, recorder, monkeypatch, retitle("Edited"))
        await pilot.press("o")

        assert recorder.runs == [([str(recorder.bin / "nano")], tmp_path / "AAAA.md")]
        assert list_titles(app) == ["Edited"]


@pytest.mark.asyncio
async def test_an_editor_that_isnt_installed_is_reported_without_suspending(
    tmp_path: Path, recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    (recorder.bin / "nano").unlink()
    save_task(tmp_path, make_task("AAAA", "First"), None)
    config_file = tmp_path.parent / "config.json"

    app = TskmngrApp(tmp_path, config=Config(path=config_file, editor=Editor.NANO))
    async with app.run_test() as pilot:
        install(app, recorder, monkeypatch)
        await pilot.press("o")

        assert recorder.events == []
        assert recorder.notifications == [
            (
                "error",
                (
                    "Nano isn't installed; install it, or set editor to vim in "
                    f"{config_file}."
                ),
            )
        ]
        assert isinstance(app.screen, TaskListScreen)


@pytest.mark.asyncio
async def test_a_missing_editor_is_reported_and_the_app_resumed(
    tmp_path: Path, recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)

    def edit(path: Path) -> int:
        raise FileNotFoundError(2, "No such file or directory")

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        install(app, recorder, monkeypatch, edit)
        await pilot.press("o")

        assert recorder.events == ["suspend", "editor", "resume"]
        # Found on PATH but gone by the time it ran; the default config file
        # is named, since this app has none.
        assert recorder.notifications == [
            (
                "error",
                (
                    "Vim isn't installed; install it, or set editor to nano in "
                    f"{config_path()}."
                ),
            )
        ]
        assert list_titles(app) == ["First"]


@pytest.mark.asyncio
async def test_an_editor_that_cant_start_is_reported(
    tmp_path: Path, recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)

    def edit(path: Path) -> int:
        raise PermissionError(13, "Permission denied")

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        install(app, recorder, monkeypatch, edit)
        await pilot.press("o")

        assert recorder.events == ["suspend", "editor", "resume"]
        assert recorder.notifications == [
            ("error", "Can't start vim: Permission denied")
        ]


@pytest.mark.asyncio
async def test_a_failed_editor_is_a_warning_and_the_task_still_reloaded(
    tmp_path: Path, recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)
    edit = retitle("Saved anyway")

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        install(app, recorder, monkeypatch, lambda path: edit(path) or 1)
        await pilot.press("o")

        assert recorder.notifications == [
            (
                "warning",
                "vim exited with status 1; the task was reloaded from disk.",
            )
        ]
        assert list_titles(app) == ["Saved anyway"]


@pytest.mark.asyncio
async def test_a_task_deleted_meanwhile_isnt_opened_and_drops_off_the_list(
    tmp_path: Path, recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)
    save_task(tmp_path, make_task("BBBB", "Second"), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        install(app, recorder, monkeypatch)
        (tmp_path / "AAAA.md").unlink()
        await pilot.press("o")

        assert recorder.events == []
        assert recorder.notifications == [("error", "AAAA.md is gone.")]
        assert list_titles(app) == ["Second"]
    # The editor didn't get the chance to create it again.
    assert not (tmp_path / "AAAA.md").exists()


@pytest.mark.asyncio
async def test_a_terminal_that_cant_suspend_is_reported(
    tmp_path: Path, recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)

    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        install(app, recorder, monkeypatch)
        # The headless test driver can't suspend, like Textual Web.
        del app.suspend
        await pilot.press("o")

        assert recorder.events == []
        assert recorder.notifications == [
            ("error", "This terminal can't hand over to an editor.")
        ]


@pytest.mark.asyncio
async def test_o_does_nothing_without_tasks(
    tmp_path: Path, recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        install(app, recorder, monkeypatch)
        await pilot.press("o")

        assert recorder.events == []
        assert recorder.notifications == []
    assert list(tmp_path.iterdir()) == []
