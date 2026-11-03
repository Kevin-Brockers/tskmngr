"""The config file: a JSON object of settings, all optional.

It lives at `~/.config/tskmngr/config.json`, or wherever `TSKMNGR_CONFIG`
points. A missing file means the defaults; the app never creates or writes
it. Anything wrong with the file (invalid JSON, an unknown key, a value of the
wrong type) is a `ConfigError`, so nothing runs with a half-read config.

    {
      "tasks_dir": "~/tasks",
      "sort": "priority",
      "reverse": false,
      "theme": "nord",
      "poll_interval": 2
    }

`tasks_dir` may start with `~`; a relative path is read from the config
file's folder. `TSKMNGR_DIR` still comes first (see `storage.tasks_dir`).
The theme is checked by the TUI, which knows the theme names.
"""

import json
import math
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tskmngr.query import SortKey

ENV_VAR = "TSKMNGR_CONFIG"
DEFAULT_PATH = Path(".config", "tskmngr", "config.json")

# Seconds between two looks at the tasks directory in the TUI; 0 turns it off.
DEFAULT_POLL_INTERVAL = 2.0


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


def config_path() -> Path:
    """The config file: `TSKMNGR_CONFIG` if set, else the default."""
    value = os.environ.get(ENV_VAR)
    if value:
        return Path(value).expanduser()
    return Path.home() / DEFAULT_PATH


def load_config(path: Path | None = None) -> Config:
    """Read the config file at `path` (default: `config_path()`).

    A missing file gives the defaults. Raises `ConfigError` if the file can't
    be read or isn't a valid config.
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
    return Config(path=path, **values)  # type: ignore[arg-type]


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


# Each known key and how its value is read, in the order the docs list them.
_READERS: dict[str, Callable[[object, Path], object]] = {
    "tasks_dir": _tasks_dir,
    "sort": _sort,
    "reverse": _reverse,
    "theme": _theme,
    "poll_interval": _poll_interval,
}


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
