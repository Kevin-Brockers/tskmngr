"""The `tskmngr` entry point. With no arguments it launches the TUI."""

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from tskmngr.app import TskmngrApp
from tskmngr.models import Priority, Status, Task, TaskValidationError, new_task
from tskmngr.query import SortKey, filter_tasks, match_id_prefix, sort_tasks
from tskmngr.storage import (
    ConflictError,
    LoadResult,
    load_tasks,
    save_task,
    tasks_dir,
)
from tskmngr.taskfile import TaskFile

ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

# Statuses `tskmngr list` shows unless told otherwise.
OPEN_STATUSES = (Status.TODO, Status.DOING)


class CommandError(Exception):
    """A command failed; `main` prints the message and returns 1."""


def main(argv: Sequence[str] | None = None) -> int:
    """Run the `tskmngr` command and return its exit code.

    `argv` defaults to the command-line arguments. Usage errors exit with 2
    (through argparse), errors while reading or saving tasks return 1.
    """
    parser = _parser()
    args, extra = parser.parse_known_args(argv)
    # argparse takes a command's words only before or after its options, not
    # both, so `list milk -t errands store` leaves "store" over.
    takes_words = isinstance(getattr(args, "words", None), list)
    if extra and takes_words and not any(arg.startswith("-") for arg in extra):
        args.words += extra
        extra = []
    if extra:
        getattr(args, "parser", parser).error(
            f"unrecognized arguments: {' '.join(extra)}"
        )
    if args.command is None:
        TskmngrApp().run()
        return 0
    try:
        return args.handler(args)
    except CommandError as error:
        print(f"tskmngr: error: {error}", file=sys.stderr)
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tskmngr",
        description="A terminal task manager. Without a command, opens the TUI.",
    )
    commands = parser.add_subparsers(dest="command", title="commands")

    add = commands.add_parser(
        "add", help="add a task", description="Add a task and print its ID."
    )
    add.add_argument("title", help="the task's title (quote it if it has spaces)")
    add.add_argument(
        "-p",
        "--priority",
        choices=[priority.value for priority in Priority],
        default=Priority.NORMAL.value,
        help="default: %(default)s",
    )
    add.add_argument(
        "-d", "--due", type=_due_date, metavar="YYYY-MM-DD", help="due date"
    )
    add.add_argument(
        "-t",
        "--tag",
        action="append",
        default=[],
        dest="tags",
        metavar="TAG",
        help="add a tag; repeat for more tags",
    )
    add.set_defaults(handler=_add, parser=add)

    list_ = commands.add_parser(
        "list",
        help="list tasks",
        description="List tasks, by default the ones not done yet, soonest due first.",
    )
    list_.add_argument(
        "words",
        nargs="*",
        metavar="WORD",
        help="only tasks with every word in their title or notes",
    )
    statuses = list_.add_mutually_exclusive_group()
    statuses.add_argument(
        "-s",
        "--status",
        action="append",
        choices=[status.value for status in Status],
        dest="statuses",
        help="only tasks with this status; repeat for more (default: todo and doing)",
    )
    statuses.add_argument("-a", "--all", action="store_true", help="include done tasks")
    list_.add_argument(
        "-p",
        "--priority",
        action="append",
        choices=[priority.value for priority in Priority],
        default=[],
        dest="priorities",
        help="only tasks with this priority; repeat for more",
    )
    list_.add_argument(
        "-t",
        "--tag",
        action="append",
        default=[],
        dest="tags",
        metavar="TAG",
        help="only tasks with this tag; repeat to require more tags",
    )
    list_.add_argument(
        "--sort",
        choices=[key.value for key in SortKey],
        default=SortKey.DUE.value,
        help="default: %(default)s",
    )
    list_.add_argument(
        "-r", "--reverse", action="store_true", help="reverse the sort order"
    )
    list_.set_defaults(handler=_list, parser=list_)

    show = commands.add_parser(
        "show",
        help="show a task",
        description="Show all fields of a task, then its notes.",
    )
    _add_id_argument(show)
    show.set_defaults(handler=_show, parser=show)

    edit = commands.add_parser(
        "edit",
        help="change a task's fields",
        description="Change the given fields of a task; the rest stay as they are.",
    )
    _add_id_argument(edit)
    edit.add_argument("--title", help="new title (quote it if it has spaces)")
    edit.add_argument("-s", "--status", choices=[status.value for status in Status])
    edit.add_argument(
        "-p", "--priority", choices=[priority.value for priority in Priority]
    )
    due = edit.add_mutually_exclusive_group()
    due.add_argument(
        "-d", "--due", type=_due_date, metavar="YYYY-MM-DD", help="new due date"
    )
    due.add_argument("--no-due", action="store_true", help="remove the due date")
    edit.add_argument(
        "-t",
        "--tag",
        action="append",
        default=[],
        dest="tags",
        metavar="TAG",
        help="add a tag; repeat for more tags",
    )
    untag = edit.add_mutually_exclusive_group()
    untag.add_argument(
        "--untag",
        action="append",
        default=[],
        dest="untags",
        metavar="TAG",
        help="remove a tag; repeat for more tags",
    )
    untag.add_argument(
        "--clear-tags", action="store_true", help="remove all tags before adding any"
    )
    edit.set_defaults(handler=_edit, parser=edit)

    done = commands.add_parser(
        "done", help="mark a task as done", description="Mark a task as done."
    )
    _add_id_argument(done)
    done.set_defaults(handler=_done, parser=done)
    return parser


