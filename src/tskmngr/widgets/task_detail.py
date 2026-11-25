"""The task detail screen: every field of one task, its subtasks, then its notes.

The subtasks, the checklist items in the notes (see `tskmngr.subtasks`), are
listed above the notes; Space, Enter or a click checks or unchecks the one
under the cursor and saves the task right away. Checking the last open one
marks the task done, unchecking one of a done task moves it back to doing; a
repeating task marked done this way gets its next occurrence. A
save that hits a conflict is shown, and the task reloaded, instead of
overwriting the file.

The notes are rendered as Markdown, checklist items included. The header shows the task's file, so it's
easy to find for editing by hand. `e` edits the task in the form and `o` opens
its file in the editor (the config's `editor`); afterwards it is reloaded
from disk. It's also reloaded when the app notices task files changed on disk.
"""

from datetime import UTC, datetime
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
from textual.widgets import Footer, Header, Markdown, OptionList, Static

from tskmngr.display import task_fields
from tskmngr.models import Status, Task
from tskmngr.recurrence import RecurrenceError
from tskmngr.storage import ConflictError, load_tasks, task_path
from tskmngr.subtasks import Subtask, parse_subtasks, toggle_subtask
from tskmngr.taskfile import TaskFile
from tskmngr.widgets.external_editor import edit_in_editor
from tskmngr.widgets.saving import notify_next, save_task_and_next
from tskmngr.widgets.syncing import record_change
from tskmngr.widgets.task_form import TaskFormScreen
from tskmngr.widgets.tasks_changed import TasksChanged


def fields_table(task: Task) -> Table:
    """The fields of a task in two columns, labels in bold."""
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold", no_wrap=True)
    table.add_column()
    for label, value in task_fields(task):
        table.add_row(Text(label), Text(value))
    return table


def subtask_prompt(subtask: Subtask) -> Text:
    """A subtask as a checklist line, indented like in the notes."""
    mark = "[x]" if subtask.done else "[ ]"
    return Text(f"{' ' * subtask.indent}{mark} {subtask.title}")


