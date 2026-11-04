"""Read and write task files in the tasks directory.

One `<id>.md` file per task. Saves are atomic and refuse to overwrite a file
that changed on disk since it was loaded. Deleting moves the file into
`.trash/`, as `<id>.<delete time>.md`. Files there are never loaded as tasks or
emptied; `load_trash` only lists them. `scan_tasks_dir` gives the time and size
of each task file, so a caller can poll for changes made outside the app.
"""

import os
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from tskmngr.models import Task
from tskmngr.taskfile import MalformedTaskError, TaskFile, parse, render

ENV_VAR = "TSKMNGR_DIR"
DEFAULT_DIR = Path(".local", "share", "tskmngr", "tasks")
SUFFIX = ".md"
TRASH = ".trash"
# The delete time in a trashed file's name, in UTC, e.g. `2026-10-30T12-00-05Z`.
TRASH_TIME_FORMAT = "%Y-%m-%dT%H-%M-%SZ"
# A trashed file's name: `<id>.<delete time>.md`, with `-N` after the time for
# the Nth later delete of the task in the same second.
_TRASH_NAME = re.compile(
    r"(?P<id>.+)\.(?P<time>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)"
    r"(?:-(?P<sequence>[1-9][0-9]*))?\.md"
)


class ConflictReason(StrEnum):
    CHANGED = "changed on disk since it was loaded"
    DELETED = "deleted on disk since it was loaded"
    EXISTS = "already exists"


class ConflictError(Exception):
    """A task file isn't in the state it was loaded in, so it's left alone.

    The caller should reload the task and let the user decide.
    """

    def __init__(self, path: Path, reason: ConflictReason) -> None:
        super().__init__(f"{path}: {reason}")
        self.path = path
        self.reason = reason


@dataclass(frozen=True)
class BadFile:
    """A task file that couldn't be loaded, and why."""

    path: Path
    error: MalformedTaskError


@dataclass(frozen=True)
class LoadResult:
    tasks: list[TaskFile]
    bad_files: list[BadFile]

    @property
    def ids(self) -> set[str]:
        """IDs of all task files, bad ones included, for `new_task`."""
        return {source.task.id for source in self.tasks} | {
            bad.path.stem for bad in self.bad_files
        }


@dataclass(frozen=True)
class DeletedTask:
    """A task file in `.trash/`: the task as it was when deleted, and when."""

    path: Path
    task: Task
    # In UTC, to the second, from the file's name.
    deleted: datetime
    # Which delete of the task in that second: 0 for the first, then 1, 2, …
    sequence: int = 0


@dataclass(frozen=True)
class TrashResult:
    # Newest delete first.
    deleted: list[DeletedTask]
    bad_files: list[BadFile]


def tasks_dir(configured: Path | None = None) -> Path:
    """The tasks directory: `configured`, else `TSKMNGR_DIR` if set, else the default.

    `configured` is the config file's `tasks_dir`, if it has one.
    """
    if configured is not None:
        return configured
    value = os.environ.get(ENV_VAR)
    if value:
        return Path(value).expanduser()
    return Path.home() / DEFAULT_DIR


def task_path(directory: Path, task_id: str) -> Path:
    return directory / f"{task_id}{SUFFIX}"


# A task file's modification time in nanoseconds and its size in bytes.
type FileStamp = tuple[int, int]


def scan_tasks_dir(directory: Path) -> dict[str, FileStamp]:
    """The modification time and size of each file `load_tasks` would load.

    Keyed by filename. Files are only looked up, never read, so this is cheap
    enough to call on a timer: if the result differs from an earlier one, task
    files were changed, added or removed since. A missing directory has no
    files; `OSError` is raised if the directory can't be listed.
    """
    stamps: dict[str, FileStamp] = {}
    if not directory.is_dir():
        return stamps
    for path in _task_paths(directory):
        try:
            stat = path.stat()
        except OSError:
            # Gone since it was listed, or unreadable: `load_tasks` reports
            # the latter, and its stamp shows up once it can be looked up.
            continue
        stamps[path.name] = (stat.st_mtime_ns, stat.st_size)
    return stamps


