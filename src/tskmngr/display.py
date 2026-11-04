"""Format tasks for display; shared by the CLI and the TUI.

Plain strings only, no Textual, so the CLI's `show` and the TUI's detail view
show the same fields in the same way.
"""

from datetime import datetime, timedelta

from tskmngr.models import Task
from tskmngr.subtasks import parse_subtasks, progress


def task_fields(task: Task) -> list[tuple[str, str]]:
    """Every field of a task as `(label, value)`; missing values are `-`.

    Subtasks are shown as done and total, like `1/3`.
    """
    return [
        ("ID", task.id),
        ("Title", task.title),
        ("Status", task.status.value),
        ("Priority", task.priority.value),
        ("Due", task.due.isoformat() if task.due else "-"),
        ("Tags", ", ".join(task.tags) or "-"),
        ("Subtasks", progress(parse_subtasks(task.notes)) or "-"),
        ("Created", format_timestamp(task.created)),
        ("Updated", format_timestamp(task.updated)),
    ]


def format_timestamp(value: datetime) -> str:
    """ISO 8601 like in the task files, with UTC written as `Z`."""
    text = value.isoformat()
    if value.utcoffset() == timedelta(0):
        text = text.removesuffix("+00:00") + "Z"
    return text
