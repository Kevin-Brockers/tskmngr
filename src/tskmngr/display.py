"""Format tasks for display; shared by the CLI and the TUI.

Plain strings only, no Textual, so the CLI's `show` and the TUI's detail view
show the same fields in the same way.
"""

from datetime import datetime, timedelta
from enum import StrEnum

from tskmngr.models import Task
from tskmngr.subtasks import parse_subtasks, progress


class Column(StrEnum):
    """A column of the TUI's task list, by the name the config file uses."""

    ID = "id"
    STATUS = "status"
    PRIORITY = "priority"
    DUE = "due"
    CREATED = "created"
    UPDATED = "updated"
    TITLE = "title"
    TAGS = "tags"


# The task list's columns when the config file doesn't set `columns`. Created
# and updated aren't among them; the list shows one only while sorting by it.
DEFAULT_COLUMNS: tuple[Column, ...] = (
    Column.ID,
    Column.STATUS,
    Column.PRIORITY,
    Column.DUE,
    Column.TITLE,
    Column.TAGS,
)


class TrashColumn(StrEnum):
    """A column of the TUI's deleted tasks view: a task list column, or when."""

    ID = "id"
    STATUS = "status"
    PRIORITY = "priority"
    DUE = "due"
    CREATED = "created"
    UPDATED = "updated"
    TITLE = "title"
    TAGS = "tags"
    # When the task was deleted.
    DELETED = "deleted"


DEFAULT_TRASH_COLUMNS: tuple[TrashColumn, ...] = (
    TrashColumn.TITLE,
    TrashColumn.TAGS,
    TrashColumn.DELETED,
    TrashColumn.ID,
)


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
        ("Repeat", format_repeat(task)),
        ("Tags", ", ".join(task.tags) or "-"),
        ("Subtasks", progress(parse_subtasks(task.notes)) or "-"),
        ("Created", format_timestamp(task.created)),
        ("Updated", format_timestamp(task.updated)),
    ]


def format_repeat(task: Task) -> str:
    """The repeat rule, with the date it counts from if it has one; else `-`."""
    if task.repeat is None:
        return "-"
    if task.repeat_from is None:
        return str(task.repeat)
    return f"{task.repeat} from {task.repeat_from.isoformat()}"


def format_next_occurrence(task: Task) -> str:
    """The line telling the user a task's next occurrence was added."""
    due = task.due.isoformat() if task.due else "-"
    return f"Next occurrence: {task.id}, due {due}"


def format_timestamp(value: datetime) -> str:
    """ISO 8601 like in the task files, with UTC written as `Z`."""
    text = value.isoformat()
    if value.utcoffset() == timedelta(0):
        text = text.removesuffix("+00:00") + "Z"
    return text


def task_cell(task: Task, column: Column, *, tags_in_title: bool = False) -> str:
    """A task's text in one of the task list's columns.

    The title is followed by `↻` if the task repeats, and its subtasks done
    and total, like `[1/3]`, if it has any; with `tags_in_title`, for a table
    without a tags column, then by its tags as `#tag`. The tags column lists
    them separated by commas.
    """
    match column:
        case Column.ID:
            return task.id
        case Column.STATUS:
            return task.status.value
        case Column.PRIORITY:
            return task.priority.value
        case Column.DUE:
            return task.due.isoformat() if task.due else ""
        case Column.CREATED:
            return format_timestamp(task.created)
        case Column.UPDATED:
            return format_timestamp(task.updated)
        case Column.TITLE:
            done = progress(parse_subtasks(task.notes))
            title = [
                task.title,
                *(["↻"] if task.repeat else []),
                *([f"[{done}]"] if done else []),
            ]
            tags = [f"#{tag}" for tag in task.tags] if tags_in_title else []
            return " ".join([*title, *tags])
        case Column.TAGS:
            return ", ".join(task.tags)