def _add_id_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "id", metavar="ID", help="the task's ID or a unique prefix of it"
    )


def _add(args: argparse.Namespace) -> int:
    directory = tasks_dir()
    existing_ids = _load(directory).ids
    try:
        task = new_task(
            args.title,
            existing_ids=existing_ids,
            priority=Priority(args.priority),
            due=args.due,
            tags=args.tags,
        )
    except TaskValidationError as error:
        args.parser.error(str(error))
    try:
        save_task(directory, task, None)
    except ConflictError as error:
        raise CommandError(f"can't save the task: {error}") from error
    except OSError as error:
        raise CommandError(
            f"can't save the task in {directory}: {_reason(error)}"
        ) from error
    print(task.id)
    return 0


def _list(args: argparse.Namespace) -> int:
    result = _load(tasks_dir())
    for bad in result.bad_files:
        print(f"tskmngr: warning: can't load {bad.path}: {bad.error}", file=sys.stderr)
    if args.statuses:
        statuses = [Status(status) for status in args.statuses]
    else:
        statuses = [] if args.all else list(OPEN_STATUSES)
    tasks = filter_tasks(
        [source.task for source in result.tasks],
        statuses=statuses,
        priorities=[Priority(priority) for priority in args.priorities],
        tags=args.tags,
        text=" ".join(args.words),
    )
    tasks = sort_tasks(tasks, SortKey(args.sort), reverse=args.reverse)
    print("\n".join(format_table(tasks)) if tasks else "No tasks.")
    return 0


def _show(args: argparse.Namespace) -> int:
    source = _find(args, _load(tasks_dir()))
    print("\n".join(format_details(source.task)))
    return 0


def _edit(args: argparse.Namespace) -> int:
    changes: dict[str, object] = {}
    if args.title is not None:
        changes["title"] = args.title
    if args.status is not None:
        changes["status"] = Status(args.status)
    if args.priority is not None:
        changes["priority"] = Priority(args.priority)
    if args.due is not None or args.no_due:
        changes["due"] = args.due
    tag_changes = args.tags or args.untags or args.clear_tags
    if not changes and not tag_changes:
        args.parser.error("nothing to change; give at least one option")
    added = [tag.lower() for tag in args.tags]
    both = sorted(set(added) & {tag.lower() for tag in args.untags})
    if both:
        args.parser.error(f"can't both add and remove tag {both[0]!r}")

    directory = tasks_dir()
    source = _find(args, _load(directory))
    task = source.task
    if tag_changes:
        tags = [] if args.clear_tags else list(task.tags)
        for tag in args.untags:
            if tag.lower() not in tags:
                raise CommandError(f"task {task.id} has no tag {tag.lower()!r}")
            tags.remove(tag.lower())
        # Adding a tag the task already has changes nothing, like `done` twice.
        changes["tags"] = tags + [
            tag for tag in dict.fromkeys(added) if tag not in tags
        ]
    try:
        edited = replace(task, **changes)
    except TaskValidationError as error:
        args.parser.error(str(error))
    _save_changed(directory, source, edited)
    return 0


