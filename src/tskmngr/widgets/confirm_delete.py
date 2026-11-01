"""A dialog asking whether to delete a task.

It names the task and says where its file goes. Dismissed with True for yes
and False for no; No has the focus, so Enter alone doesn't delete.
"""

from typing import ClassVar

# The question is built as `Text` so a title like "[b]old" is shown as written
# instead of read as markup.
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from tskmngr.models import Task
from tskmngr.storage import TRASH


def delete_question(task: Task) -> Text:
    return Text(
        f"Delete task {task.id} {task.title!r}?\n"
        f"Its file is moved to {TRASH}/ in the tasks directory."
    )


class ConfirmDeleteScreen(ModalScreen[bool]):
    """Ask whether to delete `task`."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("y", "answer(True)", "Yes", id="confirm_delete.yes"),
        Binding("n,escape", "answer(False)", "No", id="confirm_delete.no"),
    ]

    DEFAULT_CSS = """
    ConfirmDeleteScreen {
        align: center middle;
    }
    ConfirmDeleteScreen #dialog {
        width: auto;
        max-width: 90%;
        height: auto;
        border: thick $error;
        background: $surface;
        padding: 1 2;
    }
    ConfirmDeleteScreen #question {
        width: auto;
        margin-bottom: 1;
    }
    ConfirmDeleteScreen #buttons {
        width: auto;
        height: auto;
    }
    ConfirmDeleteScreen Button {
        margin-right: 2;
    }
    """

    def __init__(self, task: Task) -> None:
        super().__init__()
        self.task_to_delete = task

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(delete_question(self.task_to_delete), id="question")
            with Horizontal(id="buttons"):
                yield Button("Yes, delete", variant="error", id="yes")
                yield Button("No", id="no")

    def on_mount(self) -> None:
        self.query_one("#no", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(event.button.id == "yes")

    def action_answer(self, yes: bool) -> None:
        self.dismiss(yes)
