"""A dialog asking whether to discard the unsaved changes in the task form.

Dismissed with True to discard and False to keep editing; No has the focus, so
Enter alone doesn't discard, and Escape keeps editing too.
"""

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

QUESTION = "Discard your unsaved changes?"


class ConfirmDiscardScreen(ModalScreen[bool]):
    """Ask whether to discard the form's unsaved changes."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("y", "answer(True)", "Yes", id="confirm_discard.yes"),
        Binding("n,escape", "answer(False)", "No", id="confirm_discard.no"),
    ]

    DEFAULT_CSS = """
    ConfirmDiscardScreen {
        align: center middle;
    }
    ConfirmDiscardScreen #dialog {
        width: auto;
        max-width: 90%;
        height: auto;
        border: thick $warning;
        background: $surface;
        padding: 1 2;
    }
    ConfirmDiscardScreen #question {
        width: auto;
        margin-bottom: 1;
    }
    ConfirmDiscardScreen #buttons {
        width: auto;
        height: auto;
    }
    ConfirmDiscardScreen Button {
        margin-right: 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(Text(QUESTION), id="question")
            with Horizontal(id="buttons"):
                yield Button("Yes, discard", variant="warning", id="yes")
                yield Button("No, keep editing", id="no")

    def on_mount(self) -> None:
        self.query_one("#no", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(event.button.id == "yes")

    def action_answer(self, yes: bool) -> None:
        self.dismiss(yes)
