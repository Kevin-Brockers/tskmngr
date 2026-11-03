"""The Textual app (the TUI)."""

from pathlib import Path

from textual.app import App

from tskmngr.config import Config, ConfigError
from tskmngr.storage import FileStamp, scan_tasks_dir, tasks_dir
from tskmngr.widgets.task_list import TaskListScreen
from tskmngr.widgets.tasks_changed import TasksChanged


class TskmngrApp(App):
    """The tskmngr TUI. Opens on the task list.

    Polls the tasks directory every `poll_interval` seconds and tells the
    screens when task files were changed, added or removed on disk.
    """

    TITLE = "tskmngr"

    def __init__(
        self,
        directory: Path | None = None,
        *,
        config: Config | None = None,
        poll_interval: float | None = None,
    ) -> None:
        """Settings come from `config`, the defaults if None.

        `directory` is the tasks directory; by default `storage.tasks_dir()`
        with the config's `tasks_dir`. `poll_interval` overrides the config's;
        0 turns polling off. Raises `ConfigError` for a theme Textual doesn't
        have.
        """
        super().__init__()
        self.config = config if config is not None else Config()
        self.directory = (
            directory if directory is not None else tasks_dir(self.config.tasks_dir)
        )
        self.poll_interval = (
            poll_interval if poll_interval is not None else self.config.poll_interval
        )
        if self.config.theme is not None:
            if self.config.theme not in self.available_themes:
                names = ", ".join(sorted(self.available_themes))
                raise ConfigError(
                    self.config.path or Path("config"),
                    f"theme: unknown theme {self.config.theme!r}; the themes are "
                    f"{names}",
                )
            self.theme = self.config.theme
        # The task files as last seen; None if the directory couldn't be read.
        self._stamps: dict[str, FileStamp] | None = None

    def on_mount(self) -> None:
        self._stamps = self._scan()
        self.push_screen(
            TaskListScreen(
                self.directory,
                sort_key=self.config.sort,
                reverse=self.config.reverse,
            )
        )
        if self.poll_interval > 0:
            self.set_interval(self.poll_interval, self.check_tasks_dir)

    def check_tasks_dir(self) -> bool:
        """Send `TasksChanged` to every screen if task files changed on disk.

        Compares the time and size of each task file with the last check.
        Returns whether anything changed. The app's own saves count too; the
        screens reload them like any other change.
        """
        stamps = self._scan()
        if stamps == self._stamps:
            return False
        self._stamps = stamps
        for screen in self.screen_stack:
            screen.post_message(TasksChanged())
        return True

    def _scan(self) -> dict[str, FileStamp] | None:
        try:
            return scan_tasks_dir(self.directory)
        except OSError:
            # The list shows the error when it reloads; check again later.
            return None
