import dataclasses
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from tskmngr import models
from tskmngr.models import (
    CROCKFORD_ALPHABET,
    ID_LENGTH,
    Priority,
    Status,
    Task,
    TaskValidationError,
    new_id,
    new_task,
    next_status,
    parse_due,
)

CREATED = datetime(2026, 10, 28, 9, 15, tzinfo=UTC)


def make_task(**overrides: object) -> Task:
    fields: dict[str, object] = {
        "id": "01JB3K7Q2X",
        "title": "Buy milk",
        "created": CREATED,
        "updated": CREATED,
    }
    fields.update(overrides)
    return Task(**fields)


def assert_invalid(field: str, **overrides: object) -> TaskValidationError:
    with pytest.raises(TaskValidationError) as excinfo:
        make_task(**overrides)
    assert excinfo.value.field == field
    return excinfo.value


# Enums


def test_status_values_match_the_file_format() -> None:
    assert [s.value for s in Status] == ["todo", "doing", "done"]


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (Status.TODO, Status.DOING),
        (Status.DOING, Status.DONE),
        (Status.DONE, Status.TODO),
    ],
)
def test_next_status_cycles_todo_doing_done(status: Status, expected: Status) -> None:
    assert next_status(status) is expected


def test_priority_values_match_the_file_format() -> None:
    assert [p.value for p in Priority] == ["low", "normal", "high"]


# Task


def test_task_defaults() -> None:
    task = make_task()

    assert task.status is Status.TODO
    assert task.priority is Priority.NORMAL
    assert task.due is None
    assert task.tags == ()
    assert task.notes == ""


def test_task_is_frozen() -> None:
    task = make_task()

    with pytest.raises(dataclasses.FrozenInstanceError):
        task.title = "Other"  # type: ignore[misc]


def test_replace_creates_an_edited_copy() -> None:
    task = make_task()

    edited = dataclasses.replace(task, title="Buy oat milk", status=Status.DONE)

    assert edited.title == "Buy oat milk"
    assert edited.status is Status.DONE
    assert task.title == "Buy milk"


def test_replace_validates_the_new_values() -> None:
    task = make_task()

    with pytest.raises(TaskValidationError) as excinfo:
        dataclasses.replace(task, title="")

    assert excinfo.value.field == "title"


def test_error_message_names_the_field() -> None:
    error = assert_invalid("title", title=1.1)

    assert str(error) == "title: expected str, got float"
    assert error.message == "expected str, got float"


@pytest.mark.parametrize("value", [None, 1])
def test_id_must_be_a_string(value: object) -> None:
    assert_invalid("id", id=value)


@pytest.mark.parametrize("value", ["", "   "])
def test_id_must_not_be_blank(value: str) -> None:
    assert_invalid("id", id=value)


def test_id_need_not_be_crockford() -> None:
    # A hand-made file is a task under its own filename.
    assert make_task(id="my-task").id == "my-task"


@pytest.mark.parametrize("value", [None, 1.1, ["Buy milk"]])
def test_title_must_be_a_string(value: object) -> None:
    assert_invalid("title", title=value)


@pytest.mark.parametrize("value", ["", " ", "\t\n"])
def test_title_must_not_be_blank(value: str) -> None:
    assert_invalid("title", title=value)


@pytest.mark.parametrize("value", ["Buy\nmilk", "Buy milk\n", "Buy\rmilk", "a\u2028b"])
def test_title_must_be_a_single_line(value: str) -> None:
    assert_invalid("title", title=value)


def test_title_is_kept_as_given() -> None:
    assert make_task(title="  Buy milk ").title == "  Buy milk "


@pytest.mark.parametrize("value", ["todo", None, Priority.LOW])
def test_status_must_be_a_status(value: object) -> None:
    assert_invalid("status", status=value)


@pytest.mark.parametrize("value", ["high", None, Status.DONE])
def test_priority_must_be_a_priority(value: object) -> None:
    assert_invalid("priority", priority=value)


def test_due_accepts_a_date() -> None:
    assert make_task(due=date(2026, 11, 1)).due == date(2026, 11, 1)


@pytest.mark.parametrize("value", ["2026-11-01", datetime(2026, 11, 1, tzinfo=UTC)])
def test_due_must_be_a_date_or_none(value: object) -> None:
    assert_invalid("due", due=value)


def test_tags_are_lowercased_and_stored_as_a_tuple() -> None:
    task = make_task(tags=["Errands", "home"])

    assert task.tags == ("errands", "home")


def test_tags_keep_their_order() -> None:
    assert make_task(tags=("b", "a", "c")).tags == ("b", "a", "c")


@pytest.mark.parametrize("value", ["errands", None, {"errands"}])
def test_tags_must_be_a_list(value: object) -> None:
    assert_invalid("tags", tags=value)


@pytest.mark.parametrize("value", [[1], [None], [["a"]]])
def test_tags_must_be_strings(value: object) -> None:
    assert_invalid("tags", tags=value)


def test_tags_must_not_be_empty_strings() -> None:
    assert_invalid("tags", tags=["a", ""])


