from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from tskmngr.models import Repeat, Status, Task, Unit
from tskmngr.recurrence import RecurrenceError
from tskmngr.storage import ConflictError, load_tasks, save_task
from tskmngr.widgets.saving import save_task_and_next

CREATED = datetime(2026, 10, 28, 9, 15, tzinfo=UTC)
NOW = datetime(2026, 11, 4, 10, 0, tzinfo=UTC)
WEEKLY = Repeat(1, Unit.WEEKS)


def make_task(task_id: str = "AAAA", **fields: object) -> Task:
    defaults: dict[str, object] = {
        "id": task_id,
        "title": "Water plants",
        "created": CREATED,
        "updated": CREATED,
    }
    return Task(**(defaults | fields))


def loaded(directory: Path) -> dict[str, Task]:
    return {source.task.id: source.task for source in load_tasks(directory).tasks}


def test_saving_a_change_other_than_done_adds_nothing(tmp_path: Path) -> None:
    source = save_task(tmp_path, make_task(repeat=WEEKLY), None)
    task = replace(source.task, status=Status.DOING, updated=NOW)

    assert save_task_and_next(tmp_path, task, source) is None

    assert loaded(tmp_path) == {"AAAA": task}


def test_marking_a_task_without_a_rule_done_adds_nothing(tmp_path: Path) -> None:
    source = save_task(tmp_path, make_task(), None)
    task = replace(source.task, status=Status.DONE, updated=NOW)

    assert save_task_and_next(tmp_path, task, source) is None

    assert loaded(tmp_path) == {"AAAA": task}


def test_marking_a_repeating_task_done_adds_the_next_occurrence(
    tmp_path: Path,
) -> None:
    source = save_task(tmp_path, make_task(due=date(2099, 3, 1), repeat=WEEKLY), None)
    task = replace(source.task, status=Status.DONE, updated=NOW)

    following = save_task_and_next(tmp_path, task, source)

    assert following is not None
    tasks = loaded(tmp_path)
    assert tasks[following.id] == following
    assert following.due == date(2099, 3, 8)
    assert following.repeat == WEEKLY
    assert following.created == following.updated == NOW
    assert tasks["AAAA"] == replace(task, repeat=None)


def test_a_new_task_saved_done_with_a_rule_adds_the_next_occurrence(
    tmp_path: Path,
) -> None:
    task = make_task(status=Status.DONE, repeat=Repeat(1, Unit.DAYS), updated=NOW)

    following = save_task_and_next(tmp_path, task, None)

    assert following is not None
    assert following.due == date.today() + timedelta(days=1)
    tasks = loaded(tmp_path)
    assert set(tasks) == {"AAAA", following.id}
    assert tasks["AAAA"].repeat is None


def test_saving_a_task_that_already_was_done_adds_nothing(tmp_path: Path) -> None:
    source = save_task(tmp_path, make_task(status=Status.DONE, repeat=WEEKLY), None)
    task = replace(source.task, title="Water all plants", updated=NOW)

    assert save_task_and_next(tmp_path, task, source) is None

    assert loaded(tmp_path) == {"AAAA": task}


def test_the_next_occurrence_avoids_the_ids_on_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_task(tmp_path, make_task("BBBB"), None)
    (tmp_path / "CCCC.md").write_text("not a task", encoding="utf-8")
    source = save_task(tmp_path, make_task(repeat=WEEKLY), None)
    seen: list[object] = []

    def fake_new_id(existing: object) -> str:
        seen.append(existing)
        return "DDDD"

    monkeypatch.setattr("tskmngr.models.new_id", fake_new_id)
    task = replace(source.task, status=Status.DONE, updated=NOW)

    following = save_task_and_next(tmp_path, task, source)

    assert following is not None
    assert following.id == "DDDD"
    assert seen == [{"AAAA", "BBBB", "CCCC"}]


def test_a_next_due_date_that_cant_be_computed_saves_nothing(
    tmp_path: Path,
) -> None:
    source = save_task(
        tmp_path,
        make_task(due=date(9999, 12, 1), repeat=Repeat(1, Unit.MONTHS)),
        None,
    )
    task = replace(source.task, status=Status.DONE, updated=NOW)

    with pytest.raises(RecurrenceError):
        save_task_and_next(tmp_path, task, source)

    assert loaded(tmp_path) == {"AAAA": source.task}


def test_a_conflict_saves_nothing(tmp_path: Path) -> None:
    source = save_task(tmp_path, make_task(repeat=WEEKLY), None)
    (tmp_path / "AAAA.md").write_text("---\ntitle: Edited\n---\n", encoding="utf-8")
    task = replace(source.task, status=Status.DONE, updated=NOW)

    with pytest.raises(ConflictError):
        save_task_and_next(tmp_path, task, source)

    assert [path.name for path in tmp_path.iterdir()] == ["AAAA.md"]
