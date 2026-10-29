"""The task data model: the `Task` dataclass, its enums and ID generation."""

import secrets
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum

# Crockford base32: digits and uppercase letters without I, L, O and U.
CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ID_LENGTH = 10


class Status(StrEnum):
    TODO = "todo"
    DOING = "doing"
    DONE = "done"


class Priority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class TaskValidationError(ValueError):
    """A task field has the wrong type or an invalid value."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


@dataclass(frozen=True, kw_only=True)
class Task:
    """One task. Validated on creation; edit it with `dataclasses.replace`.

    `id` is the task file's name without `.md` and is not stored in the
    frontmatter. `notes` is the Markdown body. Tags are lowercased and stored
    as a tuple; a list is accepted too.
    """

    id: str
    title: str
    status: Status = Status.TODO
    priority: Priority = Priority.NORMAL
    due: date | None = None
    tags: tuple[str, ...] = ()
    created: datetime
    updated: datetime
    notes: str = ""

    def __post_init__(self) -> None:
        _check_id(self.id)
        _check_title(self.title)
        _check_type("status", self.status, Status)
        _check_type("priority", self.priority, Priority)
        _check_due(self.due)
        # Frozen dataclass, so the normalized tags are set via object.__setattr__.
        object.__setattr__(self, "tags", _normalize_tags(self.tags))
        _check_timestamp("created", self.created)
        _check_timestamp("updated", self.updated)
        _check_type("notes", self.notes, str)


def new_id(existing: Collection[str] = ()) -> str:
    """Return a random Crockford base32 ID that isn't in `existing`.

    The comparison ignores case, since task files may live on a
    case-insensitive filesystem.
    """
    taken = {task_id.upper() for task_id in existing}
    while True:
        task_id = "".join(secrets.choice(CROCKFORD_ALPHABET) for _ in range(ID_LENGTH))
        if task_id not in taken:
            return task_id


def new_task(
    title: str,
    *,
    existing_ids: Collection[str],
    status: Status = Status.TODO,
    priority: Priority = Priority.NORMAL,
    due: date | None = None,
    tags: Iterable[str] = (),
    notes: str = "",
) -> Task:
    """Create a task with a fresh ID, created and updated now (UTC, whole seconds)."""
    now = datetime.now(UTC).replace(microsecond=0)
    return Task(
        id=new_id(existing_ids),
        title=title,
        status=status,
        priority=priority,
        due=due,
        tags=tuple(tags),
        created=now,
        updated=now,
        notes=notes,
    )


def _check_type(field: str, value: object, expected: type) -> None:
    if not isinstance(value, expected):
        raise TaskValidationError(
            field, f"expected {expected.__name__}, got {type(value).__name__}"
        )


def _check_id(value: object) -> None:
    _check_type("id", value, str)
    if not value.strip():
        raise TaskValidationError("id", "must not be blank")


def _check_title(value: object) -> None:
    _check_type("title", value, str)
    if not value.strip():
        raise TaskValidationError("title", "must not be blank")
    if value.splitlines() != [value]:
        raise TaskValidationError("title", "must be a single line")


def _check_due(value: object) -> None:
    if value is None:
        return
    # datetime is a subclass of date, but a due date has no time of day.
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TaskValidationError(
            "due", f"expected date or None, got {type(value).__name__}"
        )


def _normalize_tags(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise TaskValidationError(
            "tags", f"expected a list of strings, got {type(value).__name__}"
        )
    tags: list[str] = []
    for tag in value:
        if not isinstance(tag, str):
            raise TaskValidationError(
                "tags", f"expected a list of strings, got {type(tag).__name__} item"
            )
        if not tag:
            raise TaskValidationError("tags", "a tag must not be empty")
        if any(char.isspace() for char in tag):
            raise TaskValidationError("tags", f"tag {tag!r} contains whitespace")
        tag = tag.lower()
        if tag in tags:
            raise TaskValidationError("tags", f"duplicate tag {tag!r}")
        tags.append(tag)
    return tuple(tags)


def _check_timestamp(field: str, value: object) -> None:
    _check_type(field, value, datetime)
    if value.utcoffset() is None:
        raise TaskValidationError(field, "must include a timezone")
