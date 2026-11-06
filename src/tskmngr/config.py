"""The config file: a JSON object of settings, all optional.

It lives at `~/.tskmngr/config.json`. If there's no file there, the CLI and
the TUI first write `DEFAULT_SETTINGS` to it (`create_default_config`). An
existing file is only changed by `tskmngr remote init`, which sets
`tasks_repo` (`set_tasks_repo`). A missing file reads as the defaults.
Anything wrong with the file (invalid JSON, an unknown key, a value of the
wrong type) is a `ConfigError`, so nothing runs with a half-read config.

    {
      "tasks_dir": "~/tasks",
      "sort": "priority",
      "reverse": false,
      "theme": "nord",
      "editor": "nano",
      "poll_interval": 2,
      "columns": ["id", "due", "title"],
      "trash_columns": ["title", "deleted"],
      "show_trash": false,
      "keybindings": {"task_list.new": "a", "task_form.save": "ctrl+s,f2"}
    }

`tasks_dir` may start with `~`; a relative path is read from the config
file's folder. It comes before `TSKMNGR_DIR` (see `storage.tasks_dir`).
`tasks_repo` (not in the example) is a git repository for the tasks, a remote
URL or a local folder (see `gitsync.parse_tasks_repo`); while it's set,
`tasks_dir` and `TSKMNGR_DIR` aren't used (see `tasks_directory`). Only its
type is checked here.
`columns` names the TUI task list's columns in display order (see
`display.Column`); the ones left out are hidden. `trash_columns` does the same
for the deleted tasks view (`display.TrashColumn`), and `show_trash` says
whether that view starts shown.
`editor` is the editor `o` in the TUI and `tskmngr config edit` open files
in: vim (the default) or nano (see `tskmngr.editor`).
`keybindings` maps binding ids to keys, as Textual's keymap does. The theme
and the binding ids are checked by the TUI, which knows the theme names and
the bindings.

The old file at `~/.config/tskmngr/config.json` (`OLD_PATH`) isn't read.
"""

import json
import math
import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from tskmngr.display import DEFAULT_COLUMNS, DEFAULT_TRASH_COLUMNS, Column, TrashColumn
from tskmngr.editor import DEFAULT_EDITOR, Editor
from tskmngr.gitsync import TasksRepo, parse_tasks_repo
from tskmngr.query import SortKey
from tskmngr.storage import tasks_dir

DEFAULT_PATH = Path(".tskmngr", "config.json")
# Where the config file was before; only looked for to warn that it's unused.
OLD_PATH = Path(".config", "tskmngr", "config.json")

# Seconds between two looks at the tasks directory in the TUI; 0 turns it off.
DEFAULT_POLL_INTERVAL = 2.0
# Textual's default theme, which the TUI uses when the config has none.
DEFAULT_THEME = "textual-dark"

# What a new config file holds: every setting but `tasks_dir` and
# `tasks_repo`, at its default, so the file shows what can be set. Without
# them, `TSKMNGR_DIR` or the default tasks directory is used.
DEFAULT_SETTINGS: dict[str, object] = {
    "sort": SortKey.DUE.value,
    "reverse": False,
    "theme": DEFAULT_THEME,
    "editor": DEFAULT_EDITOR.value,
    "poll_interval": 2,
    "columns": [column.value for column in DEFAULT_COLUMNS],
    "trash_columns": [column.value for column in DEFAULT_TRASH_COLUMNS],
    "show_trash": True,
    "keybindings": {},
}


