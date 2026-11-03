from datetime import UTC, datetime
from pathlib import Path

import pytest

from tskmngr.app import TskmngrApp
from tskmngr.config import DEFAULT_POLL_INTERVAL, Config, ConfigError
from tskmngr.models import Task
from tskmngr.query import SortKey
from tskmngr.storage import save_task, tasks_dir
from tskmngr.widgets.task_list import TaskListScreen

CREATED = datetime(2026, 10, 28, 9, 15, tzinfo=UTC)


def make_task(task_id: str, title: str) -> Task:
    return Task(id=task_id, title=title, created=CREATED, updated=CREATED)


@pytest.mark.asyncio
async def test_app_starts_and_quits(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path)
    async with app.run_test() as pilot:
        assert app.title == "tskmngr"
        await pilot.press("ctrl+q")
    assert app.return_code == 0


@pytest.mark.asyncio
async def test_app_opens_on_the_task_list_of_its_directory(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path)
    async with app.run_test():
        assert isinstance(app.screen, TaskListScreen)
        assert app.screen.directory == tmp_path


def test_app_uses_the_tasks_directory_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TSKMNGR_DIR", str(tmp_path / "tasks"))

    assert TskmngrApp().directory == tasks_dir() == tmp_path / "tasks"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("interval", "expected"), [(None, DEFAULT_POLL_INTERVAL), (0.5, 0.5), (0, None)]
)
async def test_app_polls_the_tasks_directory_on_a_timer(
    tmp_path: Path, interval: float | None, expected: float | None
) -> None:
    app = (
        TskmngrApp(tmp_path)
        if interval is None
        else TskmngrApp(tmp_path, poll_interval=interval)
    )
    intervals: list[float] = []
    set_interval = app.set_interval

    def record(seconds: float, callback: object, **kwargs: object) -> object:
        if callback == app.check_tasks_dir:
            intervals.append(seconds)
        return set_interval(seconds, callback, **kwargs)  # type: ignore[arg-type]

    app.set_interval = record  # type: ignore[method-assign]
    async with app.run_test():
        assert intervals == ([] if expected is None else [expected])


def test_default_poll_interval_is_two_seconds() -> None:
    assert DEFAULT_POLL_INTERVAL == 2.0


@pytest.mark.asyncio
async def test_check_tasks_dir_reports_each_change_once(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path, poll_interval=0)
    async with app.run_test():
        assert not app.check_tasks_dir()

        save_task(tmp_path, make_task("AAAA", "First"), None)

        assert app.check_tasks_dir()
        assert not app.check_tasks_dir()


@pytest.mark.asyncio
async def test_a_directory_that_cant_be_read_is_a_change_both_ways(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(directory: Path) -> None:
        raise PermissionError(13, "Permission denied")

    app = TskmngrApp(tmp_path, poll_interval=0)
    async with app.run_test():
        monkeypatch.setattr("tskmngr.app.scan_tasks_dir", fail)
        assert app.check_tasks_dir()
        assert not app.check_tasks_dir()

        monkeypatch.undo()
        assert app.check_tasks_dir()


@pytest.mark.asyncio
async def test_a_task_added_on_disk_shows_up_in_the_list_by_itself(
    tmp_path: Path,
) -> None:
    app = TskmngrApp(tmp_path, poll_interval=0.05)
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, TaskListScreen)

        save_task(tmp_path, make_task("AAAA", "First"), None)
        # Generous, so a slow machine doesn't fail it; usually one interval.
        for _ in range(100):
            await pilot.pause(0.05)
            if screen.tasks:
                break

        assert [source.task.id for source in screen.tasks] == ["AAAA"]


@pytest.mark.asyncio
async def test_the_list_starts_with_the_configured_sort(tmp_path: Path) -> None:
    config = Config(sort=SortKey.PRIORITY, reverse=True)

    app = TskmngrApp(tmp_path, config=config, poll_interval=0)
    async with app.run_test():
        screen = app.screen
        assert isinstance(screen, TaskListScreen)
        assert screen.sort_key is SortKey.PRIORITY
        assert screen.sort_reverse is True


def test_the_tasks_dir_comes_from_the_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TSKMNGR_DIR", raising=False)

    assert TskmngrApp(config=Config(tasks_dir=tmp_path)).directory == tmp_path


def test_the_poll_interval_comes_from_the_config(tmp_path: Path) -> None:
    config = Config(poll_interval=7.5)

    assert TskmngrApp(tmp_path, config=config).poll_interval == 7.5
    assert TskmngrApp(tmp_path, config=config, poll_interval=0).poll_interval == 0


@pytest.mark.asyncio
async def test_the_theme_comes_from_the_config(tmp_path: Path) -> None:
    app = TskmngrApp(tmp_path, config=Config(theme="nord"), poll_interval=0)
    async with app.run_test():
        assert app.theme == "nord"


def test_without_a_theme_textual_picks_its_default(tmp_path: Path) -> None:
    assert TskmngrApp(tmp_path).theme == "textual-dark"


def test_an_unknown_theme_is_a_config_error(tmp_path: Path) -> None:
    config = Config(path=tmp_path / "config.json", theme="neon")

    with pytest.raises(ConfigError) as excinfo:
        TskmngrApp(tmp_path, config=config)

    assert excinfo.value.path == tmp_path / "config.json"
    assert excinfo.value.message.startswith("theme: unknown theme 'neon'; ")
