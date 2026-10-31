import dataclasses
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from tskmngr.models import Priority, Status, Task
from tskmngr.taskfile import MalformedTaskError, TaskFile, parse, render

CREATED = datetime(2026, 10, 28, 9, 15, tzinfo=UTC)
FALLBACK = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)

DOCUMENTED = """\
---
title: Buy milk
status: todo          # todo | doing | done
priority: normal      # low | normal | high
due: 2026-11-01       # optional, ISO date
tags: [errands]
created: 2026-10-28T09:15:00Z
updated: 2026-10-28T09:15:00Z
---

Notes go here, in **Markdown**.
"""


def make_task(**overrides: object) -> Task:
    fields: dict[str, object] = {
        "id": "01JB3K7Q2X",
        "title": "Buy milk",
        "created": CREATED,
        "updated": CREATED,
    }
    fields.update(overrides)
    return Task(**fields)


def load(text: str, task_id: str = "01JB3K7Q2X") -> TaskFile:
    return parse(text, task_id, fallback_time=FALLBACK)


def edit(text: str, **changes: object) -> str:
    """Parse `text`, change fields of its task and render it back."""
    source = load(text)
    return render(dataclasses.replace(source.task, **changes), source)


def assert_malformed(
    text: str, field: str | None = None, line: int | None = None
) -> MalformedTaskError:
    with pytest.raises(MalformedTaskError) as excinfo:
        load(text)
    assert excinfo.value.field == field
    assert excinfo.value.line == line
    return excinfo.value


# Parsing


def test_parse_documented_example() -> None:
    task = load(DOCUMENTED).task

    assert task == make_task(
        due=date(2026, 11, 1),
        tags=("errands",),
        notes="Notes go here, in **Markdown**.\n",
    )


def test_parse_keeps_the_text() -> None:
    assert load(DOCUMENTED).text == DOCUMENTED


def test_parse_takes_the_id_from_the_caller() -> None:
    assert load(DOCUMENTED, task_id="my-task").task.id == "my-task"


def test_parse_with_only_a_title_uses_defaults() -> None:
    task = load("---\ntitle: Buy milk\n---\n").task

    assert task.status is Status.TODO
    assert task.priority is Priority.NORMAL
    assert task.due is None
    assert task.tags == ()
    assert task.notes == ""


def test_parse_uses_the_fallback_for_missing_timestamps() -> None:
    task = load("---\ntitle: Buy milk\n---\n").task

    assert task.created == FALLBACK
    assert task.updated == FALLBACK


def test_parse_uses_the_fallback_only_for_the_missing_timestamp() -> None:
    task = load("---\ntitle: Buy milk\ncreated: 2026-10-28T09:15:00Z\n---\n").task

    assert task.created == CREATED
    assert task.updated == FALLBACK


def test_parse_reads_status_and_priority() -> None:
    task = load("---\ntitle: x\nstatus: doing\npriority: high\n---\n").task

    assert task.status is Status.DOING
    assert task.priority is Priority.HIGH


def test_parse_keeps_the_timezone_offset() -> None:
    task = load("---\ntitle: x\ncreated: 2026-10-28T10:15:00+01:00\n---\n").task

    assert task.created.utcoffset() == timedelta(hours=1)
    assert task.created == CREATED


def test_parse_returns_plain_python_types() -> None:
    task = load(
        "---\ntitle: \"Buy milk\"\ntags: ['a']\ncreated: 2026-10-28T09:15:00Z\n---\n"
    ).task

    assert type(task.title) is str
    assert type(task.tags[0]) is str
    assert type(task.created) is datetime


def test_parse_lowercases_tags() -> None:
    assert load("---\ntitle: x\ntags: [Errands, HOME]\n---\n").task.tags == (
        "errands",
        "home",
    )


@pytest.mark.parametrize("value", ["", "~", "null", "[]"])
def test_parse_empty_tags(value: str) -> None:
    assert load(f"---\ntitle: x\ntags: {value}\n---\n").task.tags == ()


@pytest.mark.parametrize("value", ["~", "null"])
def test_parse_empty_due(value: str) -> None:
    assert load(f"---\ntitle: x\ndue: {value}\n---\n").task.due is None


def test_parse_quoted_title_that_looks_like_a_number() -> None:
    assert load('---\ntitle: "1.10"\n---\n').task.title == "1.10"


