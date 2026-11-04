import importlib
import inspect
import pkgutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from textual.screen import Screen

import tskmngr.widgets
from tskmngr.app import BINDING_SCREENS, TskmngrApp, binding_ids, keymap_problem
from tskmngr.config import DEFAULT_POLL_INTERVAL, DEFAULT_THEME, Config, ConfigError
from tskmngr.models import Task
from tskmngr.query import SortKey
from tskmngr.storage import TRASH, save_task, tasks_dir
from tskmngr.widgets.confirm_delete import ConfirmDeleteScreen
from tskmngr.widgets.task_form import TaskFormScreen
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
    # The default config file names this theme, so it must stay Textual's.
    assert TskmngrApp(tmp_path).theme == DEFAULT_THEME == "textual-dark"


def test_an_unknown_theme_is_a_config_error(tmp_path: Path) -> None:
    config = Config(path=tmp_path / "config.json", theme="neon")

    with pytest.raises(ConfigError) as excinfo:
        TskmngrApp(tmp_path, config=config)

    assert excinfo.value.path == tmp_path / "config.json"
    assert excinfo.value.message.startswith("theme: unknown theme 'neon'; ")


# Keybindings


def test_binding_screens_are_all_screens_in_widgets() -> None:
    screens: set[type] = set()
    for module_info in pkgutil.iter_modules(tskmngr.widgets.__path__):
        module = importlib.import_module(f"tskmngr.widgets.{module_info.name}")
        screens.update(
            cls
            for _, cls in inspect.getmembers(module, inspect.isclass)
            if issubclass(cls, Screen) and cls.__module__ == module.__name__
        )

    assert set(BINDING_SCREENS) == screens


def test_every_binding_has_its_own_id() -> None:
    ids = binding_ids()
    count = sum(len(screen.BINDINGS) for screen in BINDING_SCREENS)

    assert len(ids) == len(set(ids)) == count
    assert "task_list.new" in ids
    assert "confirm_discard.no" in ids


@pytest.mark.asyncio
async def test_keybindings_from_the_config_replace_the_default_keys(
    tmp_path: Path,
) -> None:
    config = Config(keybindings={"task_list.new": "a,f2"})
    app = TskmngrApp(tmp_path, config=config, poll_interval=0)
    async with app.run_test() as pilot:
        bindings = app.screen.active_bindings
        assert bindings["a"].binding.id == "task_list.new"
        assert bindings["f2"].binding.id == "task_list.new"
        assert "n" not in bindings

        await pilot.press("n")
        assert isinstance(app.screen, TaskListScreen)

        await pilot.press("f2")
        assert isinstance(app.screen, TaskFormScreen)


@pytest.mark.asyncio
async def test_two_bindings_may_swap_keys(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)
    config = Config(keybindings={"task_list.new": "d", "task_list.delete": "n"})
    app = TskmngrApp(tmp_path, config=config, poll_interval=0)
    async with app.run_test() as pilot:
        await pilot.press("n")
        assert isinstance(app.screen, ConfirmDeleteScreen)


@pytest.mark.asyncio
async def test_keybindings_apply_to_dialogs(tmp_path: Path) -> None:
    save_task(tmp_path, make_task("AAAA", "First"), None)
    config = Config(keybindings={"confirm_delete.yes": "j"})
    app = TskmngrApp(tmp_path, config=config, poll_interval=0)
    async with app.run_test() as pilot:
        await pilot.press("d", "y")
        assert isinstance(app.screen, ConfirmDeleteScreen)

        await pilot.press("j")
        assert isinstance(app.screen, TaskListScreen)
    assert not (tmp_path / "AAAA.md").exists()
    assert len(list((tmp_path / TRASH).iterdir())) == 1


def test_the_default_keys_dont_clash() -> None:
    assert keymap_problem({}) is None


@pytest.mark.parametrize(
    ("keymap", "problem"),
    [
        (
            {"task_list.new": "d"},
            "task_list.new and task_list.delete both use the key 'd'",
        ),
        (
            {"task_list.new": "a,/"},
            "task_list.new and task_list.filter both use the key 'slash'",
        ),
        (
            {"task_list.new": "a", "task_list.edit": "a"},
            "task_list.new and task_list.edit both use the key 'a'",
        ),
        (
            {"confirm_delete.yes": "escape"},
            "confirm_delete.yes and confirm_delete.no both use the key 'escape'",
        ),
        (
            {"task_form.save": "ctrl+q"},
            "task_form.save and Textual's 'quit' both use the key 'ctrl+q'",
        ),
    ],
)
def test_two_bindings_on_one_screen_cant_share_a_key(
    keymap: dict[str, str], problem: str
) -> None:
    assert keymap_problem(keymap) == problem


def test_bindings_on_different_screens_may_share_a_key() -> None:
    assert keymap_problem({"task_detail.edit": "d", "task_form.save": "n"}) is None


def test_an_unknown_binding_is_a_problem() -> None:
    problem = keymap_problem({"task_list.nwe": "a"})

    assert problem == (
        f"unknown binding 'task_list.nwe'; the bindings are {', '.join(binding_ids())}"
    )


@pytest.mark.parametrize(
    ("keymap", "start"),
    [
        ({"task_list.nwe": "a"}, "keybindings: unknown binding 'task_list.nwe'; "),
        ({"task_list.new": "d"}, "keybindings: task_list.new and task_list.delete "),
    ],
)
def test_unusable_keybindings_are_a_config_error(
    tmp_path: Path, keymap: dict[str, str], start: str
) -> None:
    config = Config(path=tmp_path / "config.json", keybindings=keymap)

    with pytest.raises(ConfigError) as excinfo:
        TskmngrApp(tmp_path, config=config)

    assert excinfo.value.path == tmp_path / "config.json"
    assert excinfo.value.message.startswith(start)