def scan_trash(directory: Path) -> dict[str, FileStamp]:
    """The modification time and size of each file `load_trash` would list.

    Like `scan_tasks_dir`, for `directory`'s `.trash/`.
    """
    return scan_tasks_dir(directory / TRASH)


def load_tasks(directory: Path) -> LoadResult:
    """Load every task file in `directory`, sorted by filename.

    Hidden files, subdirectories (including `.trash/`) and files not ending in
    `.md` are skipped. A missing directory has no tasks. Files that can't be
    read or parsed are returned in `bad_files`, never changed.
    """
    tasks: list[TaskFile] = []
    bad_files: list[BadFile] = []
    if not directory.is_dir():
        return LoadResult(tasks, bad_files)
    for path in _task_paths(directory):
        try:
            tasks.append(_load(path, path.stem))
        except MalformedTaskError as error:
            bad_files.append(BadFile(path, error))
    return LoadResult(tasks, bad_files)


def save_task(directory: Path, task: Task, source: TaskFile | None) -> TaskFile:
    """Write `task` atomically and return what was written.

    `source` is the file `task` was loaded from (None for a new task). The
    save is refused with `ConflictError` if the file no longer has the text it
    was loaded with, or if a new task's file already exists. The check and the
    write aren't one atomic step, so an edit landing in between is lost; that
    window is a few milliseconds.
    """
    if source is not None and source.task.id != task.id:
        raise ValueError(f"task ID {task.id!r} doesn't match {source.task.id!r}")
    path = task_path(directory, task.id)
    _check_unchanged(path, source)
    text = render(task, source)
    if source is None or text != source.text:
        directory.mkdir(parents=True, exist_ok=True)
        _write_atomic(path, text)
    return TaskFile(task, text)


def save_completed(
    directory: Path, task: Task, source: TaskFile | None, following: Task | None
) -> tuple[TaskFile, TaskFile | None]:
    """Save a task marked done and, if it repeats, its next occurrence.

    `source` is the file `task` was loaded from (None for a new task), and
    `following` the new task for the next occurrence (see
    `recurrence.complete`), or None. Nothing is written if `source`'s file
    changed on disk, or a new task's file already exists (`ConflictError`).
    The next occurrence is written first, so if it can't be, the task isn't
    marked done and still repeats.
    """
    _check_unchanged(task_path(directory, task.id), source)
    written = None if following is None else save_task(directory, following, None)
    return save_task(directory, task, source), written


def delete_task(
    directory: Path, source: TaskFile, *, now: datetime | None = None
) -> Path:
    """Move the task's file into `.trash/` and return its new path.

    The file is renamed to `<id>.<delete time>.md` (UTC), so earlier deletes
    of the same task are kept. Refused with `ConflictError` if the file changed
    or was deleted on disk since it was loaded.
    """
    path = task_path(directory, source.task.id)
    _check_unchanged(path, source)
    trash = directory / TRASH
    trash.mkdir(exist_ok=True)
    stamp = (now or datetime.now(UTC)).astimezone(UTC).strftime(TRASH_TIME_FORMAT)
    target = trash / f"{source.task.id}.{stamp}{SUFFIX}"
    counter = 0
    while target.exists():
        counter += 1
        target = trash / f"{source.task.id}.{stamp}-{counter}{SUFFIX}"
    path.rename(target)
    return target


