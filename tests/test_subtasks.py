from datetime import UTC, datetime

import pytest

from tskmngr.models import Status, Task
from tskmngr.subtasks import (
    Subtask,
    parse_subtasks,
    progress,
    toggle_subtask,
    uncheck_all,
)

CREATED = datetime(2026, 10, 28, 9, 15, tzinfo=UTC)
NOW = datetime(2026, 11, 4, 10, 0, tzinfo=UTC)


def make_task(notes: str, status: Status = Status.TODO) -> Task:
    return Task(
        id="A",
        title="Plan trip",
        status=status,
        created=CREATED,
        updated=CREATED,
        notes=notes,
    )


def titles(notes: str) -> list[tuple[str, bool]]:
    return [(subtask.title, subtask.done) for subtask in parse_subtasks(notes)]


def test_parse_finds_open_and_checked_items_in_order() -> None:
    notes = "Some notes.\n\n- [x] Book flights\n- [ ] Book hotel\n- [X] Pack\n"

    assert titles(notes) == [
        ("Book flights", True),
        ("Book hotel", False),
        ("Pack", True),
    ]


def test_parse_points_at_the_mark_character() -> None:
    notes = "Intro\n- [ ] Pack\n"

    (subtask,) = parse_subtasks(notes)

    assert subtask == Subtask(title="Pack", done=False, indent=0, mark=9)
    assert notes[subtask.mark] == " "
    assert notes[subtask.mark - 1 : subtask.mark + 2] == "[ ]"


@pytest.mark.parametrize(
    "line", ["- [ ] Pack", "* [ ] Pack", "+ [ ] Pack", "1. [ ] Pack", "12) [ ] Pack"]
)
def test_parse_accepts_bullet_and_ordered_markers(line: str) -> None:
    assert titles(line) == [("Pack", False)]


def test_parse_counts_nested_items_with_their_indent() -> None:
    notes = "- [ ] Trip\n  - [x] Flights\n\t- [ ] Hotel\n"

    assert [(s.title, s.indent) for s in parse_subtasks(notes)] == [
        ("Trip", 0),
        ("Flights", 2),
        ("Hotel", 4),
    ]


@pytest.mark.parametrize(
    "line",
    [
        "- two litres",
        "[ ] no list marker",
        "- [ ]",
        "- [ ]   ",
        "- [ ]no space",
        "-[ ] no space",
        "- [y] other mark",
        "- [  ] two spaces",
        "> - [ ] quoted",
        "text - [ ] in a line",
    ],
)
def test_parse_ignores_lines_that_arent_checklist_items(line: str) -> None:
    assert parse_subtasks(line) == ()


def test_parse_strips_trailing_whitespace_from_titles() -> None:
    assert titles("- [ ] Pack  \t\n") == [("Pack", False)]


def test_parse_ignores_items_in_fenced_code_blocks() -> None:
    notes = (
        "- [ ] Before\n"
        "```markdown\n"
        "- [ ] In backticks\n"
        "~~~\n"
        "- [ ] Still in backticks, a tilde fence doesn't close it\n"
        "```\n"
        "- [ ] Between\n"
        "~~~~\n"
        "- [ ] In tildes\n"
        "~~~ not a closing fence\n"
        "~~~\n"
        "- [ ] Still in tildes, a shorter fence doesn't close it\n"
        "~~~~~\n"
        "- [ ] After\n"
    )

    assert [title for title, _ in titles(notes)] == ["Before", "Between", "After"]


def test_parse_ignores_the_rest_of_an_unclosed_fence() -> None:
    assert titles("- [ ] Before\n```\n- [ ] Inside\n") == [("Before", False)]


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_parse_handles_any_line_ending(newline: str) -> None:
    notes = newline.join(["Intro", "- [ ] One", "- [x] Two", ""])

    subtasks = parse_subtasks(notes)

    assert [(s.title, s.done) for s in subtasks] == [("One", False), ("Two", True)]
    assert [notes[s.mark] for s in subtasks] == [" ", "x"]


def test_parse_without_notes_or_items() -> None:
    assert parse_subtasks("") == ()
    assert parse_subtasks("Just notes.\n") == ()


def test_progress_counts_done_and_total() -> None:
    assert progress(parse_subtasks("- [x] One\n- [ ] Two\n- [X] Three\n")) == "2/3"


def test_progress_is_empty_without_subtasks() -> None:
    assert progress(()) == ""


def test_toggle_checks_an_open_item_and_keeps_the_rest_of_the_notes() -> None:
    notes = "Intro\r\n\r\n- [ ] One  \r\n- [ ] Two\r\n\r\nOutro"
    task = make_task(notes)

    toggled = toggle_subtask(task, 1, NOW)

    assert toggled.notes == "Intro\r\n\r\n- [ ] One  \r\n- [x] Two\r\n\r\nOutro"
    assert toggled.updated == NOW
    assert toggled.status is Status.TODO


def test_toggle_unchecks_a_checked_item() -> None:
    task = make_task("- [X] One\n- [ ] Two\n", Status.DOING)

    toggled = toggle_subtask(task, 0, NOW)

    assert toggled.notes == "- [ ] One\n- [ ] Two\n"
    assert toggled.status is Status.DOING


@pytest.mark.parametrize("status", [Status.TODO, Status.DOING])
def test_checking_the_last_open_item_marks_the_task_done(status: Status) -> None:
    task = make_task("- [x] One\n- [ ] Two\n", status)

    toggled = toggle_subtask(task, 1, NOW)

    assert toggled.status is Status.DONE


def test_unchecking_an_item_of_a_done_task_moves_it_back_to_doing() -> None:
    task = make_task("- [x] One\n- [x] Two\n", Status.DONE)

    toggled = toggle_subtask(task, 0, NOW)

    assert toggled.status is Status.DOING


def test_unchecking_keeps_a_todo_task_todo() -> None:
    task = make_task("- [x] One\n- [ ] Two\n", Status.TODO)

    assert toggle_subtask(task, 0, NOW).status is Status.TODO


def test_toggle_skips_items_in_code_blocks() -> None:
    task = make_task("```\n- [ ] Code\n```\n- [ ] Real\n")

    toggled = toggle_subtask(task, 0, NOW)

    assert toggled.notes == "```\n- [ ] Code\n```\n- [x] Real\n"


@pytest.mark.parametrize("index", [2, -1])
def test_toggle_refuses_a_subtask_that_doesnt_exist(index: int) -> None:
    task = make_task("- [ ] One\n- [ ] Two\n")

    with pytest.raises(IndexError, match="the task has 2"):
        toggle_subtask(task, index, NOW)


def test_uncheck_all_unchecks_every_subtask_and_keeps_the_rest() -> None:
    notes = (
        "Intro [x] not an item\r\n- [x] One\r\n  * [X] Two\r\n- [ ] Three\r\n"
        "```\r\n- [x] Code\r\n```\r\n"
    )

    assert uncheck_all(notes) == (
        "Intro [x] not an item\r\n- [ ] One\r\n  * [ ] Two\r\n- [ ] Three\r\n"
        "```\r\n- [x] Code\r\n```\r\n"
    )


def test_uncheck_all_without_subtasks_changes_nothing() -> None:
    assert uncheck_all("Just notes.\n") == "Just notes.\n"
