"""Subtasks: the Markdown checklist items in a task's notes.

A subtask is a task-list line such as `- [ ] Book hotel` or `1. [x] Pack`, at
any indent, outside fenced code blocks. There's no separate storage: the
notes are the source of truth, and toggling a subtask flips the one character
between its brackets, leaving the rest of the notes as written.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from tskmngr.models import Status, Task

# A list marker (-, *, + or 1. / 1)), then [ ], [x] or [X], then the text.
_ITEM = re.compile(
    r"(?P<indent>[ \t]*)(?:[-*+]|[0-9]{1,9}[.)])[ \t]+"
    r"\[(?P<mark>[ xX])\][ \t]+(?P<title>\S.*?)[ \t]*"
)

# A fence opens with three or more backticks or tildes.
_FENCE = re.compile(r"[ \t]*(?P<fence>`{3,}|~{3,})")

# Each line with its line ending, which may be \n, \r\n or \r.
_LINE = re.compile(r"[^\r\n]*(?:\r\n|\r|\n)?")


@dataclass(frozen=True)
class Subtask:
    """One checklist item. `mark` is the index of its `[ ]`/`[x]` character
    in the notes; `indent` is its indent in columns (tabs count as 4)."""

    title: str
    done: bool
    indent: int
    mark: int


def parse_subtasks(notes: str) -> tuple[Subtask, ...]:
    """The checklist items in `notes`, in order."""
    subtasks: list[Subtask] = []
    fence: str | None = None
    offset = 0
    for match in _LINE.finditer(notes):
        line = match.group().rstrip("\r\n")
        start = offset
        offset = match.end()
        if not match.group():
            break
        opening = _FENCE.match(line)
        if fence is not None:
            # Closed by the same character, at least as many, nothing after.
            if opening and _closes(fence, line, opening):
                fence = None
            continue
        if opening:
            fence = opening.group("fence")
            continue
        item = _ITEM.fullmatch(line)
        if item:
            subtasks.append(
                Subtask(
                    title=item.group("title"),
                    done=item.group("mark") != " ",
                    indent=len(item.group("indent").expandtabs(4)),
                    mark=start + item.start("mark"),
                )
            )
    return tuple(subtasks)


def _closes(fence: str, line: str, match: re.Match[str]) -> bool:
    """Whether `line`, starting with fence `match`, closes the open `fence`."""
    candidate = match.group("fence")
    return (
        candidate[0] == fence[0]
        and len(candidate) >= len(fence)
        and not line[match.end() :].strip()
    )


def progress(subtasks: Sequence[Subtask]) -> str:
    """Done and total, like `1/3`; empty without subtasks."""
    if not subtasks:
        return ""
    return f"{sum(subtask.done for subtask in subtasks)}/{len(subtasks)}"


def uncheck_all(notes: str) -> str:
    """`notes` with every checked subtask unchecked, the rest as written."""
    marks = {subtask.mark for subtask in parse_subtasks(notes) if subtask.done}
    return "".join(" " if index in marks else char for index, char in enumerate(notes))


def toggle_subtask(task: Task, index: int, now: datetime) -> Task:
    """`task` with subtask `index` checked or unchecked and `updated` set to `now`.

    Checking the last open subtask marks the task done, and unchecking one of
    a done task moves it back to doing. Raises `IndexError` for a subtask that
    doesn't exist.
    """
    subtasks = parse_subtasks(task.notes)
    if not 0 <= index < len(subtasks):
        raise IndexError(f"no subtask {index}; the task has {len(subtasks)}")
    subtask = subtasks[index]
    mark = " " if subtask.done else "x"
    notes = task.notes[: subtask.mark] + mark + task.notes[subtask.mark + 1 :]
    all_done = all(s.done for s in parse_subtasks(notes))
    status = task.status
    if all_done:
        status = Status.DONE
    elif status is Status.DONE:
        status = Status.DOING
    return replace(task, notes=notes, status=status, updated=now)
