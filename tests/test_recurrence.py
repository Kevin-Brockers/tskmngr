import subprocess
import sys
from datetime import UTC, date, datetime

import pytest

from tskmngr.models import Priority, Repeat, Status, Task, Unit, parse_repeat
from tskmngr.recurrence import RecurrenceError, complete, next_due

CREATED = datetime(2026, 10, 28, 9, 15, tzinfo=UTC)
NOW = datetime(2026, 11, 4, 10, 0, tzinfo=UTC)
TODAY = date(2026, 11, 4)


def make_task(**fields: object) -> Task:
    defaults: dict[str, object] = {
        "id": "AAAA",
        "title": "Water plants",
        "created": CREATED,
        "updated": CREATED,
    }
    return Task(**(defaults | fields))


def due_after(rule: str, due: date | None, today: date = TODAY) -> date:
    return next_due(parse_repeat(rule), due, None, today)[0]


# next_due


@pytest.mark.parametrize(
    ("rule", "due", "expected"),
    [
        ("daily", date(2026, 11, 4), date(2026, 11, 5)),
        ("every 3 days", date(2026, 11, 10), date(2026, 11, 13)),
        ("weekly", date(2026, 11, 6), date(2026, 11, 13)),
        ("every 2 weeks", date(2026, 11, 6), date(2026, 11, 20)),
        ("monthly", date(2026, 11, 15), date(2026, 12, 15)),
        ("every 3 months", date(2026, 11, 15), date(2027, 2, 15)),
        ("yearly", date(2026, 12, 24), date(2027, 12, 24)),
        ("every 2 years", date(2026, 12, 24), date(2028, 12, 24)),
    ],
)
def test_next_due_adds_one_interval_to_a_due_date_not_yet_past(
    rule: str, due: date, expected: date
) -> None:
    assert due_after(rule, due) == expected


@pytest.mark.parametrize(
    ("rule", "due", "expected"),
    [
        # Overdue: occurrences already past are skipped, the next is after today.
        ("daily", date(2026, 10, 1), date(2026, 11, 5)),
        ("weekly", date(2026, 10, 7), date(2026, 11, 11)),
        # A step landing on today is skipped too.
        ("weekly", date(2026, 10, 28), date(2026, 11, 11)),
        ("monthly", date(2026, 8, 4), date(2026, 12, 4)),
        ("yearly", date(2020, 11, 5), date(2026, 11, 5)),
    ],
)
def test_next_due_skips_occurrences_that_are_already_past(
    rule: str, due: date, expected: date
) -> None:
    assert due_after(rule, due) == expected


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        ("daily", date(2026, 11, 5)),
        ("every 2 weeks", date(2026, 11, 18)),
        ("monthly", date(2026, 12, 4)),
        ("yearly", date(2027, 11, 4)),
    ],
)
def test_next_due_without_a_due_date_counts_from_today(
    rule: str, expected: date
) -> None:
    assert next_due(parse_repeat(rule), None, None, TODAY) == (expected, None)


def test_next_due_moves_a_missing_day_to_the_last_day_and_remembers_it() -> None:
    monthly = Repeat(1, Unit.MONTHS)
    today = date(2026, 1, 1)

    assert next_due(monthly, date(2026, 1, 31), None, today) == (
        date(2026, 2, 28),
        date(2026, 1, 31),
    )
    assert next_due(monthly, date(2026, 2, 28), date(2026, 1, 31), today) == (
        date(2026, 3, 31),
        None,
    )
    assert next_due(monthly, date(2026, 3, 31), None, today) == (
        date(2026, 4, 30),
        date(2026, 3, 31),
    )


def test_next_due_keeps_the_day_through_several_short_months() -> None:
    # Every 2 months from Dec 31: Feb 28, Apr 30, then Jun 30, Aug 31.
    rule = Repeat(2, Unit.MONTHS)
    today = date(2026, 1, 1)
    start = date(2025, 12, 31)

    assert next_due(rule, start, None, today) == (date(2026, 2, 28), start)
    assert next_due(rule, date(2026, 2, 28), start, today) == (
        date(2026, 4, 30),
        start,
    )
    assert next_due(rule, date(2026, 6, 30), start, today) == (
        date(2026, 8, 31),
        None,
    )


def test_next_due_moves_a_leap_day_to_feb_28_until_the_next_leap_year() -> None:
    yearly = Repeat(1, Unit.YEARS)
    leap_day = date(2028, 2, 29)
    today = date(2028, 1, 1)

    assert next_due(yearly, leap_day, None, today) == (date(2029, 2, 28), leap_day)
    assert next_due(yearly, date(2031, 2, 28), leap_day, today) == (
        date(2032, 2, 29),
        None,
    )


