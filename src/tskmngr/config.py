"""The config file: a JSON object of settings, all optional.

It lives at `~/.tskmngr/config.json`. If there's no file there, the CLI and
the TUI first write `DEFAULT_SETTINGS` to it (`create_default_config`); an
existing file is never changed. A missing file reads as the defaults.
Anything wrong with the file (invalid JSON, an unknown key, a value of the
wrong type) is a `ConfigError`, so nothing runs with a half-read config.

    {
      "tasks_dir": "~/tasks",
      "sort": "priority",
      "reverse": false,
      "theme": "nord",
      "poll_interval": 2,
      "columns": ["id", "due", "title"],
      "keybindings": {"task_list.new": "a", "task_form.save": "ctrl+s,f2"}
    }

`tasks_dir` may start with `~`; a relative path is read from the config
file's folder. It comes before `TSKMNGR_DIR` (see `storage.tasks_dir`).
`columns` names the TUI task list's columns in display order (see
`display.Column`); the ones left out are hidden.
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
from pathlib import Path

from tskmngr.display import DEFAULT_COLUMNS, Column
from tskmngr.query import SortKey

DEFAULT_PATH = Path(".tskmngr", "config.json")
# Where the config file was before; only looked for to warn that it's unused.
OLD_PATH = Path(".config", "tskmngr", "config.json")

# Seconds between two looks at the tasks directory in the TUI; 0 turns it off.
DEFAULT_POLL_INTERVAL = 2.0
# Textual's default theme, which the TUI uses when the config has none.
DEFAULT_THEME = "textual-dark"

# What a new config file holds: every setting but `tasks_dir`, at its default,
# so the file shows what can be set. Without `tasks_dir`, `TSKMNGR_DIR` or the
# default tasks directory is used.
DEFAULT_SETTINGS: dict[str, object] = {
    "sort": SortKey.DUE.value,
    "reverse": False,
    "theme": DEFAULT_THEME,
    "poll_interval": 2,
    "columns": [column.value for column in DEFAULT_COLUMNS],
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
    sort: SortKey = SortKey.DUE
    reverse: bool = False
    # None means Textual's default theme.
    theme: str | None = None
    poll_interval: float = DEFAULT_POLL_INTERVAL
    # The TUI task list's columns, in display order.
    columns: tuple[Column, ...] = DEFAULT_COLUMNS
    # Binding id to its keys, comma-separated, like Textual's keymap.
    keybindings: dict[str, str] = field(default_factory=dict)
    # The keys the file sets; the other settings are at their defaults. Not
    # compared, so a config equals another with the same settings.
    keys: frozenset[str] = field(default=frozenset(), compare=False)


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


def _sort(value: object, path: Path) -> SortKey:
    names = ", ".join(key.value for key in SortKey)
    if not isinstance(value, str) or value not in set(SortKey):
        raise _BadValue(f"expected one of {names}, got {_describe(value)}")
    return SortKey(value)


def _reverse(value: object, path: Path) -> bool:
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
    names = ", ".join(column.value for column in Column)
    if not isinstance(value, list):
        raise _BadValue(f"expected a list of column names, got {_describe(value)}")
    if not value:
        raise _BadValue(f"expected at least one of {names}, got an empty list")
    columns: list[Column] = []
    for name in value:
        if not isinstance(name, str) or name not in set(Column):
            raise _BadValue(f"expected names from {names}, got {_describe(name)}")
        column = Column(name)
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
    "sort": _sort,
    "reverse": _reverse,
    "theme": _theme,
    "poll_interval": _poll_interval,
    "columns": _columns,
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
