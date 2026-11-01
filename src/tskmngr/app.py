"""The Textual app (the TUI)."""

from pathlib import Path

from textual.app import App

from tskmngr.storage import tasks_dir
from tskmngr.widgets.task_list import TaskListScreen


class TskmngrApp(App):
    """The tskmngr TUI. Opens on the task list."""

    TITLE = "tskmngr"

    def __init__(self, directory: Path | None = None) -> None:
        """`directory` is the tasks directory; by default `storage.tasks_dir()`."""
        super().__init__()
        self.directory = directory if directory is not None else tasks_dir()

    def on_mount(self) -> None:
        self.push_screen(TaskListScreen(self.directory))