def test_next_due_with_repeat_from_still_skips_past_occurrences() -> None:
    monthly = Repeat(1, Unit.MONTHS)

    assert next_due(monthly, date(2026, 2, 28), date(2026, 1, 31), TODAY) == (
        date(2026, 11, 30),
        date(2026, 1, 31),
    )


@pytest.mark.parametrize("unit", [Unit.DAYS, Unit.WEEKS])
def test_next_due_ignores_repeat_from_for_days_and_weeks(unit: Unit) -> None:
    rule = Repeat(1, unit)

    due, repeat_from = next_due(rule, date(2026, 11, 30), date(2026, 1, 31), TODAY)

    assert due == next_due(rule, date(2026, 11, 30), None, TODAY)[0]
    assert repeat_from is None


def test_next_due_refuses_a_date_after_the_year_9999() -> None:
    with pytest.raises(RecurrenceError, match="after the year 9999"):
        next_due(Repeat(5000, Unit.YEARS), date(9000, 1, 1), None, TODAY)
    with pytest.raises(RecurrenceError, match="after the year 9999"):
        next_due(Repeat(10**9, Unit.DAYS), date(2026, 1, 1), None, TODAY)


# complete


def test_complete_marks_a_task_without_a_rule_done() -> None:
    task = make_task(status=Status.DOING, due=date(2026, 11, 6))

    done, following = complete(task, existing_ids={"AAAA"}, now=NOW, today=TODAY)

    assert done == make_task(status=Status.DONE, due=date(2026, 11, 6), updated=NOW)
    assert following is None


def test_complete_creates_the_next_occurrence_and_moves_the_rule_to_it() -> None:
    task = make_task(
        status=Status.DOING,
        priority=Priority.HIGH,
        due=date(2026, 1, 31),
        repeat=Repeat(1, Unit.MONTHS),
        tags=("home",),
        notes="Use the can.\n\n- [x] Kitchen\n- [X] Balcony\n- [ ] Office\n",
    )

    done, following = complete(
        task, existing_ids={"AAAA"}, now=NOW, today=date(2026, 1, 31)
    )

    assert done == make_task(
        status=Status.DONE,
        priority=Priority.HIGH,
        due=date(2026, 1, 31),
        tags=("home",),
        notes=task.notes,
        updated=NOW,
    )
    assert following is not None
    assert following.id != "AAAA"
    assert following == Task(
        id=following.id,
        title="Water plants",
        status=Status.TODO,
        priority=Priority.HIGH,
        due=date(2026, 2, 28),
        repeat=Repeat(1, Unit.MONTHS),
        repeat_from=date(2026, 1, 31),
        tags=("home",),
        created=NOW,
        updated=NOW,
        notes="Use the can.\n\n- [ ] Kitchen\n- [ ] Balcony\n- [ ] Office\n",
    )


def test_complete_gives_the_next_occurrence_an_unused_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    taken: list[object] = []

    def fake_new_id(existing: object) -> str:
        taken.append(existing)
        return "BBBB"

    monkeypatch.setattr("tskmngr.models.new_id", fake_new_id)
    task = make_task(repeat=Repeat(1, Unit.DAYS))

    _, following = complete(task, existing_ids={"AAAA", "CCCC"}, now=NOW, today=TODAY)

    assert following is not None
    assert following.id == "BBBB"
    assert taken == [{"AAAA", "CCCC"}]


def test_complete_without_a_due_date_gives_the_next_one_a_due_date() -> None:
    task = make_task(repeat=Repeat(1, Unit.WEEKS))

    _, following = complete(task, existing_ids=(), now=NOW, today=TODAY)

    assert following is not None
    assert following.due == date(2026, 11, 11)


def test_complete_keeps_other_edits_of_the_task() -> None:
    task = make_task(title="Water all plants", repeat=Repeat(1, Unit.DAYS))

    done, following = complete(task, existing_ids=(), now=NOW, today=TODAY)

    assert done.title == "Water all plants"
    assert following is not None
    assert following.title == "Water all plants"


def test_complete_raises_when_the_next_due_date_cant_be_computed() -> None:
    task = make_task(due=date(9999, 12, 1), repeat=Repeat(1, Unit.MONTHS))

    with pytest.raises(RecurrenceError):
        complete(task, existing_ids=(), now=NOW, today=TODAY)


def test_recurrence_does_not_import_textual() -> None:
    code = "import sys, tskmngr.recurrence; sys.exit('textual' in sys.modules)"

    subprocess.run([sys.executable, "-c", code], check=True)