def test_parse_notes_without_a_blank_line_after_the_frontmatter() -> None:
    assert load("---\ntitle: x\n---\nNotes\n").task.notes == "Notes\n"


def test_parse_strips_only_one_blank_line_before_the_notes() -> None:
    assert load("---\ntitle: x\n---\n\n\nNotes\n").task.notes == "\nNotes\n"


def test_parse_keeps_delimiter_lines_in_the_notes() -> None:
    text = "---\ntitle: x\n---\n\nAbove\n\n---\n\nBelow\n"

    assert load(text).task.notes == "Above\n\n---\n\nBelow\n"


def test_parse_windows_line_endings() -> None:
    task = load("---\r\ntitle: Buy milk\r\n---\r\n\r\nNotes\r\n").task

    assert task.title == "Buy milk"
    assert task.notes == "Notes\r\n"


def test_parse_old_mac_line_endings() -> None:
    task = load("---\rtitle: Buy milk\r---\r\rNotes\r").task

    assert task.title == "Buy milk"
    assert task.notes == "Notes\r"


def test_parse_mixed_line_endings_in_the_frontmatter() -> None:
    assert load("---\rtitle: Buy milk\n---\n").task.title == "Buy milk"


def test_parse_ignores_unknown_keys() -> None:
    assert load("---\ntitle: x\nid: other\nproject: home\n---\n").task.id == (
        "01JB3K7Q2X"
    )


# Rendering a new file


def test_render_new_task_in_the_documented_format() -> None:
    task = make_task(
        due=date(2026, 11, 1),
        tags=("errands",),
        notes="Notes go here, in **Markdown**.\n",
    )

    assert render(task) == (
        "---\n"
        "title: Buy milk\n"
        "status: todo\n"
        "priority: normal\n"
        "due: 2026-11-01\n"
        "tags: [errands]\n"
        "created: 2026-10-28T09:15:00Z\n"
        "updated: 2026-10-28T09:15:00Z\n"
        "---\n"
        "\n"
        "Notes go here, in **Markdown**.\n"
    )


def test_render_without_due_or_notes() -> None:
    text = render(make_task())

    assert "due:" not in text
    assert text.endswith("updated: 2026-10-28T09:15:00Z\n---\n")


def test_render_does_not_write_the_id() -> None:
    assert "01JB3K7Q2X" not in render(make_task())


def test_render_empty_tags_as_a_flow_list() -> None:
    assert "tags: []\n" in render(make_task())


def test_render_timestamp_with_an_offset() -> None:
    cet = timezone(timedelta(hours=1))
    task = make_task(created=datetime(2026, 10, 28, 10, 15, tzinfo=cet))

    assert "created: 2026-10-28T10:15:00+01:00\n" in render(task)


@pytest.mark.parametrize(
    "task",
    [
        make_task(),
        make_task(
            status=Status.DONE,
            priority=Priority.LOW,
            due=date(2026, 11, 1),
            tags=("a", "b"),
            notes="Line\n\n---\n\nMore",
        ),
        make_task(title="1.10"),
        make_task(title="yes"),
        make_task(title="2026-11-01"),
        make_task(title="Title: with colon # and hash"),
        make_task(title="  spaces  "),
        make_task(title="x" * 200),
        make_task(tags=("1.10", "null")),
        make_task(created=CREATED.replace(microsecond=123456)),
        make_task(updated=datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=-5)))),
    ],
)
def test_render_then_parse_round_trips(task: Task) -> None:
    assert load(render(task)).task == task


def test_render_writes_a_long_title_on_one_line() -> None:
    title = " ".join(["word"] * 50)

    assert f"title: {title}\n" in render(make_task(title=title))


# Rendering an edited file


HAND_EDITED = """\
---
# A comment at the top
title: Buy milk   # inline comment
status: todo
project:
    name: 'home'
    order: 3
tags:
- Errands
- shop
---


Notes
  with odd   spacing
"""


@pytest.mark.parametrize(
    "text",
    [
        DOCUMENTED,
        HAND_EDITED,
        "---\ntitle: Buy milk\n---\n",
        "---\r\ntitle: Buy milk\r\n---\r\n\r\nNotes\r\n",
        "---\rtitle: Buy milk\r---\r\rNotes\r",
        "---\ntitle: x\n---\nNo trailing newline",
    ],
)
def test_unchanged_task_renders_byte_for_byte(text: str) -> None:
    source = load(text)

    assert render(source.task, source) == text


