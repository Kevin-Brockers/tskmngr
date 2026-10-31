"""The `tskmngr` entry point. With no arguments it launches the TUI."""

import argparse
import re
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from tskmngr.app import TskmngrApp
from tskmngr.models import Priority, Status, Task, TaskValidationError, new_task
from tskmngr.query import SortKey, filter_tasks, sort_tasks
from tskmngr.storage import (
    ConflictError,
    LoadResult,
    load_tasks,
    save_task,
    tasks_dir,
)

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
    return parser


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
