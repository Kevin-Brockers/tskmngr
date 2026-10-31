"""Convert tasks to and from Markdown text with YAML frontmatter.

Pure text handling, no file I/O: `storage` reads and writes the files. The
frontmatter is handled by `ruamel.yaml` in round-trip mode, so unknown keys,
comments and formatting survive a save.
"""

import io
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import MarkedYAMLError, YAMLError
from ruamel.yaml.representer import RoundTripRepresenter

from tskmngr.models import Priority, Status, Task, TaskValidationError

DELIMITER = "---"

# Frontmatter keys in the order they're written for a new task.
FIELDS = ("title", "status", "priority", "due", "tags", "created", "updated")

QUOTE_HINT = "if it's meant as text, put it in quotes"


class MalformedTaskError(ValueError):
    """A task file can't be read as a task.

    `field` is the frontmatter key at fault and `line` the 1-based line in the
    file, when known.
    """

    def __init__(
        self, message: str, *, field: str | None = None, line: int | None = None
    ) -> None:
        prefix = "".join(
            [
                f"line {line}: " if line is not None else "",
                f"{field}: " if field else "",
            ]
        )
        super().__init__(prefix + message)
        self.message = message
        self.field = field
        self.line = line


@dataclass(frozen=True)
class TaskFile:
    """A task parsed from `text`. Pass it to `render` to save edits to it."""

    task: Task
    text: str


def parse(text: str, task_id: str, *, fallback_time: datetime) -> TaskFile:
    """Parse the text of a task file.

    `task_id` is the file's name without `.md`. A missing `created` or
    `updated` is set to `fallback_time` (storage passes the file's modification
    time); the text itself isn't changed until the task is saved.

    Raises `MalformedTaskError` if the text isn't a valid task.
    """
    frontmatter_text, _, notes = _split(text)
    frontmatter = _load(frontmatter_text)
    if "title" not in frontmatter:
        raise MalformedTaskError("missing", field="title")

    try:
        task = Task(
            id=task_id,
            title=_text(frontmatter, "title"),
            status=_choice(frontmatter, "status", Status, Status.TODO),
            priority=_choice(frontmatter, "priority", Priority, Priority.NORMAL),
            due=_due(frontmatter),
            tags=_tags(frontmatter),
            created=_timestamp(frontmatter, "created", fallback_time),
            updated=_timestamp(frontmatter, "updated", fallback_time),
            notes=notes,
        )
    except TaskValidationError as error:
        raise MalformedTaskError(
            error.message, field=error.field, line=_line(frontmatter, error.field)
        ) from error
    return TaskFile(task, text)


def render(task: Task, source: TaskFile | None = None) -> str:
    """Return the text of the task file for `task`.

    With `source`, the file `task` was loaded from, only what changed is
    rewritten: unknown keys and comments are kept, and an unchanged task gives
    back `source.text` byte for byte. The ID isn't written; it's the filename.
    """
    if source is None:
        frontmatter = _dump(_update(CommentedMap(), task, None))
        return _join(f"{DELIMITER}\n{frontmatter}{DELIMITER}\n", task.notes)

    # Unchanged parts are copied from the source text, not re-rendered.
    frontmatter_text, old_header, _ = _split(source.text)
    old = source.task
    header = old_header
    if any(getattr(task, field) != getattr(old, field) for field in FIELDS):
        frontmatter = _dump(_update(_load(frontmatter_text), task, old))
        header = f"{DELIMITER}\n{frontmatter}{DELIMITER}\n"
    if task.notes == old.notes:
        return header + source.text[len(old_header) :]
    return _join(header, task.notes)


# Splitting the text


def _split(text: str) -> tuple[str, str, str]:
    """Split a task file into frontmatter YAML, header and notes.

    The header is everything up to and including the closing delimiter line.
    The notes are the rest, without the blank line that separates them.
    """
    lines = _header_lines(text)
    header = "".join(lines)
    # Taken from the lines, not split on "\n", so any line ending works.
    frontmatter_text = "".join(lines[1:-1])
    notes = text[len(header) :]
    for separator in ("\r\n", "\n", "\r"):
        if notes.startswith(separator):
            notes = notes[len(separator) :]
            break
    return frontmatter_text, header, notes