def test_unchanged_task_with_fallback_timestamps_is_not_rewritten() -> None:
    source = load("---\ntitle: Buy milk\n---\n")

    assert render(source.task, source) == "---\ntitle: Buy milk\n---\n"


def test_edit_keeps_comments_and_unknown_keys() -> None:
    text = edit(HAND_EDITED, status=Status.DONE)

    assert "# A comment at the top\n" in text
    assert "title: Buy milk   # inline comment\n" in text
    assert "status: done\n" in text
    assert "name: 'home'" in text
    assert "order: 3" in text
    assert load(text).task.status is Status.DONE


def test_edit_keeps_unchanged_values_as_written() -> None:
    # The model lowercases tags, but unchanged tags stay as written.
    assert "- Errands\n- shop\n" in edit(HAND_EDITED, status=Status.DONE)


def test_edit_only_notes_keeps_the_frontmatter_byte_for_byte() -> None:
    text = edit(HAND_EDITED, notes="New notes\n")

    header = HAND_EDITED[: HAND_EDITED.index("---\n", 4) + 4]
    assert text == header + "\nNew notes\n"


def test_edit_only_frontmatter_keeps_the_notes_byte_for_byte() -> None:
    text = edit(HAND_EDITED, priority=Priority.HIGH)

    assert text.endswith("---\n\n\nNotes\n  with odd   spacing\n")


def test_edit_clearing_notes() -> None:
    assert edit(DOCUMENTED, notes="").endswith("updated: 2026-10-28T09:15:00Z\n---\n")


def test_edit_adding_notes() -> None:
    assert edit("---\ntitle: x\n---\n", notes="Hi\n") == "---\ntitle: x\n---\n\nHi\n"


def test_edit_adds_missing_fields_in_the_documented_order() -> None:
    text = edit("---\ntitle: Buy milk\nproject: home\n---\n", status=Status.DONE)

    assert text == (
        "---\n"
        "title: Buy milk\n"
        "status: done\n"
        "priority: normal\n"
        "tags: []\n"
        "created: 2026-10-30T12:00:00Z\n"
        "updated: 2026-10-30T12:00:00Z\n"
        "project: home\n"
        "---\n"
    )


def test_edit_setting_due_adds_it() -> None:
    text = edit(
        DOCUMENTED.replace("due: 2026-11-01       # optional, ISO date\n", ""),
        due=date(2026, 12, 24),
    )

    assert "priority: normal      # low | normal | high\ndue: 2026-12-24\n" in text


def test_edit_clearing_due_removes_it() -> None:
    text = edit(DOCUMENTED, due=None)

    assert "due" not in text
    assert load(text).task.due is None


def test_edit_changing_due() -> None:
    assert "due: 2026-12-24" in edit(DOCUMENTED, due=date(2026, 12, 24))


def test_edit_tags_keeps_flow_style() -> None:
    assert "tags: [errands, home]\n" in edit(DOCUMENTED, tags=("errands", "home"))


def test_edit_tags_keeps_block_style() -> None:
    assert "tags:\n- errands\n- home\n" in edit(HAND_EDITED, tags=("errands", "home"))


def test_edit_title_that_needs_quotes() -> None:
    text = edit(DOCUMENTED, title="1.10")

    assert load(text).task.title == "1.10"


def test_edit_updated_timestamp() -> None:
    later = datetime(2026, 10, 29, 8, 0, tzinfo=UTC)

    text = edit(DOCUMENTED, updated=later)

    assert "created: 2026-10-28T09:15:00Z\n" in text
    assert "updated: 2026-10-29T08:00:00Z\n" in text


def test_edit_ignores_a_changed_id() -> None:
    # The ID is the filename; renaming the file is storage's job.
    source = load(DOCUMENTED)

    assert render(dataclasses.replace(source.task, id="OTHER"), source) == DOCUMENTED


# Malformed files


@pytest.mark.parametrize("text", ["", "title: x\n", "\n---\ntitle: x\n---\n"])
def test_malformed_without_opening_delimiter(text: str) -> None:
    assert_malformed(text, line=1)


def test_malformed_without_closing_delimiter() -> None:
    assert_malformed("---\ntitle: x\n")


def test_malformed_yaml_reports_the_line() -> None:
    error = assert_malformed("---\ntitle: x\nstatus: [todo\n---\n", line=4)

    assert "invalid YAML" in str(error)