def load_trash(directory: Path) -> TrashResult:
    """List the deleted tasks in `directory`'s `.trash/`, newest delete first.

    Each file is one delete, so a task deleted twice is listed twice. The
    delete time comes from the file's name (see `parse_trash_name`); deletes
    in the same second are newest first by their `-N`. Hidden files,
    subdirectories and files not ending in `.md` are skipped, like
    `load_tasks` does. A file that can't be read or parsed, or whose name has
    no delete time, is returned in `bad_files`, sorted by name. Nothing is
    changed. A missing `.trash/` has no deleted tasks; `OSError` is raised if
    it can't be listed.
    """
    trash = directory / TRASH
    deleted: list[DeletedTask] = []
    bad_files: list[BadFile] = []
    if not trash.is_dir():
        return TrashResult(deleted, bad_files)
    for path in _task_paths(trash):
        name = parse_trash_name(path.name)
        if name is None:
            error = MalformedTaskError("name isn't <id>.<delete time>.md")
            bad_files.append(BadFile(path, error))
            continue
        task_id, when, sequence = name
        try:
            source = _load(path, task_id)
        except MalformedTaskError as error:
            bad_files.append(BadFile(path, error))
            continue
        deleted.append(DeletedTask(path, source.task, when, sequence))
    deleted.sort(
        key=lambda entry: (entry.deleted, entry.sequence, entry.path.name),
        reverse=True,
    )
    return TrashResult(deleted, bad_files)


def parse_trash_name(name: str) -> tuple[str, datetime, int] | None:
    """The task ID, delete time (UTC) and `-N` in a trashed file's name.

    `delete_task` names the files `<id>.<delete time>.md`, adding `-N` after
    the time for later deletes of the task in the same second; without it,
    N is 0. Returns None for any other name, or one with a time that doesn't
    exist (like month 13).
    """
    match = _TRASH_NAME.fullmatch(name)
    if match is None:
        return None
    try:
        when = datetime.strptime(match["time"], TRASH_TIME_FORMAT)
    except ValueError:
        return None
    sequence = int(match["sequence"]) if match["sequence"] else 0
    return match["id"], when.replace(tzinfo=UTC), sequence


def check_unchanged(directory: Path, source: TaskFile) -> None:
    """Raise `ConflictError` if `source`'s file changed or was deleted on disk.

    The same check a save or delete of `source` makes before writing.
    """
    _check_unchanged(task_path(directory, source.task.id), source)


def _task_paths(directory: Path) -> list[Path]:
    """The task files in `directory`, sorted by name.

    Hidden files, subdirectories (including `.trash/`) and files not ending in
    `.md` aren't task files.
    """
    return [
        path
        for path in sorted(directory.iterdir())
        if not path.name.startswith(".") and path.suffix == SUFFIX and path.is_file()
    ]


def _load(path: Path, task_id: str) -> TaskFile:
    try:
        text = _read(path)
        mtime = path.stat().st_mtime
    except UnicodeDecodeError:
        raise MalformedTaskError("not UTF-8 text") from None
    except OSError as error:
        raise MalformedTaskError(f"can't be read: {error.strerror}") from error
    fallback = datetime.fromtimestamp(mtime, UTC).replace(microsecond=0)
    return parse(text, task_id, fallback_time=fallback)


def _read(path: Path) -> str:
    # newline="" keeps \r\n, so an unchanged file saves back byte for byte.
    with path.open(encoding="utf-8", newline="") as file:
        return file.read()


def _check_unchanged(path: Path, source: TaskFile | None) -> None:
    if source is None:
        if path.exists():
            raise ConflictError(path, ConflictReason.EXISTS)
        return
    try:
        text = _read(path)
    except FileNotFoundError:
        raise ConflictError(path, ConflictReason.DELETED) from None
    except UnicodeDecodeError:
        raise ConflictError(path, ConflictReason.CHANGED) from None
    if text != source.text:
        raise ConflictError(path, ConflictReason.CHANGED)


def _write_atomic(path: Path, text: str) -> None:
    """Write to a hidden temp file next to `path`, then rename it over `path`."""
    temp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    # 0o666 lets the umask decide a new file's permissions, like open() does.
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        if path.exists():
            os.chmod(temp, path.stat().st_mode)
        os.replace(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
