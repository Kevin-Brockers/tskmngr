"""The task list screen: every task in a table, soonest due first.

Task files that can't be loaded are named in a warning panel above the table,
so they're never hidden. The tasks directory is shown in the header. Enter
opens the task under the cursor in the detail screen, `n` creates a task and
`e` edits the one under the cursor. `s` moves the task under the cursor to the
next status (todo → doing → done → todo) and saves it right away; `d` asks
whether to delete it and moves its file to `.trash/`; `o` opens its file in
`$VISUAL` or `$EDITOR`. The list is reloaded from disk after each of these, and
a save or delete that hits a conflict is shown instead of overwriting the file.
"""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

# Cells and the warning are built as `Text` so a title like "[b]old" is shown
# as written instead of read as markup.
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from tskmngr.models import Task, next_status
from tskmngr.query import SortKey, sort_tasks
from tskmngr.storage import (
    BadFile,
    ConflictError,
    delete_task,
    load_tasks,
    save_task,
    task_path,
)
from tskmngr.taskfile import TaskFile
from tskmngr.widgets.confirm_delete import ConfirmDeleteScreen
from tskmngr.widgets.external_editor import edit_in_editor
from tskmngr.widgets.task_detail import TaskDetailScreen
from tskmngr.widgets.task_form import TaskFormScreen

COLUMNS = ("ID", "Status", "Priority", "Due", "Title")


def task_row(task: Task) -> tuple[Text, ...]:
    """The table cells for a task; tags follow the title as `#tag`."""
    title = " ".join([task.title, *(f"#{tag}" for tag in task.tags)])
    return tuple(
        Text(cell)
        for cell in (
            task.id,
            task.status.value,
            task.priority.value,
            task.due.isoformat() if task.due else "",
            title,
        )
    )


def bad_files_warning(directory: Path, bad_files: Sequence[BadFile]) -> Text:
    """A warning naming each task file that couldn't be loaded, and why.

    Files are named relative to `directory`, which the header already shows;
    a file outside it keeps its full path.
    """
    count = len(bad_files)
    noun = "task file" if count == 1 else "task files"
    lines = [f"{count} {noun} couldn't be loaded:"]
    lines += [
        f"  {_display_path(directory, bad.path)}: {bad.error}" for bad in bad_files
    ]
    return Text("\n".join(lines))


def _display_path(directory: Path, path: Path) -> Path:
    return path.relative_to(directory) if path.is_relative_to(directory) else path


