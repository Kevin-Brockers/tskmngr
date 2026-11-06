"""Open a file in the editor the config file sets.

The config's `editor` key picks it: vim (the default) or nano, both run in the
same terminal as tskmngr. `$VISUAL` and `$EDITOR` aren't read, so the editor
is the same wherever tskmngr runs, and works without setting anything.
"""

import shutil
import subprocess
from enum import StrEnum
from pathlib import Path


class Editor(StrEnum):
    """The editors the config's `editor` key can name."""

    VIM = "vim"
    NANO = "nano"


DEFAULT_EDITOR = Editor.VIM


class EditorNotFound(Exception):
    """The editor the config names isn't installed (not on `PATH`)."""

    def __init__(self, editor: Editor) -> None:
        super().__init__(f"{editor} isn't installed")
        self.editor = editor


def editor_command(editor: Editor) -> list[str]:
    """The command that runs `editor`: the full path of its program on `PATH`.

    Raises `EditorNotFound` if it isn't installed.
    """
    program = shutil.which(editor.value)
    if program is None:
        raise EditorNotFound(editor)
    return [program]


def not_found_hint(editor: Editor, config_file: Path) -> str:
    """What to do about a missing `editor`: install it, or pick the other one."""
    other = next(choice for choice in Editor if choice is not editor)
    return (
        f"{editor} isn't installed; install it, or set editor to {other} in "
        f"{config_file}"
    )


def run_editor(command: list[str], path: Path) -> int:
    """Run `command` on `path`, wait for it to exit and return its exit status.

    The editor shares this process's terminal. Raises `OSError` if it can't be
    started, e.g. `FileNotFoundError` if the program doesn't exist.
    """
    return subprocess.run([*command, str(path)], check=False).returncode