def _header_lines(text: str) -> list[str]:
    """The lines of `text` up to and including the closing delimiter line."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != DELIMITER:
        raise MalformedTaskError(
            f"must start with a {DELIMITER!r} line followed by the frontmatter",
            line=1,
        )
    for index, line in enumerate(lines[1:], start=1):
        if line.rstrip("\r\n") == DELIMITER:
            return lines[: index + 1]
    raise MalformedTaskError(f"frontmatter has no closing {DELIMITER!r} line")


def _join(header: str, notes: str) -> str:
    return f"{header}\n{notes}" if notes else header


# YAML


class _Representer(RoundTripRepresenter):
    """Writes datetimes in ISO 8601 with a `T`, and UTC as `Z`."""

    def ignore_aliases(self, data: Any) -> bool:
        # Equal created and updated times must not become `&id001`/`*id001`.
        return True

    def represent_datetime(self, data: datetime) -> Any:
        text = data.isoformat()
        if data.utcoffset() is not None and not data.utcoffset():
            text = text.removesuffix("+00:00") + "Z"
        return self.represent_scalar("tag:yaml.org,2002:timestamp", text)


# Registered on the subclass, so other users of ruamel.yaml aren't affected.
_Representer.add_representer(datetime, _Representer.represent_datetime)


def _yaml() -> YAML:
    yaml = YAML()
    yaml.Representer = _Representer
    yaml.preserve_quotes = True
    # Don't wrap long titles over several lines.
    yaml.width = 4096
    return yaml


def _load(frontmatter_text: str) -> CommentedMap:
    try:
        frontmatter = _yaml().load(frontmatter_text)
    except YAMLError as error:
        line = None
        if isinstance(error, MarkedYAMLError) and error.problem_mark is not None:
            # +1 for 1-based lines, +1 for the opening delimiter.
            line = error.problem_mark.line + 2
        problem = getattr(error, "problem", None) or str(error)
        raise MalformedTaskError(f"invalid YAML: {problem}", line=line) from error
    if frontmatter is None:
        return CommentedMap()
    if not isinstance(frontmatter, CommentedMap):
        raise MalformedTaskError("frontmatter must be a mapping of keys to values")
    return frontmatter


def _dump(frontmatter: CommentedMap) -> str:
    stream = io.StringIO()
    _yaml().dump(frontmatter, stream)
    return stream.getvalue()


def _update(frontmatter: CommentedMap, task: Task, old: Task | None) -> CommentedMap:
    """Write the fields of `task` that differ from `old` or are missing."""
    for field in FIELDS:
        value = getattr(task, field)
        unchanged = old is not None and value == getattr(old, field)
        if field == "due" and value is None:
            if not unchanged:
                frontmatter.pop("due", None)
            continue
        if unchanged and field in frontmatter:
            continue
        if field == "tags":
            value = _tag_list(value, frontmatter.get("tags"))
        elif isinstance(value, (Status, Priority)):
            value = value.value
        if field in frontmatter:
            frontmatter[field] = value
        else:
            frontmatter.insert(_position(frontmatter, field), field, value)
    return frontmatter


def _position(frontmatter: CommentedMap, field: str) -> int:
    """Where to add a missing field: after the fields before it in `FIELDS`."""
    keys = list(frontmatter)
    earlier = FIELDS[: FIELDS.index(field)]
    return max((keys.index(key) + 1 for key in earlier if key in keys), default=0)


def _tag_list(tags: tuple[str, ...], old: object) -> CommentedSeq:
    seq = CommentedSeq(tags)
    # Written as [a, b] like in the documented format, unless the file uses
    # block style.
    if isinstance(old, CommentedSeq) and old.fa.flow_style() is False:
        seq.fa.set_block_style()
    else:
        seq.fa.set_flow_style()
    return seq


# Reading fields


def _line(frontmatter: CommentedMap, key: str) -> int | None:
    if key not in frontmatter:
        return None
    # +1 for 1-based lines, +1 for the opening delimiter.
    return frontmatter.lc.key(key)[0] + 2


def _error(frontmatter: CommentedMap, key: str, message: str) -> MalformedTaskError:
    return MalformedTaskError(message, field=key, line=_line(frontmatter, key))


def _describe(value: object) -> str:
    if value is None:
        return "no value"
    if isinstance(value, bool):
        return f"the boolean {str(value).lower()}"
    if isinstance(value, (int, float)):
        return f"the number {value}"
    if isinstance(value, datetime):
        return "a timestamp"
    if isinstance(value, date):
        return "a date"
    if isinstance(value, str):
        return f"the text {value!r}"
    return f"a {type(value).__name__}"


def _is_scalar(value: object) -> bool:
    return isinstance(value, (bool, int, float, date))


def _text(frontmatter: CommentedMap, key: str) -> str:
    value = frontmatter[key]
    if isinstance(value, str):
        # Drop ruamel's quoting-style subclass.
        return str(value)
    hint = f"; {QUOTE_HINT}" if _is_scalar(value) else ""
    raise _error(frontmatter, key, f"expected text, got {_describe(value)}{hint}")


def _choice[E: (Status, Priority)](
    frontmatter: CommentedMap, key: str, enum: type[E], default: E
) -> E:
    if key not in frontmatter:
        return default
    value = _text(frontmatter, key)
    try:
        return enum(value)
    except ValueError:
        allowed = ", ".join(member.value for member in enum)
        raise _error(
            frontmatter, key, f"unknown value {value!r}, expected one of {allowed}"
        ) from None


def _due(frontmatter: CommentedMap) -> date | None:
    value = frontmatter.get("due")
    if isinstance(value, str):
        raise _error(
            frontmatter, "due", f"expected a date like 2026-11-01, got {value!r}"
        )
    return value


def _tags(frontmatter: CommentedMap) -> tuple[str, ...]:
    value = frontmatter.get("tags", [])
    if value is None:
        return ()
    if not isinstance(value, list):
        raise _error(
            frontmatter,
            "tags",
            f"expected a list like [errands, home], got {_describe(value)}",
        )
    for tag in value:
        if not isinstance(tag, str):
            hint = f"; {QUOTE_HINT}" if _is_scalar(tag) else ""
            raise _error(
                frontmatter, "tags", f"expected text, got {_describe(tag)}{hint}"
            )
    return tuple(str(tag) for tag in value)


def _timestamp(frontmatter: CommentedMap, key: str, fallback: datetime) -> datetime:
    if key not in frontmatter:
        return fallback
    value = frontmatter[key]
    if isinstance(value, datetime):
        # Drop ruamel's TimeStamp subclass.
        return datetime(
            value.year,
            value.month,
            value.day,
            value.hour,
            value.minute,
            value.second,
            value.microsecond,
            tzinfo=value.tzinfo,
        )
    if isinstance(value, str):
        raise _error(
            frontmatter,
            key,
            f"expected a timestamp like 2026-10-28T09:15:00Z, got {value!r}",
        )
    return value
