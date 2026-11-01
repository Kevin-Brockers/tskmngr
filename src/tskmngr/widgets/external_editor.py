"""Open a task file in the user's editor from the TUI.

The app is suspended while the editor runs, so it gets the terminal, and
resumed when it exits. The file is never written here: the caller reloads it
from disk afterwards, which also reports a file the editor left malformed.
Anything that stops the editor from running is shown as a notification.
"""

from pathlib import Path

from textual.app import App, SuspendNotSupported

from tskmngr.editor import EditorSettingError, editor_command, run_editor

TITLE = "Not opened"


def edit_in_editor(app: App, path: Path) -> None:
    """Open `path` in `$VISUAL` or `$EDITOR` and wait until the editor exits."""
    try:
        command = editor_command()
    except EditorSettingError as error:
        _notify_error(app, str(error))
        return
    if command is None:
        _notify_error(app, "Set $VISUAL or $EDITOR to open tasks in an editor.")
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
        _notify_error(app, f"Editor not found: {command[0]}")
    elif failure is not None:
        reason = failure.strerror or str(failure)
        _notify_error(app, f"Can't start {command[0]}: {reason}")
    elif status != 0:
        app.notify(
            f"{command[0]} exited with status {status}; the task was reloaded "
            "from disk.",
            title="Editor failed",
            severity="warning",
            markup=False,
        )


def _notify_error(app: App, message: str) -> None:
    app.notify(message, title=TITLE, severity="error", markup=False)
