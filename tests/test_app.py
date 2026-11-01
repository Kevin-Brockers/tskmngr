from pathlib import Path

import pytest

from tskmngr.app import TskmngrApp
from tskmngr.storage import tasks_dir
from tskmngr.widgets.task_list import TaskListScreen


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
