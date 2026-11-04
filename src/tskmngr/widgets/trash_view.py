"""The deleted tasks view: the files in `.trash/`, newest delete first.

A read-only table below the task list (see `storage.load_trash`). It never
takes focus, so every key keeps acting on the task list; it scrolls with the
mouse. Files in `.trash/` that can't be loaded are named above the table, so
they're never hidden. Restoring a task stays moving its file back by hand.
"""

from collections.abc import Sequence
from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from tskmngr.display import (
    DEFAULT_TRASH_COLUMNS,
    Column,
    TrashColumn,
    format_timestamp,
    task_cell,
)
from tskmngr.storage import TRASH, BadFile, DeletedTask, load_trash

# The header of each column.
TRASH_COLUMN_LABELS = {
    TrashColumn.ID: "ID",
    TrashColumn.STATUS: "Status",
    TrashColumn.PRIORITY: "Priority",
    TrashColumn.DUE: "Due",
    TrashColumn.CREATED: "Created",
    TrashColumn.UPDATED: "Updated",
    TrashColumn.TITLE: "Title",
    TrashColumn.DELETED: "Deleted",
}


def trash_labels(
    columns: Sequence[TrashColumn] = DEFAULT_TRASH_COLUMNS,
) -> tuple[str, ...]:
    """The headers of `columns`."""
    return tuple(TRASH_COLUMN_LABELS[column] for column in columns)


def trash_row(
    entry: DeletedTask, columns: Sequence[TrashColumn] = DEFAULT_TRASH_COLUMNS
) -> tuple[Text, ...]:
    """The table cells for a deleted task, matching `trash_labels`.

    The delete time is written like `created` and `updated`; the other
    columns are as in the task list.
    """
    return tuple(
        Text(
            format_timestamp(entry.deleted)
            if column is TrashColumn.DELETED
            else task_cell(entry.task, Column(column.value))
        )
        for column in columns
    )


def bad_trash_warning(directory: Path, bad_files: Sequence[BadFile]) -> Text:
    """A warning naming each file in `.trash/` that couldn't be loaded, and why.

    Files are named relative to the tasks directory `directory`, like
    `.trash/<file>`.
    """
    count = len(bad_files)
    noun = "file" if count == 1 else "files"
    lines = [f"{count} {noun} in {TRASH}/ couldn't be loaded:"]
    lines += [
        f"  {bad.path.relative_to(directory)}: {bad.error}"
        if bad.path.is_relative_to(directory)
        else f"  {bad.path}: {bad.error}"
        for bad in bad_files
    ]
    return Text("\n".join(lines))


class TrashTable(DataTable[Text]):
    """The table of deleted tasks; never focused, so keys reach the task list."""

    can_focus = False


class TrashView(Vertical):
    """The deleted tasks of the tasks directory `directory`, newest first."""

    DEFAULT_CSS = """
    TrashView {
        border: round $panel;
        border-title-color: $text-muted;
    }
    TrashView #trash-warning {
        display: none;
        color: $text-warning;
        max-height: 50%;
        overflow-y: auto;
    }
    TrashView #trash-warning.-shown {
        display: block;
    }
    TrashView #trash-table {
        height: 1fr;
    }
    TrashView #no-deleted-tasks {
        display: none;
        color: $text-muted;
    }
    TrashView #no-deleted-tasks.-shown {
        display: block;
    }
    """

    def __init__(
        self,
        directory: Path,
        *,
        columns: Sequence[TrashColumn] = DEFAULT_TRASH_COLUMNS,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self.directory = directory
        self.columns = tuple(columns)
        self.border_title = "Deleted tasks"
        # The deleted tasks shown, in table order.
        self.deleted: list[DeletedTask] = []
        self.bad_files: list[BadFile] = []

    def compose(self) -> ComposeResult:
        yield Static(id="trash-warning")
        table = TrashTable(id="trash-table", cursor_type="none")
        table.add_columns(*trash_labels(self.columns))
        yield table
        yield Static(Text("No deleted tasks."), id="no-deleted-tasks")

    def on_mount(self) -> None:
        self.load()

    def load(self) -> None:
        """(Re)load the deleted tasks from disk and show them."""
        warning = self.query_one("#trash-warning", Static)
        failed = False
        try:
            result = load_trash(self.directory)
        except OSError as error:
            failed = True
            self.deleted, self.bad_files = [], []
            reason = error.strerror or str(error)
            warning.update(
                Text(
                    f"Can't read the deleted tasks in {self.directory / TRASH}: {reason}"
                )
            )
            warning.set_class(True, "-shown")
        else:
            self.deleted, self.bad_files = result.deleted, result.bad_files
            if self.bad_files:
                warning.update(bad_trash_warning(self.directory, self.bad_files))
            warning.set_class(bool(self.bad_files), "-shown")
        table = self.query_one("#trash-table", TrashTable)
        # Rows only, so a reload keeps the scroll position.
        table.clear()
        for entry in self.deleted:
            table.add_row(*trash_row(entry, self.columns), key=entry.path.name)
        self.query_one("#no-deleted-tasks", Static).set_class(
            not self.deleted and not failed, "-shown"
        )
