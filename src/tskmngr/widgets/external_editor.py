"""Open a task file in the editor from the TUI.

The editor is the config's `editor`, vim (the default) or nano. The app is
suspended while the editor runs, so it gets the terminal, and
resumed when it exits. The file is never written here: the caller reloads it
from disk afterwards, which also reports a file the editor left malformed.
Anything that stops the editor from running is shown as a notification.
"""

from pathlib import Path

from textual.app import App, SuspendNotSupported

from tskmngr.config import Config, config_path
from tskmngr.editor import (
    DEFAULT_EDITOR,
    EditorNotFound,
    editor_command,
    not_found_hint,
    run_editor,
)

TITLE = "Not opened"


def edit_in_editor(app: App, path: Path) -> None:
    """Open `path` in the config's editor and wait until the editor exits.

    The config is `app.config` (a `TskmngrApp`'s); without one, the default
    editor is used.
    """
    config = getattr(app, "config", None)
    editor = config.editor if isinstance(config, Config) else DEFAULT_EDITOR
    config_file = (config.path if isinstance(config, Config) else None) or (
        config_path()
    )
    try:
        command = editor_command(editor)
    except EditorNotFound:
        _notify_error(app, _sentence(not_found_hint(editor, config_file)))
        return
    if not path.is_file():
        # The editor would create it, making a new task by accident.
        _notify_error(app, f"{path.name} is gone.")
        return
    status = None
    failure = None
    try:
        with app.suspend():
            # Caught inside the block: `App.suspend` doesn't resume the app
            # when an exception passes through it.
            try:
                status = run_editor(command, path)
            except OSError as error:
                failure = error
    except SuspendNotSupported:
        _notify_error(app, "This terminal can't hand over to an editor.")
        return
    if isinstance(failure, FileNotFoundError):
        _notify_error(app, _sentence(not_found_hint(editor, config_file)))
    elif failure is not None:
        reason = failure.strerror or str(failure)
        _notify_error(app, f"Can't start {editor}: {reason}")
    elif status != 0:
        app.notify(
            f"{editor} exited with status {status}; the task was reloaded from disk.",
            title="Editor failed",
            severity="warning",
            markup=False,
        )


def _sentence(text: str) -> str:
    """`text` as a notification's sentence: capitalized, with a full stop."""
    return text[:1].upper() + text[1:] + "."


def _notify_error(app: App, message: str) -> None:
    app.notify(message, title=TITLE, severity="error", markup=False)