class ConfigError(Exception):
    """The config file can't be used; `message` says why."""

    def __init__(self, path: Path, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


@dataclass(frozen=True)
class Config:
    """The settings, with the defaults for anything not in the file."""

    # The config file read, or None if there was none.
    path: Path | None = None
    # None means `TSKMNGR_DIR` or the default (see `storage.tasks_dir`).
    tasks_dir: Path | None = None
    # The git repository for the tasks; None means they aren't synced.
    tasks_repo: TasksRepo | None = None
    sort: SortKey = SortKey.DUE
    reverse: bool = False
    # None means Textual's default theme.
    theme: str | None = None
    # The editor `o` in the TUI and `tskmngr config edit` open files in.
    editor: Editor = DEFAULT_EDITOR
    poll_interval: float = DEFAULT_POLL_INTERVAL
    # The TUI task list's columns, in display order.
    columns: tuple[Column, ...] = DEFAULT_COLUMNS
    # The TUI's deleted tasks view: its columns in display order, and whether
    # it starts shown.
    trash_columns: tuple[TrashColumn, ...] = DEFAULT_TRASH_COLUMNS
    show_trash: bool = True
    # Binding id to its keys, comma-separated, like Textual's keymap.
    keybindings: dict[str, str] = field(default_factory=dict)
    # The keys the file sets; the other settings are at their defaults. Not
    # compared, so a config equals another with the same settings.
    keys: frozenset[str] = field(default=frozenset(), compare=False)


def tasks_directory(config: Config) -> Path:
    """The tasks directory in use: `tasks_repo`'s, else as `storage.tasks_dir`.

    A `tasks_repo`'s is its `tasks/` folder (see `gitsync`).
    """
    if config.tasks_repo is not None:
        return config.tasks_repo.tasks_directory
    return tasks_dir(config.tasks_dir)


def config_path() -> Path:
    """The config file, `~/.tskmngr/config.json`."""
    return Path.home() / DEFAULT_PATH


def old_config_path() -> Path:
    """Where the config file was before, `~/.config/tskmngr/config.json`."""
    return Path.home() / OLD_PATH


def default_config_text() -> str:
    """The text of a new config file: `DEFAULT_SETTINGS` as indented JSON."""
    return json.dumps(DEFAULT_SETTINGS, indent=2) + "\n"


def create_default_config(path: Path) -> bool:
    """Write the default config to `path` if nothing is there yet.

    Returns whether it was written. An existing file (or anything else at
    `path`) is never overwritten. The file appears whole or not at all: it's
    written to a hidden temp file, then linked to `path`, which fails if
    `path` came into being meanwhile. Missing folders are created. Raises
    `ConfigError` if the file can't be written.
    """
    if os.path.lexists(path):
        return False
    temp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # 0o666 lets the umask decide the file's permissions, like open() does.
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as file:
                file.write(default_config_text())
                file.flush()
                os.fsync(file.fileno())
            try:
                os.link(temp, path)
            except FileExistsError:
                # Made by someone else since the check above: leave it be.
                return False
        finally:
            temp.unlink(missing_ok=True)
    except OSError as error:
        reason = error.strerror or str(error)
        raise ConfigError(path, f"can't be created: {reason}") from error
    return True


def set_tasks_repo(path: Path, location: str) -> None:
    """Set `tasks_repo` to `location` in the config file at `path`.

    The only change tskmngr makes to an existing config file, for `tskmngr
    remote init`. Every other key and value is kept, in its order; the file is
    written as indented JSON like the default one, so its whitespace changes.
    The new file replaces the old one whole, through a hidden temp file.
    Raises `ConfigError` if the file can't be read, isn't a JSON object or
    can't be written.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        reason = getattr(error, "strerror", None) or str(error)
        raise ConfigError(path, f"can't be read: {reason}") from error
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ConfigError(
            path, f"line {error.lineno}, column {error.colno}: {error.msg}"
        ) from None
    if not isinstance(data, dict):
        raise ConfigError(
            path, f"expected an object of settings, got {_describe(data)}"
        )
    data["tasks_repo"] = location
    temp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    try:
        # 0o666 lets the umask decide the file's permissions, like open() does.
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as file:
            file.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, path)
    except OSError as error:
        reason = error.strerror or str(error)
        raise ConfigError(path, f"can't be written: {reason}") from error
    finally:
        temp.unlink(missing_ok=True)


def editor_setting(path: Path) -> Editor:
    """The editor the config file at `path` names, for `tskmngr config edit`.

    That command opens the file even when it can't be used, so it can be
    fixed: anything that keeps `editor` from being read (no file, not JSON,
    not an object, a bad value) gives the default editor. Other keys aren't
    checked.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return DEFAULT_EDITOR
    value = data.get("editor") if isinstance(data, dict) else None
    try:
        return _editor(value, path) if value is not None else DEFAULT_EDITOR
    except _BadValue:
        return DEFAULT_EDITOR


def load_config(path: Path | None = None) -> Config:
    """Read the config file at `path` (default: `config_path()`).

    A missing file gives the defaults (`create_default_config` writes one
    first). Raises `ConfigError` if the file can't be read or isn't a valid
    config.
    """
    path = path if path is not None else config_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Config()
    except UnicodeDecodeError:
        raise ConfigError(path, "not UTF-8 text") from None
    except OSError as error:
        reason = error.strerror or str(error)
        raise ConfigError(path, f"can't be read: {reason}") from error
    return parse_config(text, path)


def parse_config(text: str, path: Path) -> Config:
    """The config in `text`, the contents of the file at `path`.

    `path` names the file in errors and is where a relative `tasks_dir` is
    read from. Raises `ConfigError` if `text` isn't a valid config.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ConfigError(
            path, f"line {error.lineno}, column {error.colno}: {error.msg}"
        ) from None
    if not isinstance(data, dict):
        raise ConfigError(
            path, f"expected an object of settings, got {_describe(data)}"
        )
    unknown = [key for key in data if key not in _READERS]
    if unknown:
        known = ", ".join(_READERS)
        raise ConfigError(
            path, f"unknown key {unknown[0]!r}; the known keys are {known}"
        )
    values: dict[str, object] = {}
    for key, value in data.items():
        try:
            values[key] = _READERS[key](value, path)
        except _BadValue as error:
            raise ConfigError(path, f"{key}: {error}") from None
    return Config(path=path, keys=frozenset(data), **values)  # type: ignore[arg-type]


class _BadValue(Exception):
    """A setting's value can't be used; the message says what was expected."""


def _tasks_dir(value: object, path: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise _BadValue(f"expected a folder path, got {_describe(value)}")
    directory = Path(value).expanduser()
    return directory if directory.is_absolute() else path.parent / directory


def _tasks_repo(value: object, path: Path) -> TasksRepo:
    if not isinstance(value, str) or not value.strip():
        raise _BadValue(
            f"expected a git repository's URL or folder, got {_describe(value)}"
        )
    return parse_tasks_repo(value.strip(), path.parent)


def _sort(value: object, path: Path) -> SortKey:
    names = ", ".join(key.value for key in SortKey)
    if not isinstance(value, str) or value not in set(SortKey):
        raise _BadValue(f"expected one of {names}, got {_describe(value)}")
    return SortKey(value)


def _editor(value: object, path: Path) -> Editor:
    names = " or ".join(editor.value for editor in Editor)
    if not isinstance(value, str) or value not in set(Editor):
        raise _BadValue(f"expected {names}, got {_describe(value)}")
    return Editor(value)


def _boolean(value: object, path: Path) -> bool:
    if not isinstance(value, bool):
        raise _BadValue(f"expected true or false, got {_describe(value)}")
    return value


def _theme(value: object, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _BadValue(f"expected a theme name, got {_describe(value)}")
    return value


def _poll_interval(value: object, path: Path) -> float:
    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
    # JSON reads NaN and Infinity too.
    if not is_number or not math.isfinite(value) or value < 0:  # type: ignore[arg-type,operator]
        raise _BadValue(
            f"expected a number of seconds, 0 or more, got {_describe(value)}"
        )
    return float(value)  # type: ignore[arg-type]


def _columns(value: object, path: Path) -> tuple[Column, ...]:
    return _column_names(value, Column)


def _trash_columns(value: object, path: Path) -> tuple[TrashColumn, ...]:
    return _column_names(value, TrashColumn)


def _column_names[C: StrEnum](value: object, kind: type[C]) -> tuple[C, ...]:
    """A non-empty list of names of `kind`, each once, as `kind` members."""
    names = ", ".join(column.value for column in kind)
    if not isinstance(value, list):
        raise _BadValue(f"expected a list of column names, got {_describe(value)}")
    if not value:
        raise _BadValue(f"expected at least one of {names}, got an empty list")
    columns: list[C] = []
    for name in value:
        if not isinstance(name, str) or name not in set(kind):
            raise _BadValue(f"expected names from {names}, got {_describe(name)}")
        column = kind(name)
        if column in columns:
            raise _BadValue(f"{name!r} is listed twice")
        columns.append(column)
    return tuple(columns)


def _keybindings(value: object, path: Path) -> dict[str, str]:
    if not isinstance(value, dict):
        raise _BadValue(
            f"expected an object of binding ids and keys, got {_describe(value)}"
        )
    keymap: dict[str, str] = {}
    for binding_id, keys in value.items():
        names = (
            [name.strip() for name in keys.split(",")] if isinstance(keys, str) else []
        )
        if not names or not all(names):
            raise _BadValue(
                f"{binding_id}: expected one or more keys, separated by commas, "
                f"got {_describe(keys)}"
            )
        keymap[binding_id] = ",".join(names)
    return keymap


# Each known key and how its value is read, in the order the docs list them.
_READERS: dict[str, Callable[[object, Path], object]] = {
    "tasks_dir": _tasks_dir,
    "tasks_repo": _tasks_repo,
    "sort": _sort,
    "reverse": _boolean,
    "theme": _theme,
    "editor": _editor,
    "poll_interval": _poll_interval,
    "columns": _columns,
    "trash_columns": _trash_columns,
    "show_trash": _boolean,
    "keybindings": _keybindings,
}


# Every key the file may have, in the order the docs list them.
SETTING_KEYS: tuple[str, ...] = tuple(_READERS)


def _describe(value: object) -> str:
    """A JSON value in plain words, for error messages."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return f"the boolean {str(value).lower()}"
    if isinstance(value, (int, float)):
        return f"the number {value}"
    if isinstance(value, str):
        return f"the text {value!r}"
    if isinstance(value, list):
        return "a list"
    return "an object"