def _done(args: argparse.Namespace) -> int:
    directory = tasks_dir()
    source = _find(args, _load(directory))
    _save_changed(directory, source, replace(source.task, status=Status.DONE))
    return 0


def _find(args: argparse.Namespace, result: LoadResult) -> TaskFile:
    """The task whose ID starts with `args.id`, among files that failed to load too.

    A malformed file can be picked or make a prefix ambiguous, so its error is
    reported instead of a misleading "no task".
    """
    bad_files = {bad.path.stem: bad for bad in result.bad_files}
    ids = [source.task.id for source in result.tasks] + list(bad_files)
    try:
        task_id = match_id_prefix(ids, args.id)
    except ValueError as error:
        args.parser.error(str(error))
    except LookupError as error:
        raise CommandError(str(error)) from error
    if task_id in bad_files:
        bad = bad_files[task_id]
        raise CommandError(f"can't load {bad.path}: {bad.error}")
    return next(source for source in result.tasks if source.task.id == task_id)


def _save_changed(directory: Path, source: TaskFile, task: Task) -> None:
    """Save `task` with `updated` set to now, unless it's the same as `source`'s."""
    if task == source.task:
        return
    task = replace(task, updated=datetime.now(UTC).replace(microsecond=0))
    try:
        save_task(directory, task, source)
    except ConflictError as error:
        raise CommandError(f"can't save the task: {error}") from error
    except OSError as error:
        raise CommandError(
            f"can't save the task in {directory}: {_reason(error)}"
        ) from error


def format_details(task: Task) -> list[str]:
    """Format every field of a task as `Label: value` lines, then its notes.

    Missing values are shown as `-`. The notes follow after a blank line, as
    written in the file.
    """
    fields = (
        ("ID", task.id),
        ("Title", task.title),
        ("Status", task.status.value),
        ("Priority", task.priority.value),
        ("Due", task.due.isoformat() if task.due else "-"),
        ("Tags", ", ".join(task.tags) or "-"),
        ("Created", _timestamp(task.created)),
        ("Updated", _timestamp(task.updated)),
    )
    width = max(len(label) for label, _ in fields) + 1
    lines = [f"{label + ':':<{width}}  {value}" for label, value in fields]
    notes = task.notes.rstrip("\r\n")
    return [*lines, "", notes] if notes else lines


def _timestamp(value: datetime) -> str:
    """ISO 8601 like in the task files, with UTC written as `Z`."""
    text = value.isoformat()
    if value.utcoffset() == timedelta(0):
        text = text.removesuffix("+00:00") + "Z"
    return text


def format_table(tasks: Sequence[Task]) -> list[str]:
    """Format tasks as lines of aligned columns under a header line.

    The title comes last and isn't padded; tags follow it as `#tag`.
    """
    header = ("ID", "STATUS", "PRIORITY", "DUE", "TITLE")
    rows = [
        (
            task.id,
            task.status.value,
            task.priority.value,
            task.due.isoformat() if task.due else "",
            " ".join([task.title, *(f"#{tag}" for tag in task.tags)]),
        )
        for task in tasks
    ]
    widths = [max(len(row[i]) for row in [header, *rows]) for i in range(4)]
    return [
        "  ".join([*map(str.ljust, row[:4], widths), row[4]]) for row in [header, *rows]
    ]


def _load(directory: Path) -> LoadResult:
    try:
        return load_tasks(directory)
    except OSError as error:
        raise CommandError(
            f"can't read the tasks in {directory}: {_reason(error)}"
        ) from error


def _reason(error: OSError) -> str:
    return error.strerror or str(error)


def _due_date(value: str) -> date:
    """Parse a due date given as YYYY-MM-DD, for argparse."""
    # date.fromisoformat also takes forms like 20261101 or 2026-W44-7.
    if ISO_DATE.fullmatch(value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(f"expected a date like 2026-11-01, got {value!r}")
