"""Recurring tasks: when the next occurrence is due, and creating it.

Pure logic, no file I/O. A task with a repeat rule that's marked done gets a
next occurrence: a new task with a fresh ID, the same title, priority, tags and
rule, the notes with every subtask unchecked, status todo and the next due
date. The rule moves to the new task, so the done one no longer repeats.

The next due date follows the schedule from the old due date, skipping
occurrences that are already past, so it's always after today. A task without
a due date counts from the day it's done. Monthly and yearly rules keep the day
of the month: a due date on the 31st moves to the last day of a shorter month,
and `repeat_from` remembers the 31st until the day fits again.
"""

import calendar
from collections.abc import Collection
from dataclasses import replace
from datetime import date, datetime, timedelta

from tskmngr.models import Repeat, Status, Task, Unit, new_task
from tskmngr.subtasks import uncheck_all


class RecurrenceError(ValueError):
    """The next occurrence can't be computed, e.g. it's after the year 9999."""


def next_due(
    repeat: Repeat, due: date | None, repeat_from: date | None, today: date
) -> tuple[date, date | None]:
    """The next due date after `due` and `today`, and the `repeat_from` to keep.

    Without `due`, the next occurrence is one interval after `today`. Days
    and weeks step from `due`; months and years step from `repeat_from`, if
    given, else `due`, keeping its day of the month where the month has it.
    The returned `repeat_from` is that start date when the next due date had
    to be moved to a month's last day, else None.
    """
    if due is None:
        return _add(today, repeat, 1), None
    by_month = repeat.unit in (Unit.MONTHS, Unit.YEARS)
    start = repeat_from if by_month and repeat_from is not None else due
    try:
        steps = 1
        candidate = _add(start, repeat, steps)
        while candidate <= due or candidate <= today:
            steps += 1
            candidate = _add(start, repeat, steps)
    except OverflowError:
        raise RecurrenceError(
            f"the next occurrence of {repeat} would be after the year {date.max.year}"
        ) from None
    return candidate, (start if by_month and candidate.day != start.day else None)


def _add(start: date, repeat: Repeat, steps: int) -> date:
    """`start` plus `steps` intervals of `repeat`."""
    count = repeat.every * steps
    match repeat.unit:
        case Unit.DAYS:
            return start + timedelta(days=count)
        case Unit.WEEKS:
            return start + timedelta(weeks=count)
        case Unit.MONTHS:
            return _add_months(start, count)
        case Unit.YEARS:
            return _add_months(start, 12 * count)


def _add_months(start: date, months: int) -> date:
    """`start` plus `months`; a missing day becomes the month's last day."""
    year, month = divmod(start.month - 1 + months, 12)
    year += start.year
    if year > date.max.year:
        raise OverflowError
    last_day = calendar.monthrange(year, month + 1)[1]
    return date(year, month + 1, min(start.day, last_day))


def complete(
    task: Task, *, existing_ids: Collection[str], now: datetime, today: date
) -> tuple[Task, Task | None]:
    """Mark `task` done; return it and its next occurrence, if it repeats.

    Call it only when a task that isn't done yet is being marked done.

    `task` is the task as it's about to be saved, with any other edits; it's
    returned with status done and `updated` set to `now`. If it repeats, the
    returned task no longer does and the next occurrence (a new ID not in
    `existing_ids`) carries the rule. Raises `RecurrenceError` if the next
    due date can't be computed.
    """
    done = replace(task, status=Status.DONE, updated=now)
    if task.repeat is None:
        return done, None
    due, repeat_from = next_due(task.repeat, task.due, task.repeat_from, today)
    following = replace(
        new_task(
            task.title,
            existing_ids=existing_ids,
            priority=task.priority,
            due=due,
            repeat=task.repeat,
            repeat_from=repeat_from,
            tags=task.tags,
            notes=uncheck_all(task.notes),
        ),
        created=now,
        updated=now,
    )
    return replace(done, repeat=None, repeat_from=None), following
