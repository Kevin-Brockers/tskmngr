"""The task detail screen: every field of one task, then its notes.

The notes are rendered as Markdown. The header shows the task's file, so it's
easy to find for editing by hand.
"""

from pathlib import Path
from typing import ClassVar

# Field values are built as `Text` so a title like "[b]old" is shown as
# written instead of read as markup.
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Markdown, Static

from tskmngr.display import task_fields
from tskmngr.models import Task
from tskmngr.taskfile import TaskFile


def fields_table(task: Task) -> Table:
    """The fields of a task in two columns, labels in bold."""
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold", no_wrap=True)
    table.add_column()
    for label, value in task_fields(task):
        table.add_row(Text(label), Text(value))
    return table


class TaskDetailScreen(Screen):
    """One task from `directory`: all its fields and its rendered notes."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Back", id="task_detail.close"),
    ]

    DEFAULT_CSS = """
    TaskDetailScreen #detail-body {
        height: 1fr;
        padding: 1 2;
    }
    TaskDetailScreen #fields {
        margin-bottom: 1;
    }
    TaskDetailScreen #no-notes {
        color: $text-muted;
    }
    """

    def __init__(self, directory: Path, source: TaskFile) -> None:
        super().__init__()
        self.directory = directory
        # The loaded file; later steps edit the task through it.
        self.source = source

    @property
    def path(self) -> Path:
        """The task's file."""
        return self.directory / f"{self.source.task.id}.md"

    def compose(self) -> ComposeResult:
        task = self.source.task
        has_notes = bool(task.notes.strip())
        yield Header()
        with VerticalScroll(id="detail-body"):
            yield Static(fields_table(task), id="fields")
            # Only one of the two is shown.
            notes = Markdown(task.notes, id="notes")
            notes.display = has_notes
            yield notes
            no_notes = Static(Text("No notes."), id="no-notes")
            no_notes.display = not has_notes
            yield no_notes
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = str(self.path)
        # Focused so the arrow and page keys scroll long notes.
        self.query_one("#detail-body").focus()

    def action_close(self) -> None:
        self.dismiss()