class TaskDetailScreen(Screen):
    """One task from `directory`: all its fields and its rendered notes."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Back", id="task_detail.close"),
        Binding("e", "edit", "Edit", id="task_detail.edit"),
        Binding("o", "external_editor", "Editor", id="task_detail.external_editor"),
        Binding("space", "toggle_subtask", "Check", id="task_detail.toggle_subtask"),
    ]

    DEFAULT_CSS = """
    TaskDetailScreen #detail-body {
        height: 1fr;
        padding: 1 2;
    }
    TaskDetailScreen #fields {
        margin-bottom: 1;
    }
    TaskDetailScreen #subtasks-label {
        text-style: bold;
    }
    TaskDetailScreen #subtasks {
        height: auto;
        margin-bottom: 1;
    }
    TaskDetailScreen #no-notes {
        color: $text-muted;
    }
    """

    def __init__(self, directory: Path, source: TaskFile) -> None:
        super().__init__()
        self.directory = directory
        # The loaded file; the task is edited through it.
        self.source = source
        # Task files changed on disk while another screen was on top.
        self._stale = False

    @property
    def path(self) -> Path:
        """The task's file."""
        return task_path(self.directory, self.source.task.id)

    def compose(self) -> ComposeResult:
        task = self.source.task
        has_notes = bool(task.notes.strip())
        subtasks = parse_subtasks(task.notes)
        yield Header()
        with VerticalScroll(id="detail-body"):
            yield Static(fields_table(task), id="fields")
            label = Static(Text("Subtasks"), id="subtasks-label")
            label.display = bool(subtasks)
            yield label
            checklist = OptionList(*map(subtask_prompt, subtasks), id="subtasks")
            checklist.display = bool(subtasks)
            yield checklist
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
        checklist = self.query_one("#subtasks", OptionList)
        if checklist.display:
            checklist.focus()
        else:
            # Focused so the arrow and page keys scroll long notes.
            self.query_one("#detail-body").focus()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool:
        if action == "toggle_subtask":
            # Only shown in the footer, and only works, in the checklist.
            return self.focused is self.query_one("#subtasks", OptionList)
        return True

    def action_close(self) -> None:
        self.dismiss()

    def action_edit(self) -> None:
        self.app.push_screen(
            TaskFormScreen(self.directory, self.source), self._form_closed
        )

    async def action_toggle_subtask(self) -> None:
        index = self.query_one("#subtasks", OptionList).highlighted
        if index is not None:
            await self._toggle(index)

    async def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        # Enter or a click on a subtask.
        event.stop()
        await self._toggle(event.option_index)

    async def _toggle(self, index: int) -> None:
        """Check or uncheck subtask `index`, save the task and reload it."""
        old = self.source.task
        task = toggle_subtask(old, index, datetime.now(UTC).replace(microsecond=0))
        try:
            following = save_task_and_next(self.directory, task, self.source)
        except ConflictError as error:
            self._notify_error(
                f"{error.path.name} {error.reason}. It was reloaded from disk; "
                "the subtask wasn't changed."
            )
        except RecurrenceError as error:
            self._notify_error(
                f"Can't add the next occurrence: {error}. The subtask wasn't changed."
            )
        except OSError as error:
            self._notify_error(
                f"Can't save the task in {self.directory}: {error.strerror or error}"
            )
        else:
            done = task.status is Status.DONE and old.status is not Status.DONE
            record_change(self, "done" if done else "edit", task.id, task.title)
            if task.status is not old.status:
                reason = (
                    "All subtasks are done"
                    if task.status is Status.DONE
                    else "A subtask is open again"
                )
                self.notify(
                    f"{reason}, so the task is now {task.status.value}.",
                    title="Status changed",
                    markup=False,
                )
            notify_next(self, following)
        await self.reload()

    def _notify_error(self, message: str) -> None:
        self.notify(message, title="Not saved", severity="error", markup=False)

    async def action_external_editor(self) -> None:
        """Open the task's file in the user's editor, then reload it."""
        edit_in_editor(self.app, self.path)
        await self.reload()
        task = self.source.task
        record_change(self, "edit", task.id, task.title)

    async def on_tasks_changed(self, message: TasksChanged) -> None:
        """Task files changed on disk: reload the task, if it's on top.

        Under another screen (the form), it reloads once it's back on top,
        since a task that's gone closes this screen.
        """
        # Not `is_current`, which is also true for a screen drawn behind another.
        if self.app.screen is self:
            await self.reload()
        else:
            self._stale = True

    async def on_screen_resume(self) -> None:
        if self._stale:
            await self.reload()

    async def _form_closed(self, task_id: str | None) -> None:
        # None means cancelled: nothing was saved, so there's nothing to reload.
        if task_id is not None:
            await self.reload()

    async def reload(self) -> None:
        """Reload the task from disk and show it again.

        If it can't be loaded anymore, that's reported and the screen closes,
        back to the list, which reloads too.
        """
        self._stale = False
        name = self.path.name
        try:
            result = load_tasks(self.directory)
        except OSError as error:
            self._close_with_error(
                f"Can't read the tasks in {self.directory}: {error.strerror or error}"
            )
            return
        task_id = self.source.task.id
        source = next((s for s in result.tasks if s.task.id == task_id), None)
        if source is None:
            bad = next((b for b in result.bad_files if b.path.stem == task_id), None)
            self._close_with_error(
                f"Can't load {name}: {bad.error}" if bad else f"{name} is gone."
            )
            return
        if source == self.source:
            # Unchanged: showing it again would only reset the notes.
            return
        self.source = source
        await self._show()

    async def _show(self) -> None:
        task = self.source.task
        has_notes = bool(task.notes.strip())
        self.query_one("#fields", Static).update(fields_table(task))
        self._show_subtasks(parse_subtasks(task.notes))
        notes = self.query_one("#notes", Markdown)
        await notes.update(task.notes)
        notes.display = has_notes
        self.query_one("#no-notes").display = not has_notes

    def _show_subtasks(self, subtasks: tuple[Subtask, ...]) -> None:
        """Show `subtasks`, keeping the cursor on the same row if it's there."""
        checklist = self.query_one("#subtasks", OptionList)
        highlighted = checklist.highlighted
        had_focus = self.focused is checklist
        checklist.clear_options()
        checklist.add_options(map(subtask_prompt, subtasks))
        if subtasks and highlighted is not None:
            checklist.highlighted = min(highlighted, len(subtasks) - 1)
        checklist.display = bool(subtasks)
        self.query_one("#subtasks-label").display = bool(subtasks)
        if had_focus and not subtasks:
            self.query_one("#detail-body").focus()

    def _close_with_error(self, message: str) -> None:
        self.notify(message, title="Task not shown", severity="error", markup=False)
        self.dismiss()
