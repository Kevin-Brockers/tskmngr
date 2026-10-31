"""The `tskmngr` entry point. With no arguments it launches the TUI."""

import argparse
import re
import sys
from collections.abc import Sequence
from datetime import date

from tskmngr.app import TskmngrApp
from tskmngr.models import Priority, TaskValidationError, new_task
from tskmngr.storage import ConflictError, load_tasks, save_task, tasks_dir

ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the `tskmngr` command and return its exit code.

    `argv` defaults to the command-line arguments. Usage errors exit with 2
    (through argparse), errors while saving return 1.
    """
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command is None:
        TskmngrApp().run()
        return 0
    return args.handler(args)


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
    return parser


def _add(args: argparse.Namespace) -> int:
    directory = tasks_dir()
    try:
        existing_ids = load_tasks(directory).ids
    except OSError as error:
        reason = error.strerror or str(error)
        return _fail(f"can't read the tasks in {directory}: {reason}")
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
        return _fail(f"can't save the task: {error}")
    except OSError as error:
        reason = error.strerror or str(error)
        return _fail(f"can't save the task in {directory}: {reason}")
    print(task.id)
    return 0


def _due_date(value: str) -> date:
    """Parse a due date given as YYYY-MM-DD, for argparse."""
    # date.fromisoformat also takes forms like 20261101 or 2026-W44-7.
    if ISO_DATE.fullmatch(value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(f"expected a date like 2026-11-01, got {value!r}")


def _fail(message: str) -> int:
    print(f"tskmngr: error: {message}", file=sys.stderr)
    return 1