@pytest.mark.parametrize("frontmatter", ["- a\n- b\n", "just text\n"])
def test_malformed_when_frontmatter_is_not_a_mapping(frontmatter: str) -> None:
    assert_malformed(f"---\n{frontmatter}---\n")


@pytest.mark.parametrize("text", ["---\n---\n", "---\nstatus: todo\n---\n"])
def test_malformed_without_title(text: str) -> None:
    error = assert_malformed(text, field="title")

    assert str(error) == "title: missing"


@pytest.mark.parametrize(
    ("value", "described"),
    [
        ("1.10", "the number 1.1"),
        ("42", "the number 42"),
        ("true", "the boolean true"),
        ("2026-11-01", "a date"),
    ],
)
def test_malformed_title_of_wrong_type_suggests_quotes(
    value: str, described: str
) -> None:
    error = assert_malformed(f"---\nstatus: todo\ntitle: {value}\n---\n", "title", 3)

    assert str(error) == (
        f"line 3: title: expected text, got {described}; "
        "if it's meant as text, put it in quotes"
    )


@pytest.mark.parametrize("value", ["", "[a]", "{a: 1}"])
def test_malformed_title_that_is_not_a_scalar(value: str) -> None:
    error = assert_malformed(f"---\ntitle: {value}\n---\n", "title", 2)

    assert "quotes" not in error.message


@pytest.mark.parametrize("value", ["'  '", "|\n  two\n  lines"])
def test_malformed_title_failing_model_validation(value: str) -> None:
    assert_malformed(f"---\ntitle: {value}\n---\n", "title", 2)


@pytest.mark.parametrize("field", ["status", "priority"])
def test_malformed_unknown_choice(field: str) -> None:
    error = assert_malformed(f"---\ntitle: x\n{field}: Urgent\n---\n", field, 3)

    assert "unknown value 'Urgent'" in error.message


def test_malformed_choice_of_wrong_type() -> None:
    error = assert_malformed("---\ntitle: x\nstatus: 1\n---\n", "status", 3)

    assert "quotes" in error.message


@pytest.mark.parametrize("value", ["tomorrow", "'2026-11-01'", "2026-11-1"])
def test_malformed_due_text(value: str) -> None:
    error = assert_malformed(f"---\ntitle: x\ndue: {value}\n---\n", "due", 3)

    assert "expected a date like 2026-11-01" in error.message


def test_malformed_due_with_a_time() -> None:
    assert_malformed("---\ntitle: x\ndue: 2026-11-01T10:00:00Z\n---\n", "due", 3)


@pytest.mark.parametrize("value", ["errands", "{a: 1}"])
def test_malformed_tags_not_a_list(value: str) -> None:
    error = assert_malformed(f"---\ntitle: x\ntags: {value}\n---\n", "tags", 3)

    assert "expected a list" in error.message


def test_malformed_tag_of_wrong_type_suggests_quotes() -> None:
    error = assert_malformed("---\ntitle: x\ntags: [a, 2026]\n---\n", "tags", 3)

    assert "the number 2026" in error.message
    assert "quotes" in error.message


@pytest.mark.parametrize("value", ["[a, A]", "['two words']", "[[a]]"])
def test_malformed_tags_failing_model_validation(value: str) -> None:
    assert_malformed(f"---\ntitle: x\ntags: {value}\n---\n", "tags", 3)


@pytest.mark.parametrize("field", ["created", "updated"])
@pytest.mark.parametrize(
    "value", ["'2026-10-28T09:15:00Z'", "2026-10-28", "2026-10-28 09:15:00", "1"]
)
def test_malformed_timestamp(field: str, value: str) -> None:
    assert_malformed(f"---\ntitle: x\n{field}: {value}\n---\n", field, 3)


def test_malformed_naive_timestamp_says_why() -> None:
    error = assert_malformed(
        "---\ntitle: x\ncreated: 2026-10-28T09:15:00\n---\n", "created", 3
    )

    assert error.message == "must include a timezone"


def test_malformed_line_numbers_count_from_the_file_start() -> None:
    text = "---\n# comment\n\ntitle: x\npriority: urgent\n---\n"

    assert_malformed(text, "priority", 5)


def test_taskfile_does_not_import_textual() -> None:
    code = "import sys, tskmngr.taskfile; sys.exit('textual' in sys.modules)"

    subprocess.run([sys.executable, "-c", code], check=True)
