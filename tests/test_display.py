from datetime import UTC, date, datetime, timedelta, timezone

from tskmngr.display import format_timestamp, task_fields
from tskmngr.models import Priority, Status, Task

CREATED = datetime(2026, 10, 28, 9, 15, tzinfo=UTC)


def make_task(task_id: str, title: str, **fields: object) -> Task:
    return Task(id=task_id, title=title, created=CREATED, updated=CREATED, **fields)


def test_task_fields_lists_every_field() -> None:
    task = make_task(
        "01JB3K7Q2X",
        "Buy milk",
        status=Status.DOING,
        priority=Priority.HIGH,
        due=date(2026, 11, 1),
        tags=("errands", "shop"),
    )

    assert task_fields(task) == [
        ("ID", "01JB3K7Q2X"),
        ("Title", "Buy milk"),
        ("Status", "doing"),
        ("Priority", "high"),
        ("Due", "2026-11-01"),
        ("Tags", "errands, shop"),
        ("Subtasks", "-"),
        ("Created", "2026-10-28T09:15:00Z"),
        ("Updated", "2026-10-28T09:15:00Z"),
    ]


def test_task_fields_shows_missing_values_as_a_dash() -> None:
    fields = dict(task_fields(make_task("A", "Read")))

    assert fields["Due"] == "-"
    assert fields["Tags"] == "-"
    assert fields["Subtasks"] == "-"


def test_task_fields_shows_subtasks_done_and_total() -> None:
    task = make_task("A", "Plan trip", notes="- [x] Book flights\n- [ ] Pack\n")

    assert dict(task_fields(task))["Subtasks"] == "1/2"


def test_task_fields_keeps_a_non_utc_offset() -> None:
    created = datetime(2026, 10, 28, 9, 15, tzinfo=timezone(timedelta(hours=2)))
    task = Task(id="A", title="Read", created=created, updated=CREATED)

    assert dict(task_fields(task))["Created"] == "2026-10-28T09:15:00+02:00"


def test_format_timestamp_writes_utc_as_z() -> None:
    assert format_timestamp(CREATED) == "2026-10-28T09:15:00Z"


def test_format_timestamp_keeps_other_offsets_and_microseconds() -> None:
    value = datetime(2026, 10, 28, 9, 15, 0, 5, tzinfo=timezone(timedelta(hours=-5)))

    assert format_timestamp(value) == "2026-10-28T09:15:00.000005-05:00"
