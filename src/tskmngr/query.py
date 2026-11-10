"""Filter, search, sort and look up tasks. Shared by the CLI and the TUI.

Every function takes either `Task`s or `TaskFile`s (as returned by
`storage.load_tasks`) and returns the same kind, so callers keep what they
need for saving.
"""

import re
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from enum import StrEnum

from tskmngr.models import Priority, Status, Task
from tskmngr.taskfile import TaskFile

PRIORITY_RANK = {Priority.LOW: 0, Priority.NORMAL: 1, Priority.HIGH: 2}

# The words of a title or notes, for typo matches: runs of letters and digits.
_WORD = re.compile(r"[^\W_]+")


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

    Words are split on whitespace. `#tag` requires a tag that starts with
    it, and `status:<status>` and `priority:<priority>` restrict to the values
    that start with it, like `status:do` for doing and done (repeat them for
    any of several), all ignoring case. Every other word, including other
    `key:value` words, is searched for in the title and notes.

    Returns the filter and a message for each word that was left out of it:
    a status or priority nothing starts with, a missing one, or a bare `#`.
    The rest of the filter still applies, so a half-typed word doesn't empty
    the list.
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
    """Append the `enum` members `value` starts, or a message to `errors`."""
    matches = values_starting_with(enum, value)
    if matches:
        values.extend(matches)
        return
    choices = [member.value for member in enum]
    options = f"{', '.join(choices[:-1])} or {choices[-1]}"
    given = f"unknown {name} {value!r}" if value else f"{name}: needs a value"
    errors.append(f"{given}; use {options}")


def values_starting_with[E: StrEnum](enum: type[E], prefix: str) -> list[E]:
    """The members of `enum` whose value starts with `prefix`, ignoring case.

    In the enum's order; none for an empty `prefix`, so a bare `status:` is
    still an error.
    """
    prefix = prefix.lower()
    if not prefix:
        return []
    return [member for member in enum if member.value.startswith(prefix)]


# The `key:value` words of a filter whose values `suggest_filter` completes.
_VALUE_KEYS: dict[str, type[StrEnum]] = {"status": Status, "priority": Priority}


def suggest_filter(text: str, tags: Iterable[str]) -> str | None:
    """`text` with the `#tag`, status or priority being typed completed, or None.

    The word being typed is the last one in `text`. `#<start>` completes to
    the alphabetically first of `tags` that starts with it, ignoring case and
    leaving out the tags already typed as `#tag` before it. `status:<start>`
    and `priority:<start>` complete to the first value that starts with it,
    in the order of `values_starting_with`. The text as typed is kept and the
    rest of the match added. Nothing is suggested for a plain word, while no
    word is being typed (empty text or whitespace at the end), before a letter
    follows `#` or the colon, or when the match is what's typed already.
    """
    if not text or text[-1].isspace():
        return None
    word = text.split()[-1]
    if word.startswith("#"):
        before = text[: len(text) - len(word)].split()
        entered = {typed[1:].lower() for typed in before if typed.startswith("#")}
        matches = (tag for tag in sorted(set(tags)) if tag not in entered)
        return _complete(text, word[1:], matches)
    key, colon, value = word.partition(":")
    enum = _VALUE_KEYS.get(key.lower()) if colon else None
    if enum is None:
        return None
    return _complete(text, value, (member.value for member in enum))


def _complete(text: str, typed: str, values: Iterable[str]) -> str | None:
    """`text` plus the rest of the first of `values` that starts with `typed`.

    Ignoring case; None if `typed` is empty, nothing starts with it, or the
    first match is `typed` itself.
    """
    start = typed.lower()
    if not start:
        return None
    for value in values:
        if value.lower().startswith(start):
            return None if value.lower() == start else text + value[len(typed) :]
    return None


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
    of `statuses`, its priority one of `priorities`, each of `tags` starts one
    of its tags (`err` for `errands`) or is a typo of one, and every word of
    `text` appears in its title or notes or is a typo of a word there (`mlik`
    for milk). Tags and text ignore case; see `is_typo_of` for what counts as
    a typo.
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
    if not all(
        any(own.startswith(tag) or is_typo_of(tag, own) for own in task.tags)
        for tag in tags
    ):
        return False
    haystack = f"{task.title}\n{task.notes}".casefold()
    missing = [word for word in words if word not in haystack]
    if not missing:
        return True
    own_words = set(_WORD.findall(haystack))
    return all(any(is_typo_of(word, own) for own in own_words) for word in missing)


def allowed_edits(word: str) -> int:
    """How many typos `word` may have: none up to 3 letters, 1 up to 7, then 2."""
    if len(word) <= 3:
        return 0
    return 1 if len(word) <= 7 else 2


def is_typo_of(word: str, other: str) -> bool:
    """Whether `word` is `other` with at most `allowed_edits(word)` typos.

    A typo is a wrong, missing or extra letter, or two neighbouring letters
    swapped (`mlik` for milk). Both are expected in the same case. A word of
    3 letters or fewer must be exact, so it's never a typo of another word.
    """
    limit = allowed_edits(word)
    if limit == 0 or abs(len(word) - len(other)) > limit:
        return False
    return edit_distance(word, other) <= limit


def edit_distance(a: str, b: str) -> int:
    """The fewest typos that turn `a` into `b`, as `is_typo_of` counts them.

    The optimal string alignment distance: changing, adding or removing a
    letter, or swapping two neighbours, each count as one, and no part of the
    word is edited twice.
    """
    # rows[i][j]: the distance between a[:i] and b[:j].
    rows = [list(range(len(b) + 1))]
    for i in range(1, len(a) + 1):
        row = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            row[j] = min(rows[i - 1][j] + 1, row[j - 1] + 1, rows[i - 1][j - 1] + cost)
            swapped = a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]
            if i > 1 and j > 1 and swapped:
                row[j] = min(row[j], rows[i - 2][j - 2] + 1)
        rows.append(row)
    return rows[-1][-1]
