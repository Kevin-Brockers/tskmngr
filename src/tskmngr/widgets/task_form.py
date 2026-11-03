"""The task form: create a task or edit the fields of one.

Title, status, priority, due date, tags and the notes, which are edited as
plain text in a text area. Input is checked on save and each problem is shown
under its field. A save that hits a conflict (the file changed or was deleted
on disk) is shown as an error and the form closes without saving, so the
caller reloads from disk. Cancelling a form with changes asks before
discarding them.

When the app notices task files changed on disk while a task is being edited,
the form isn't reloaded: what was typed stays. If the task's own file changed
or was deleted, the conflict is shown right away, before saving runs into it.
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
from textual.widgets import Footer, Header, Input, Label, Select, Static, TextArea

from tskmngr.models import (
    Priority,
    Status,
    Task,
    TaskValidationError,
    new_task,
    parse_due,
)
from tskmngr.storage import (
    ConflictError,
    check_unchanged,
    load_tasks,
    save_task,
    task_path,
)
from tskmngr.taskfile import TaskFile
from tskmngr.widgets.confirm_discard import ConfirmDiscardScreen
from tskmngr.widgets.tasks_changed import TasksChanged

FIELDS = ("title", "status", "priority", "due", "tags", "notes")

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


def tidy_notes(text: str, newline: str = "\n") -> str:
    """Notes as typed in the form, ready to save.

    Whitespace-only notes become no notes, and other notes end with `newline`,
    so the task file ends with a line break.
    """
    if not text.strip():
        return ""
    return text if text.endswith(("\r\n", "\n", "\r")) else text + newline


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
    TaskFormScreen #notes {
        height: 12;
    }
    """

    def __init__(self, directory: Path, source: TaskFile | None = None) -> None:
        super().__init__()
        self.directory = directory
        self.source = source
        # The fields as first shown, to tell whether anything was changed.
        self._initial_values: tuple[object, ...] = ()
        # Whether a conflict with the file on disk was already shown.
        self._conflict_shown = False

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
            yield Label("Notes", classes="field-label")
            yield TextArea(task.notes if task else "", id="notes")
        yield Footer()

    def _error(self, field: str) -> ComposeResult:
        yield Static(id=f"{field}-error", classes="field-error")

    def on_mount(self) -> None:
        if self.source is None:
            self.sub_title = "New task"
        else:
            self.sub_title = f"Edit {task_path(self.directory, self.source.task.id)}"
        self.query_one("#title", Input).focus()
        self._initial_values = self._field_values()

    def _field_values(self) -> tuple[object, ...]:
        """What the fields hold, as shown, before any checks."""
        return (
            self.query_one("#title", Input).value,
            self.query_one("#status", Select).value,
            self.query_one("#priority", Select).value,
            self.query_one("#due", Input).value,
            self.query_one("#tags", Input).value,
            self.query_one("#notes", TextArea).text,
        )

    def on_tasks_changed(self, message: TasksChanged) -> None:
        """Task files changed on disk: show a conflict with the edited task's.

        The fields are left as they are, and the conflict is shown once. Other
        files changing doesn't matter here.
        """
        if self.source is None or self._conflict_shown:
            return
        try:
            check_unchanged(self.directory, self.source)
        except ConflictError as error:
            self._conflict_shown = True
            self.notify(
                f"{error.path.name} {error.reason}. Your changes are kept here, "
                "but saving them will be refused so the file isn't overwritten.",
                title="Conflict",
                severity="warning",
                markup=False,
            )
        except OSError:
            # Can't tell now; saving checks again.
            pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Enter moves to the next field; in the notes it starts a new line.
        event.stop()
        self.focus_next()

    def action_cancel(self) -> None:
        """Close without saving, after asking if anything was changed."""
        if self._field_values() == self._initial_values:
            self.dismiss(None)
            return
        self.app.push_screen(
            ConfirmDiscardScreen(),
            lambda discard: self.dismiss(None) if discard else None,
        )

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
                notes=self._notes(),
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

    def _notes(self) -> str:
        """The notes to save: the task's own if untouched, else tidied.

        Untouched notes aren't taken from the text area, which would turn
        mixed line endings into one kind and so change the file.
        """
        notes = self.query_one("#notes", TextArea)
        if notes.text == self._initial_values[FIELDS.index("notes")]:
            return self.source.task.notes if self.source else ""
        return tidy_notes(notes.text, notes.document.newline)

    def _build(
        self,
        *,
        title: str,
        status: Status,
        priority: Priority,
        due: date | None,
        tags: list[str],
        notes: str,
    ) -> Task:
        if self.source is None:
            return new_task(
                title,
                existing_ids=load_tasks(self.directory).ids,
                status=status,
                priority=priority,
                due=due,
                tags=tags,
                notes=notes,
            )
        old = self.source.task
        task = replace(
            old,
            title=title,
            status=status,
            priority=priority,
            due=due,
            tags=tags,
            notes=notes,
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
