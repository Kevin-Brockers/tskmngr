"""The Textual app (the TUI)."""

from collections.abc import Iterable, Mapping
from pathlib import Path

from textual.app import App
from textual.binding import Binding, BindingType
from textual.screen import Screen

from tskmngr.config import Config, ConfigError, tasks_directory
from tskmngr.storage import TRASH, FileStamp, scan_tasks_dir, scan_trash
from tskmngr.widgets.confirm_delete import ConfirmDeleteScreen
from tskmngr.widgets.confirm_discard import ConfirmDiscardScreen
from tskmngr.widgets.task_detail import TaskDetailScreen
from tskmngr.widgets.task_form import TaskFormScreen
from tskmngr.widgets.task_list import TaskListScreen
from tskmngr.widgets.tasks_changed import TasksChanged

# Every screen with key bindings; the config's `keybindings` can remap these.
BINDING_SCREENS: tuple[type[Screen], ...] = (
    TaskListScreen,
    TaskDetailScreen,
    TaskFormScreen,
    ConfirmDeleteScreen,
    ConfirmDiscardScreen,
)


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

        `directory` is the tasks directory; by default the config's
        (`config.tasks_directory`). `poll_interval` overrides the config's;
        0 turns polling off. Raises `ConfigError` for a theme Textual doesn't
        have, or keybindings that name an unknown binding or give two bindings
        on one screen the same key.
        """
        super().__init__()
        self.config = config if config is not None else Config()
        self.directory = (
            directory if directory is not None else tasks_directory(self.config)
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
        if self.config.keybindings:
            problem = keymap_problem(self.config.keybindings)
            if problem is not None:
                raise ConfigError(
                    self.config.path or Path("config"), f"keybindings: {problem}"
                )
            self.set_keymap(dict(self.config.keybindings))
        # The task files as last seen; None if the directory couldn't be read.
        self._stamps: dict[str, FileStamp] | None = None

    def on_mount(self) -> None:
        self._stamps = self._scan()
        self.push_screen(
            TaskListScreen(
                self.directory,
                sort_key=self.config.sort,
                reverse=self.config.reverse,
                columns=self.config.columns,
                trash_columns=self.config.trash_columns,
                show_trash=self.config.show_trash,
            )
        )
        if self.poll_interval > 0:
            self.set_interval(self.poll_interval, self.check_tasks_dir)

    def check_tasks_dir(self) -> bool:
        """Send `TasksChanged` to every screen if task files changed on disk.

        Compares the time and size of each task file, and each file in
        `.trash/`, with the last check. Returns whether anything changed. The app's own saves count too; the
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
            stamps = scan_tasks_dir(self.directory)
            # Named apart from task files, which can't be in a folder.
            for name, stamp in scan_trash(self.directory).items():
                stamps[f"{TRASH}/{name}"] = stamp
            return stamps
        except OSError:
            # The list shows the error when it reloads; check again later.
            return None


def binding_ids() -> list[str]:
    """The ids of the bindings the config's `keybindings` can remap."""
    return [
        binding.id
        for screen in BINDING_SCREENS
        for binding in _bindings(screen.BINDINGS)
        if binding.id is not None
    ]


def keymap_problem(keymap: Mapping[str, str]) -> str | None:
    """What's wrong with `keymap`, binding ids to keys, or None if it's fine.

    An id must be one of `binding_ids()`. With the keymap applied, no two
    bindings on one screen may share a key, nor take one of the app's own
    keys (`Ctrl+Q` quits on every screen).
    """
    known = binding_ids()
    for binding_id in keymap:
        if binding_id not in known:
            return (
                f"unknown binding {binding_id!r}; the bindings are {', '.join(known)}"
            )
    app_bindings = list(_bindings(TskmngrApp.BINDINGS))
    for screen in BINDING_SCREENS:
        users: dict[str, list[str]] = {}
        for binding in [*_bindings(screen.BINDINGS), *app_bindings]:
            keys = keymap.get(binding.id, binding.key) if binding.id else binding.key
            name = binding.id or f"Textual's {binding.action!r}"
            for key in _keys(keys):
                if name not in users.setdefault(key, []):
                    users[key].append(name)
        for key, names in users.items():
            if len(names) > 1:
                return f"{names[0]} and {names[1]} both use the key {key!r}"
    return None


def _bindings(bindings: Iterable[BindingType]) -> Iterable[Binding]:
    """`bindings` as `Binding`s, one per binding as written (not per key)."""
    for binding in bindings:
        yield binding if isinstance(binding, Binding) else Binding(*binding)


def _keys(keys: str) -> list[str]:
    """The keys in `keys`, comma-separated, in the names Textual matches on."""
    return [binding.key for binding in Binding.make_bindings([Binding(keys, "")])]
