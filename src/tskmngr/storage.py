"""Read and write task files in the tasks directory.

One `<id>.md` file per task. Saves are atomic and refuse to overwrite a file
that changed on disk since it was loaded. Deleting moves the file into
`.trash/`, which is never loaded or emptied. `scan_tasks_dir` gives the time and
size of each task file, so a caller can poll for changes made outside the app.
"""

import os
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


def tasks_dir() -> Path:
    """The tasks directory: `TSKMNGR_DIR` if set, else the default."""
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
            tasks.append(_load(path))
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
    stamp = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    target = trash / f"{source.task.id}.{stamp}{SUFFIX}"
    counter = 0
    while target.exists():
        counter += 1
        target = trash / f"{source.task.id}.{stamp}-{counter}{SUFFIX}"
    path.rename(target)
    return target


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


def _load(path: Path) -> TaskFile:
    try:
        text = _read(path)
        mtime = path.stat().st_mtime
    except UnicodeDecodeError:
        raise MalformedTaskError("not UTF-8 text") from None
    except OSError as error:
        raise MalformedTaskError(f"can't be read: {error.strerror}") from error
    fallback = datetime.fromtimestamp(mtime, UTC).replace(microsecond=0)
    return parse(text, path.stem, fallback_time=fallback)


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
