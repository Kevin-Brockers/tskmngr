"""The task form: create a task or edit the fields of one.

Title, status, priority, due date and tags; the notes are left as they are.
Input is checked on save and each problem is shown under its field. A save
that hits a conflict (the file changed or was deleted on disk) is shown as an
error and the form closes without saving, so the caller reloads from disk.
"""

import re
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import ClassVar

# Errors are shown as `Text` so a value like "[b]" is shown as written instead
# of read as markup.
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Label, Select, Static

from tskmngr.models import (
    Priority,
    Status,
    Task,
    TaskValidationError,
    new_task,
    parse_due,
)
from tskmngr.storage import ConflictError, load_tasks, save_task, task_path
from tskmngr.taskfile import TaskFile

FIELDS = ("title", "status", "priority", "due", "tags")

TAG_SEPARATORS = re.compile(r"[\s,]+")


def parse_tags(text: str) -> list[str]:
    """Split tags separated by spaces and/or commas; duplicates are merged.

    Tags are lowercased, like the model does, so `Home home` is one tag.
    """
    tags = (tag.lower() for tag in TAG_SEPARATORS.split(text) if tag)
    return list(dict.fromkeys(tags))


def format_tags(tags: tuple[str, ...]) -> str:
    """Tags as the form shows them, for `parse_tags` to read back."""
    return ", ".join(tags)


class TaskFormScreen(Screen[str | None]):
    """Create a task in `directory` (`source` None) or edit `source`'s task.

    Dismissed with the ID of the task the caller should show after reloading
    from disk: the saved task, or the one whose save hit a conflict. Dismissed
    with None when cancelled, since nothing changed.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+s", "save", "Save", id="task_form.save"),
        Binding("escape", "cancel", "Cancel", id="task_form.cancel"),
    ]

    DEFAULT_CSS = """
    TaskFormScreen #form-body {
        height: 1fr;
        padding: 1 2;
    }
    TaskFormScreen .field-label {
        margin-top: 1;
        text-style: bold;
    }
    TaskFormScreen .field-error {
        display: none;
        color: $text-error;
    }
    TaskFormScreen .field-error.-shown {
        display: block;
    }
    """

    def __init__(self, directory: Path, source: TaskFile | None = None) -> None:
        super().__init__()
        self.directory = directory
        self.source = source

    def compose(self) -> ComposeResult:
        task = self.source.task if self.source else None
        yield Header()
        with VerticalScroll(id="form-body"):
            yield Label("Title", classes="field-label")
            yield Input(task.title if task else "", id="title")
            yield from self._error("title")
            yield Label("Status", classes="field-label")
            yield Select(
                [(status.value, status) for status in Status],
                value=task.status if task else Status.TODO,
                allow_blank=False,
                id="status",
            )
            yield Label("Priority", classes="field-label")
            yield Select(
                [(priority.value, priority) for priority in Priority],
                value=task.priority if task else Priority.NORMAL,
                allow_blank=False,
                id="priority",
            )
            yield Label("Due date", classes="field-label")
            due = task.due.isoformat() if task and task.due else ""
            yield Input(due, placeholder="YYYY-MM-DD, empty for none", id="due")
            yield from self._error("due")
            yield Label("Tags", classes="field-label")
            tags = format_tags(task.tags) if task else ""
            yield Input(tags, placeholder="separated by spaces or commas", id="tags")
            yield from self._error("tags")
        yield Footer()

    def _error(self, field: str) -> ComposeResult:
        yield Static(id=f"{field}-error", classes="field-error")

    def on_mount(self) -> None:
        if self.source is None:
            self.sub_title = "New task"
        else:
            self.sub_title = f"Edit {task_path(self.directory, self.source.task.id)}"
        self.query_one("#title", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Enter moves to the next field, and saves from the last one.
        event.stop()
        if event.input.id == FIELDS[-1]:
            self.action_save()
        else:
            self.focus_next()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_save(self) -> None:
        task = self._task_from_fields()
        if task is None:
            return
        if self.source is not None and task == self.source.task:
            self.dismiss(task.id)
            return
        try:
            save_task(self.directory, task, self.source)
        except ConflictError as error:
            self.notify(
                f"{error.path.name} {error.reason}. It was reloaded from disk; "
                "your changes weren't saved.",
                title="Not saved",
                severity="error",
                markup=False,
            )
            self.dismiss(task.id)
            return
        except OSError as error:
            # Not a conflict, so the form stays open and the user can retry.
            self.notify(
                f"Can't save the task in {self.directory}: {error.strerror or error}",
                title="Not saved",
                severity="error",
                markup=False,
            )
            return
        self.dismiss(task.id)

    def _task_from_fields(self) -> Task | None:
        """The task as filled in, or None after showing what's wrong.

        An edited task that differs from `source`'s gets `updated` set to now.
        """
        errors: dict[str, str] = {}
        due_text = self.query_one("#due", Input).value.strip()
        due = None
        if due_text:
            try:
                due = parse_due(due_text)
            except TaskValidationError as error:
                errors["due"] = error.message
        task = None
        try:
            # Built even with a bad due date, so a bad title shows up too.
            task = self._build(
                title=self.query_one("#title", Input).value,
                status=self.query_one("#status", Select).value,
                priority=self.query_one("#priority", Select).value,
                due=due,
                tags=parse_tags(self.query_one("#tags", Input).value),
            )
        except TaskValidationError as error:
            errors.setdefault(error.field, error.message)
        except OSError as error:
            # Reading the existing IDs for a new task failed.
            self._show_errors(errors)
            self.notify(
                f"Can't read the tasks in {self.directory}: {error.strerror or error}",
                title="Not saved",
                severity="error",
                markup=False,
            )
            return None
        self._show_errors(errors)
        return None if errors else task

    def _build(
        self,
        *,
        title: str,
        status: Status,
        priority: Priority,
        due: date | None,
        tags: list[str],
    ) -> Task:
        if self.source is None:
            return new_task(
                title,
                existing_ids=load_tasks(self.directory).ids,
                status=status,
                priority=priority,
                due=due,
                tags=tags,
            )
        old = self.source.task
        task = replace(
            old, title=title, status=status, priority=priority, due=due, tags=tags
        )
        if task == old:
            return task
        return replace(task, updated=datetime.now(UTC).replace(microsecond=0))

    def _show_errors(self, errors: dict[str, str]) -> None:
        for field in ("title", "due", "tags"):
            message = errors.get(field, "")
            error = self.query_one(f"#{field}-error", Static)
            error.update(Text(message[:1].upper() + message[1:]))
            error.set_class(bool(message), "-shown")
        for field in FIELDS:
            if field in errors:
                self.query_one(f"#{field}").focus()
                break