@pytest.mark.parametrize("tag", ["two words", " lead", "tab\there", "new\nline"])
def test_tags_must_not_contain_whitespace(tag: str) -> None:
    assert_invalid("tags", tags=[tag])


@pytest.mark.parametrize("value", [["a", "a"], ["Work", "work"]])
def test_tags_must_be_unique_after_lowercasing(value: list[str]) -> None:
    error = assert_invalid("tags", tags=value)

    assert error.message == f"duplicate tag {value[1].lower()!r}"


@pytest.mark.parametrize("field", ["created", "updated"])
@pytest.mark.parametrize("value", ["2026-10-28T09:15:00Z", date(2026, 10, 28), None])
def test_timestamps_must_be_datetimes(field: str, value: object) -> None:
    assert_invalid(field, **{field: value})


@pytest.mark.parametrize("field", ["created", "updated"])
def test_timestamps_must_be_timezone_aware(field: str) -> None:
    assert_invalid(field, **{field: datetime(2026, 10, 28, 9, 15)})


def test_timestamps_accept_any_timezone() -> None:
    cet = timezone(timedelta(hours=1))
    created = datetime(2026, 10, 28, 10, 15, tzinfo=cet)

    assert make_task(created=created).created == created


def test_updated_may_be_earlier_than_created() -> None:
    # Hand-edited files can have any order; they must still load.
    task = make_task(updated=CREATED - timedelta(days=1))

    assert task.updated < task.created


@pytest.mark.parametrize("value", [None, 1, ["notes"]])
def test_notes_must_be_a_string(value: object) -> None:
    assert_invalid("notes", notes=value)


# ID generation


def test_new_id_is_ten_crockford_characters() -> None:
    for _ in range(100):
        task_id = new_id()
        assert len(task_id) == ID_LENGTH
        assert set(task_id) <= set(CROCKFORD_ALPHABET)


def test_crockford_alphabet_excludes_i_l_o_u() -> None:
    assert len(CROCKFORD_ALPHABET) == 32
    assert not set("ILOU") & set(CROCKFORD_ALPHABET)


def scripted_choice(monkeypatch: pytest.MonkeyPatch, ids: list[str]) -> None:
    """Make `new_id` draw the characters of `ids`, one ID after another."""
    chars = iter("".join(ids))
    monkeypatch.setattr(models.secrets, "choice", lambda alphabet: next(chars))


def test_new_id_is_regenerated_on_collision(monkeypatch: pytest.MonkeyPatch) -> None:
    scripted_choice(monkeypatch, ["AAAAAAAAAA", "BBBBBBBBBB", "CCCCCCCCCC"])

    assert new_id({"AAAAAAAAAA", "BBBBBBBBBB"}) == "CCCCCCCCCC"


def test_new_id_collision_ignores_case(monkeypatch: pytest.MonkeyPatch) -> None:
    scripted_choice(monkeypatch, ["ABCDEFGHJK", "0000000000"])

    assert new_id(["abcdefghjk"]) == "0000000000"


# new_task


def test_new_task_sets_id_and_timestamps() -> None:
    before = datetime.now(UTC).replace(microsecond=0)

    task = new_task("Buy milk", existing_ids=())

    after = datetime.now(UTC)
    assert len(task.id) == ID_LENGTH
    assert before <= task.created <= after
    assert task.created.microsecond == 0
    assert task.created.tzinfo is UTC
    assert task.updated == task.created


def test_new_task_passes_the_fields_on() -> None:
    task = new_task(
        "Buy milk",
        existing_ids=(),
        status=Status.DOING,
        priority=Priority.HIGH,
        due=date(2026, 11, 1),
        tags=iter(["Errands"]),
        notes="2 litres",
    )

    assert task.title == "Buy milk"
    assert task.status is Status.DOING
    assert task.priority is Priority.HIGH
    assert task.due == date(2026, 11, 1)
    assert task.tags == ("errands",)
    assert task.notes == "2 litres"


def test_new_task_avoids_existing_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    scripted_choice(monkeypatch, ["AAAAAAAAAA", "BBBBBBBBBB"])

    assert new_task("Buy milk", existing_ids=["AAAAAAAAAA"]).id == "BBBBBBBBBB"


def test_new_task_validates_the_title() -> None:
    with pytest.raises(TaskValidationError):
        new_task("", existing_ids=())


def test_parse_due_reads_an_iso_date() -> None:
    assert parse_due("2026-11-01") == date(2026, 11, 1)


@pytest.mark.parametrize(
    "text", ["", "20261101", "2026-W44-7", "2026-13-01", "2026-11-1", " 2026-11-01"]
)
def test_parse_due_rejects_anything_but_yyyy_mm_dd(text: str) -> None:
    with pytest.raises(TaskValidationError) as raised:
        parse_due(text)

    assert raised.value.field == "due"
    assert raised.value.message == f"expected a date like 2026-11-01, got {text!r}"


def test_models_does_not_import_textual() -> None:
    code = "import sys, tskmngr.models; sys.exit('textual' in sys.modules)"

    subprocess.run([sys.executable, "-c", code], check=True)
