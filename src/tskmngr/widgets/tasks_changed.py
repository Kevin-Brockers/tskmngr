"""The message the app sends its screens when task files change on disk."""

from textual.message import Message


class TasksChanged(Message, bubble=False):
    """Task files were changed, added or removed in the tasks directory.

    Sent to every screen on the app's stack when polling notices a change (see
    `TskmngrApp.check_tasks_dir`). It doesn't say which files changed: each
    screen reloads what it shows, or checks the task it's editing.
    """
