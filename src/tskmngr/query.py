"""Filter, search, sort and look up tasks. Shared by the CLI and the TUI.

Every function takes either `Task`s or `TaskFile`s (as returned by
`storage.load_tasks`) and returns the same kind, so callers keep what they
need for saving.
"""

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from enum import StrEnum

from tskmngr.models import Priority, Status, Task
from tskmngr.taskfile import TaskFile

PRIORITY_RANK = {Priority.LOW: 0, Priority.NORMAL: 1, Priority.HIGH: 2}


class SortKey(StrEnum):
    DUE = "due"
    PRIORITY = "priority"
    CREATED = "created"
    UPDATED = "updated"


class TaskNotFoundError(LookupError):
    """No task ID starts with the given prefix."""

    def __init__(self, prefix: str) -> None:
        super().__init__(f"no task with ID prefix {prefix!r}")
        self.prefix = prefix


class AmbiguousIDError(LookupError):
    """Several task IDs start with the given prefix and none equals it."""

    def __init__(self, prefix: str, ids: list[str]) -> None:
        super().__init__(
            f"ID prefix {prefix!r} matches {len(ids)} tasks: {', '.join(ids)}"
        )
        self.prefix = prefix
        self.ids = ids


@dataclass(frozen=True)
class TaskFilter:
    """The criteria of `filter_tasks`, as parsed from a filter string."""

    statuses: tuple[Status, ...] = ()
    priorities: tuple[Priority, ...] = ()
    tags: tuple[str, ...] = ()
    text: str = ""

    def apply[T: (Task, TaskFile)](self, items: Iterable[T]) -> list[T]:
        """`filter_tasks` with these criteria."""
        return filter_tasks(
            items,
            statuses=self.statuses,
            priorities=self.priorities,
            tags=self.tags,
            text=self.text,
        )


def parse_filter(text: str) -> tuple[TaskFilter, list[str]]:
    """Parse a filter string such as `milk #errands status:todo priority:high`.

    Words are split on whitespace. `#tag` requires a tag, `status:<status>`
    and `priority:<priority>` restrict to that value (repeat for any of
    several), ignoring case. Every other word, including other `key:value`
    words, is searched for in the title and notes.

    Returns the filter and a message for each word that was left out of it:
    an unknown or missing status or priority, or a bare `#`. The rest of the
    filter still applies, so a half-typed word doesn't empty the list.
    """
    statuses: list[Status] = []
    priorities: list[Priority] = []
    tags: list[str] = []
    words: list[str] = []
    errors: list[str] = []
    for word in text.split():
        key, colon, value = word.partition(":")
        if word.startswith("#"):
            if word == "#":
                errors.append("'#' needs a tag after it, as in #errands")
            else:
                tags.append(word[1:].lower())
        elif colon and key.lower() == "status":
            _parse_value(Status, "status", value, statuses, errors)
        elif colon and key.lower() == "priority":
            _parse_value(Priority, "priority", value, priorities, errors)
        else:
            words.append(word)
    task_filter = TaskFilter(
        statuses=tuple(dict.fromkeys(statuses)),
        priorities=tuple(dict.fromkeys(priorities)),
        tags=tuple(dict.fromkeys(tags)),
        text=" ".join(words),
    )
    return task_filter, errors


def _parse_value[E: (Status, Priority)](
    enum: type[E], name: str, value: str, values: list[E], errors: list[str]
) -> None:
    """Append `value` as an `enum` member to `values`, or a message to `errors`."""
    try:
        values.append(enum(value.lower()))
    except ValueError:
        choices = [member.value for member in enum]
        options = f"{', '.join(choices[:-1])} or {choices[-1]}"
        given = f"unknown {name} {value!r}" if value else f"{name}: needs a value"
        errors.append(f"{given}; use {options}")


def filter_tasks[T: (Task, TaskFile)](
    items: Iterable[T],
    *,
    statuses: Collection[Status] = (),
    priorities: Collection[Priority] = (),
    tags: Collection[str] = (),
    text: str = "",
) -> list[T]:
    """Return the tasks that match every given criterion, in their order.

    An empty criterion matches all tasks. A task matches if its status is one
    of `statuses`, its priority one of `priorities`, it has all of `tags` and
    every word of `text` appears in its title or notes. Tags and text ignore
    case.
    """
    wanted_tags = {tag.lower() for tag in tags}
    words = text.casefold().split()
    return [
        item
        for item in items
        if _matches(_task(item), statuses, priorities, wanted_tags, words)
    ]


def sort_tasks[T: (Task, TaskFile)](
    items: Iterable[T], key: SortKey, *, reverse: bool = False
) -> list[T]:
    """Return the tasks sorted by `key`.

    By default the due date is soonest first, priority highest first, and
    created and updated oldest first. `reverse` flips that, but tasks without
    a due date always come last. Ties are broken by created time, then ID.
    """
    ordered = sorted(items, key=lambda item: (_task(item).created, _task(item).id))
    if key is SortKey.DUE:
        dated = [item for item in ordered if _task(item).due is not None]
        undated = [item for item in ordered if _task(item).due is None]
        # sorted() is stable with reverse=True too, so ties keep their order.
        return (
            sorted(dated, key=lambda item: _task(item).due, reverse=reverse) + undated
        )
    if key is SortKey.PRIORITY:
        return sorted(
            ordered,
            key=lambda item: -PRIORITY_RANK[_task(item).priority],
            reverse=reverse,
        )
    return sorted(
        ordered, key=lambda item: getattr(_task(item), key.value), reverse=reverse
    )


def find_by_prefix[T: (Task, TaskFile)](items: Iterable[T], prefix: str) -> T:
    """Return the one task whose ID starts with `prefix`, ignoring case.

    An ID equal to `prefix` wins over longer IDs that start with it. Raises
    `TaskNotFoundError` if nothing matches, `AmbiguousIDError` if several
    tasks do, and `ValueError` for a blank prefix.
    """
    items = list(items)
    task_id = match_id_prefix([_task(item).id for item in items], prefix)
    # match_id_prefix raises if task_id isn't unique, so exactly one item has it.
    return next(item for item in items if _task(item).id == task_id)


def match_id_prefix(ids: Iterable[str], prefix: str) -> str:
    """Return the one ID in `ids` that starts with `prefix`, ignoring case.

    The same rules and errors as `find_by_prefix`, for callers that also look
    up IDs without a task, such as the files that failed to load.
    """
    if not prefix.strip():
        raise ValueError("ID prefix must not be blank")
    folded = prefix.casefold()
    matches = [task_id for task_id in ids if task_id.casefold().startswith(folded)]
    if not matches:
        raise TaskNotFoundError(prefix)
    if len(matches) == 1:
        return matches[0]
    # Hand-made filenames may differ only in case, so an exact match wins first.
    exact = [task_id for task_id in matches if task_id == prefix] or [
        task_id for task_id in matches if task_id.casefold() == folded
    ]
    if len(exact) == 1:
        return exact[0]
    raise AmbiguousIDError(prefix, sorted(matches))


def _task(item: Task | TaskFile) -> Task:
    return item.task if isinstance(item, TaskFile) else item


def _matches(
    task: Task,
    statuses: Collection[Status],
    priorities: Collection[Priority],
    tags: set[str],
    words: list[str],
) -> bool:
    if statuses and task.status not in statuses:
        return False
    if priorities and task.priority not in priorities:
        return False
    if not tags.issubset(task.tags):
        return False
    haystack = f"{task.title}\n{task.notes}".casefold()
    return all(word in haystack for word in words)
