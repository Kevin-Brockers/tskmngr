"""Filter, search, sort and look up tasks. Shared by the CLI and the TUI.

Every function takes either `Task`s or `TaskFile`s (as returned by
`storage.load_tasks`) and returns the same kind, so callers keep what they
need for saving.
"""

from collections.abc import Collection, Iterable
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
    if not prefix.strip():
        raise ValueError("ID prefix must not be blank")
    folded = prefix.casefold()
    matches = [item for item in items if _task(item).id.casefold().startswith(folded)]
    if not matches:
        raise TaskNotFoundError(prefix)
    if len(matches) == 1:
        return matches[0]
    # Hand-made filenames may differ only in case, so an exact match wins first.
    exact = [item for item in matches if _task(item).id == prefix] or [
        item for item in matches if _task(item).id.casefold() == folded
    ]
    if len(exact) == 1:
        return exact[0]
    raise AmbiguousIDError(prefix, sorted(_task(item).id for item in matches))


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