class TaskListScreen(Screen):
    """All tasks in `directory`, done ones included, soonest due first."""

    BINDINGS: ClassVar[list[BindingType]] = [
        # Priority, so Enter reaches the screen before the focused table.
        Binding("enter", "open_task", "Open", id="task_list.open", priority=True),
        Binding("n", "new_task", "New", id="task_list.new"),
        Binding("e", "edit_task", "Edit", id="task_list.edit"),
        Binding("s", "cycle_status", "Status", id="task_list.cycle_status"),
        Binding("d", "delete_task", "Delete", id="task_list.delete"),
        Binding("o", "external_editor", "Editor", id="task_list.external_editor"),
    ]

    DEFAULT_CSS = """
    TaskListScreen #load-warning {
        display: none;
        border: round $warning;
        color: $text-warning;
        padding: 0 1;
        max-height: 50%;
        overflow-y: auto;
    }
    TaskListScreen #load-warning.-shown {
        display: block;
    }
    TaskListScreen #task-table {
        height: 1fr;
    }
    TaskListScreen #no-tasks {
        display: none;
        padding: 1 2;
        color: $text-muted;
    }
    TaskListScreen #no-tasks.-shown {
        display: block;
    }
    """

    def __init__(self, directory: Path) -> None:
        super().__init__()
        self.directory = directory
        # The loaded files, in table order; later steps save edits through them.
        self.tasks: list[TaskFile] = []
        self.bad_files: list[BadFile] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="load-warning")
        table: DataTable[Text] = DataTable(id="task-table", cursor_type="row")
        table.add_columns(*COLUMNS)
        yield table
        yield Static(Text("No tasks."), id="no-tasks")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = str(self.directory)
        self.load()

    def load(self) -> None:
        """(Re)load the tasks from disk and show them."""
        warning = self.query_one("#load-warning", Static)
        try:
            result = load_tasks(self.directory)
        except OSError as error:
            self.tasks, self.bad_files = [], []
            reason = error.strerror or str(error)
            warning.update(Text(f"Can't read the tasks in {self.directory}: {reason}"))
            warning.set_class(True, "-shown")
            self._show_tasks()
            return
        self.tasks = sort_tasks(result.tasks, SortKey.DUE)
        self.bad_files = result.bad_files
        if self.bad_files:
            warning.update(bad_files_warning(self.directory, self.bad_files))
        warning.set_class(bool(self.bad_files), "-shown")
        self._show_tasks()

    def _show_tasks(self) -> None:
        table = self.query_one("#task-table", DataTable)
        table.clear()
        for source in self.tasks:
            table.add_row(*task_row(source.task), key=source.task.id)
        self.query_one("#no-tasks").set_class(not self.tasks, "-shown")

    def reload(self, task_id: str | None) -> None:
        """Reload from disk, keeping the cursor on `task_id` if it's still there."""
        self.load()
        if task_id is None:
            return
        for row, source in enumerate(self.tasks):
            if source.task.id == task_id:
                self.query_one("#task-table", DataTable).move_cursor(row=row)
                return

    def _current(self) -> TaskFile | None:
        """The task under the cursor, if there are any tasks."""
        if not self.tasks:
            return None
        return self.tasks[self.query_one("#task-table", DataTable).cursor_row]

    def action_open_task(self) -> None:
        """Show the task under the cursor in the detail screen."""
        source = self._current()
        if source is None:
            return
        task_id = source.task.id
        self.app.push_screen(
            TaskDetailScreen(self.directory, source),
            # It may have been edited from there.
            lambda _: self.reload(task_id),
        )

    def action_new_task(self) -> None:
        self.app.push_screen(TaskFormScreen(self.directory), self._form_closed)

    def action_edit_task(self) -> None:
        """Edit the task under the cursor in the form."""
        source = self._current()
        if source is None:
            return
        self.app.push_screen(TaskFormScreen(self.directory, source), self._form_closed)

    def _form_closed(self, task_id: str | None) -> None:
        # None means cancelled: nothing was saved, so there's nothing to reload.
        if task_id is not None:
            self.reload(task_id)

    def action_cycle_status(self) -> None:
        """Save the task under the cursor with the next status."""
        source = self._current()
        if source is None:
            return
        task = replace(
            source.task,
            status=next_status(source.task.status),
            updated=datetime.now(UTC).replace(microsecond=0),
        )
        try:
            save_task(self.directory, task, source)
        except ConflictError as error:
            self._notify_error(
                f"{error.path.name} {error.reason}. It was reloaded from disk; "
                "the status wasn't changed.",
                "Not saved",
            )
        except OSError as error:
            self._notify_error(
                f"Can't save the task in {self.directory}: {error.strerror or error}",
                "Not saved",
            )
        self.reload(task.id)

    def action_delete_task(self) -> None:
        """Ask whether to delete the task under the cursor, then delete it."""
        source = self._current()
        if source is None:
            return
        self.app.push_screen(
            ConfirmDeleteScreen(source.task),
            lambda yes: self._delete(source) if yes else None,
        )

    def _delete(self, source: TaskFile) -> None:
        task_id = source.task.id
        # Where the cursor goes afterwards: the next task, or else the previous.
        ids = [s.task.id for s in self.tasks]
        row = ids.index(task_id) if task_id in ids else 0
        neighbours = ids[row + 1 :] + ids[:row][::-1]
        try:
            trashed = delete_task(self.directory, source)
        except ConflictError as error:
            self._notify_error(
                f"{error.path.name} {error.reason}. It was reloaded from disk; "
                "nothing was deleted.",
                "Not deleted",
            )
            self.reload(task_id)
            return
        except OSError as error:
            self._notify_error(
                f"Can't delete the task in {self.directory}: {error.strerror or error}",
                "Not deleted",
            )
            self.reload(task_id)
            return
        self.notify(
            f"Moved {task_id} to {_display_path(self.directory, trashed)}",
            title="Deleted",
            markup=False,
        )
        self.reload(neighbours[0] if neighbours else None)

    def action_external_editor(self) -> None:
        """Open the file of the task under the cursor in the user's editor."""
        source = self._current()
        if source is None:
            return
        task_id = source.task.id
        edit_in_editor(self.app, task_path(self.directory, task_id))
        self.reload(task_id)

    def _notify_error(self, message: str, title: str) -> None:
        self.notify(message, title=title, severity="error", markup=False)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        # Clicking a row selects it; Enter is handled by the binding.
        event.stop()
        self.action_open_task()
