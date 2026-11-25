"""Saving a task from the TUI, with the next occurrence of a repeating task.

Used wherever the TUI saves a task whose status may have become done: the
list's status key, the form and the detail view's subtask checklist.
"""

from datetime import date
from pathlib import Path

from textual.widget import Widget

from tskmngr.display import format_next_occurrence
from tskmngr.models import Status, Task
from tskmngr.recurrence import complete
from tskmngr.storage import load_tasks, save_completed, save_task
from tskmngr.taskfile import TaskFile


def save_task_and_next(
    directory: Path, task: Task, source: TaskFile | None
) -> Task | None:
    """Save `task`; if it's being marked done and repeats, add its next occurrence.

    `source` is the file `task` was loaded from (None for a new task), and
    `task.updated` the time of the change. Returns the next occurrence, if one
    was added. Raises what `save_task` and `save_completed` raise, and
    `RecurrenceError` if the next due date can't be computed (then nothing is
    saved).
    """
    was_done = source is not None and source.task.status is Status.DONE
    if task.status is not Status.DONE or was_done or task.repeat is None:
        save_task(directory, task, source)
        return None
    done, following = complete(
        task,
        existing_ids=load_tasks(directory).ids,
        now=task.updated,
        today=date.today(),
    )
    save_completed(directory, done, source, following)
    return following


def notify_next(widget: Widget, following: Task | None) -> None:
    """Tell the user about a next occurrence that was added, if any."""
    if following is not None:
        widget.notify(format_next_occurrence(following), title="Repeats", markup=False)
