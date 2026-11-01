"""Find the user's text editor and open a file in it.

The editor comes from `$VISUAL`, then `$EDITOR`, the same order as git and
most Unix tools. Their value is split like a shell command line, so an editor
with arguments (`code --wait`) works. There's no fallback editor: if neither is
set, the caller tells the user.
"""

import os
import shlex
import subprocess
from collections.abc import Mapping
from pathlib import Path

ENV_VARS = ("VISUAL", "EDITOR")


class EditorSettingError(Exception):
    """`$VISUAL` or `$EDITOR` is set but can't be split into a command."""

    def __init__(self, name: str, value: str, reason: str) -> None:
        super().__init__(f"${name} can't be read as a command ({reason}): {value}")
        self.name = name
        self.value = value


def editor_command(environ: Mapping[str, str] | None = None) -> list[str] | None:
    """The editor command from `$VISUAL` or `$EDITOR`, or None if neither is set.

    `environ` defaults to `os.environ`. Variables that are empty or only
    whitespace count as unset. Raises `EditorSettingError` for a value that
    can't be split, like one with an unclosed quote.
    """
    environ = os.environ if environ is None else environ
    for name in ENV_VARS:
        value = environ.get(name, "")
        if not value.strip():
            continue
        try:
            words = shlex.split(value)
        except ValueError as error:
            raise EditorSettingError(name, value, str(error)) from None
        if words and words[0]:
            return words
    return None


def run_editor(command: list[str], path: Path) -> int:
    """Run `command` on `path`, wait for it to exit and return its exit status.

    The editor shares this process's terminal. Raises `OSError` if it can't be
    started, e.g. `FileNotFoundError` if the program doesn't exist.
    """
    return subprocess.run([*command, str(path)], check=False).returncode
