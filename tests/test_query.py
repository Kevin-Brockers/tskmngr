import subprocess
import sys
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from tskmngr.models import Priority, Status, Task
from tskmngr.query import (
    AmbiguousIDError,
    SortKey,
    TaskFilter,
    TaskNotFoundError,
    allowed_edits,
    edit_distance,
    filter_tasks,
    find_by_prefix,
    is_typo_of,
    match_id_prefix,
    parse_filter,
    sort_tasks,
    suggest_filter,
    values_starting_with,
)
from tskmngr.taskfile import TaskFile

CREATED = datetime(2026, 10, 28, 9, 15, tzinfo=UTC)


def make_task(task_id: str, **overrides: object) -> Task:
    fields: dict[str, object] = {
        "id": task_id,
        "title": f"Task {task_id}",
        "created": CREATED,
        "updated": CREATED,
    }
    fields.update(overrides)
    return Task(**fields)


def ids(tasks: list[Task]) -> list[str]:
    return [task.id for task in tasks]


def test_query_does_not_import_textual() -> None:
    code = "import sys, tskmngr.query; print('textual' in sys.modules)"
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )

    assert result.stdout.strip() == "False"


# Filtering


def test_filter_without_criteria_keeps_all_tasks_in_order() -> None:
    tasks = [make_task("B"), make_task("A")]

    assert filter_tasks(tasks) == tasks


def test_filter_by_status_matches_any_given_status() -> None:
    tasks = [
        make_task("A", status=Status.TODO),
        make_task("B", status=Status.DOING),
        make_task("C", status=Status.DONE),
    ]

    result = filter_tasks(tasks, statuses={Status.TODO, Status.DOING})

    assert ids(result) == ["A", "B"]


def test_filter_by_priority_matches_any_given_priority() -> None:
    tasks = [
        make_task("A", priority=Priority.LOW),
        make_task("B", priority=Priority.NORMAL),
        make_task("C", priority=Priority.HIGH),
    ]

    result = filter_tasks(tasks, priorities=[Priority.HIGH, Priority.LOW])

    assert ids(result) == ["A", "C"]


def test_filter_by_tags_requires_all_given_tags() -> None:
    tasks = [
        make_task("A", tags=["work"]),
        make_task("B", tags=["work", "urgent"]),
        make_task("C", tags=["urgent", "home", "work"]),
        make_task("D"),
    ]

    result = filter_tasks(tasks, tags=["work", "urgent"])

    assert ids(result) == ["B", "C"]


def test_filter_by_tags_ignores_case() -> None:
    tasks = [make_task("A", tags=["work"]), make_task("B")]

    assert ids(filter_tasks(tasks, tags=["Work"])) == ["A"]


def test_filter_by_tags_matches_the_start_of_a_tag() -> None:
    tasks = [
        make_task("A", tags=["errands"]),
        make_task("B", tags=["err"]),
        make_task("C", tags=["work", "ferry"]),
        make_task("D"),
    ]

    assert ids(filter_tasks(tasks, tags=["err"])) == ["A", "B"]
    assert ids(filter_tasks(tasks, tags=["ERR"])) == ["A", "B"]
    assert ids(filter_tasks(tasks, tags=["shopping"])) == []


def test_each_tag_prefix_needs_a_tag_starting_with_it() -> None:
    tasks = [
        make_task("A", tags=["errands", "phone"]),
        make_task("B", tags=["errands"]),
        make_task("C", tags=["phone"]),
    ]

    assert ids(filter_tasks(tasks, tags=["err", "ph"])) == ["A"]
    # One tag may start several prefixes.
    assert ids(filter_tasks(tasks, tags=["e", "err"])) == ["A", "B"]


def test_filter_combines_criteria_with_and() -> None:
    tasks = [
        make_task("A", status=Status.TODO, priority=Priority.HIGH, tags=["work"]),
        make_task("B", status=Status.DONE, priority=Priority.HIGH, tags=["work"]),
        make_task("C", status=Status.TODO, priority=Priority.LOW, tags=["work"]),
        make_task("D", status=Status.TODO, priority=Priority.HIGH),
    ]

    result = filter_tasks(
        tasks, statuses=[Status.TODO], priorities=[Priority.HIGH], tags=["work"]
    )

    assert ids(result) == ["A"]


# Text search


def test_search_matches_title_and_notes_ignoring_case() -> None:
    tasks = [
        make_task("A", title="Buy MILK"),
        make_task("B", notes="Remember the milk.\n"),
        make_task("C", title="Buy bread"),
    ]

    assert ids(filter_tasks(tasks, text="milk")) == ["A", "B"]


def test_search_needs_every_word_in_any_order() -> None:
    tasks = [
        make_task("A", title="Buy oat milk"),
        make_task("B", title="Buy bread"),
        make_task("C", title="Milk", notes="buy at the market\n"),
    ]

    assert ids(filter_tasks(tasks, text="milk  buy")) == ["A", "C"]


def test_search_matches_part_of_a_word() -> None:
    tasks = [make_task("A", title="Groceries")]

    assert ids(filter_tasks(tasks, text="grocer")) == ["A"]


# Typos (M9.1b)


@pytest.mark.parametrize(
    ("a", "b", "distance"),
    [
        ("milk", "milk", 0),
        ("mlik", "milk", 1),
        ("milc", "milk", 1),
        ("mil", "milk", 1),
        ("milkk", "milk", 1),
        ("reprot", "report", 1),
        ("rpeort", "report", 1),
        ("rpeotr", "report", 2),
        ("quartely", "quarterly", 1),
        ("", "abc", 3),
        ("kitten", "sitting", 3),
    ],
)
def test_edit_distance(a: str, b: str, distance: int) -> None:
    assert edit_distance(a, b) == distance
    assert edit_distance(b, a) == distance


@pytest.mark.parametrize(
    ("word", "edits"),
    [("a", 0), ("buy", 0), ("milk", 1), ("lisbon", 1), ("dentist", 1), ("quartely", 2)],
)
def test_allowed_edits_grow_with_the_word(word: str, edits: int) -> None:
    assert allowed_edits(word) == edits


@pytest.mark.parametrize(
    ("word", "other", "expected"),
    [
        ("mlik", "milk", True),
        ("reprot", "report", True),
        ("lisbn", "lisbon", True),
        ("quartely", "quarterly", True),
        ("quartrly", "quarterly", True),
        ("qartrly", "quarterly", False),
        ("qaurtrly", "quarterly", True),
        ("qrtrly", "quarterly", False),
        ("mlki", "milk", False),
        ("bus", "buy", False),
        ("milk", "milk", True),
        ("milk", "milkshake", False),
    ],
)
def test_is_typo_of(word: str, other: str, expected: bool) -> None:
    assert is_typo_of(word, other) is expected


def test_search_matches_a_word_with_a_typo() -> None:
    tasks = [
        make_task("A", title="Buy milk"),
        make_task("B", title="Write report", notes="For the quarterly review."),
        make_task("C", title="Mile run"),
        make_task("D", title="Read"),
    ]

    assert ids(filter_tasks(tasks, text="mlik")) == ["A"]
    assert ids(filter_tasks(tasks, text="Reprot QUARTELY")) == ["B"]
    # Any typo tolerance also finds real words one letter apart.
    assert ids(filter_tasks(tasks, text="milk")) == ["A", "C"]


def test_short_words_need_to_match_exactly() -> None:
    tasks = [make_task("A", title="Buy milk"), make_task("B", title="Take the bus")]

    assert ids(filter_tasks(tasks, text="buy")) == ["A"]
    assert ids(filter_tasks(tasks, text="byu")) == []


def test_a_typo_matches_a_whole_word_not_part_of_one() -> None:
    tasks = [make_task("A", title="Milkshake"), make_task("B", title="milk-shake")]

    assert ids(filter_tasks(tasks, text="mlik")) == ["B"]
    assert ids(filter_tasks(tasks, text="mil")) == ["A", "B"]


def test_every_word_still_has_to_match_with_or_without_a_typo() -> None:
    tasks = [make_task("A", title="Buy milk"), make_task("B", title="Buy bread")]

    assert ids(filter_tasks(tasks, text="mlik buy")) == ["A"]
    assert ids(filter_tasks(tasks, text="mlik braed")) == []


def test_a_tag_with_a_typo_matches() -> None:
    tasks = [
        make_task("A", tags=["errands"]),
        make_task("B", tags=["errand"]),
        make_task("C", tags=["work"]),
    ]

    # Two edits from errand, and 6 letters may have only one.
    assert ids(filter_tasks(tasks, tags=["erands"])) == ["A"]
    assert ids(filter_tasks(tasks, tags=["erand"])) == ["B"]
    assert ids(filter_tasks(tasks, tags=["wrok"])) == ["C"]
    # Three letters or fewer must still be the start of a tag.
    assert ids(filter_tasks(tasks, tags=["wro"])) == []


def test_search_does_not_match_across_title_and_notes() -> None:
    tasks = [make_task("A", title="Buy", notes="milk\n")]

    assert filter_tasks(tasks, text="buymilk") == []


def test_blank_search_matches_all_tasks() -> None:
    tasks = [make_task("A"), make_task("B")]

    assert filter_tasks(tasks, text="   ") == tasks


# Filter strings


def test_parse_filter_of_a_blank_string_matches_everything() -> None:
    assert parse_filter("") == (TaskFilter(), [])
    assert parse_filter("  \t ") == (TaskFilter(), [])


def test_parse_filter_reads_words_tags_statuses_and_priorities() -> None:
    task_filter = TaskFilter(
        statuses=(Status.TODO,),
        priorities=(Priority.HIGH,),
        tags=("errands",),
        text="buy milk",
    )

    assert parse_filter("buy #errands status:todo milk priority:high") == (
        task_filter,
        [],
    )


def test_parse_filter_collects_repeated_criteria_without_duplicates() -> None:
    task_filter, errors = parse_filter(
        "status:todo status:doing status:todo priority:low priority:high #a #b #a"
    )

    assert task_filter == TaskFilter(
        statuses=(Status.TODO, Status.DOING),
        priorities=(Priority.LOW, Priority.HIGH),
        tags=("a", "b"),
    )
    assert errors == []


def test_parse_filter_ignores_case_of_keys_values_and_tags() -> None:
    assert parse_filter("Status:DOING PRIORITY:Low #Errands #errands")[0] == (
        TaskFilter(
            statuses=(Status.DOING,), priorities=(Priority.LOW,), tags=("errands",)
        )
    )


def test_parse_filter_searches_other_key_value_words_as_text() -> None:
    # Titles like "Re: invoice" or "10:30 call" are searched as written.
    assert parse_filter("re:invoice 10:30") == (TaskFilter(text="re:invoice 10:30"), [])


def test_parse_filter_takes_the_start_of_a_status_or_priority() -> None:
    task_filter, errors = parse_filter("status:do priority:H #Err")

    assert errors == []
    assert task_filter == TaskFilter(
        statuses=(Status.DOING, Status.DONE),
        priorities=(Priority.HIGH,),
        tags=("err",),
    )


def test_parse_filter_keeps_each_value_once_when_prefixes_overlap() -> None:
    task_filter = parse_filter("status:done status:d status:t")[0]

    assert task_filter.statuses == (Status.DONE, Status.DOING, Status.TODO)


def test_a_status_prefix_filters_like_its_values() -> None:
    tasks = [
        make_task("A", status=Status.TODO),
        make_task("B", status=Status.DOING),
        make_task("C", status=Status.DONE),
    ]

    assert ids(parse_filter("status:do")[0].apply(tasks)) == ["B", "C"]


@pytest.mark.parametrize(
    ("prefix", "values"),
    [
        ("do", [Status.DOING, Status.DONE]),
        ("D", [Status.DOING, Status.DONE]),
        ("todo", [Status.TODO]),
        ("todos", []),
        ("x", []),
        ("", []),
    ],
)
def test_values_starting_with(prefix: str, values: list[Status]) -> None:
    assert values_starting_with(Status, prefix) == values


def test_parse_filter_takes_everything_after_hash_as_the_tag() -> None:
    assert parse_filter("#status:todo ##x")[0] == TaskFilter(tags=("status:todo", "#x"))


@pytest.mark.parametrize(
    ("word", "message"),
    [
        ("status:later", "unknown status 'later'; use todo, doing or done"),
        ("priority:urgent", "unknown priority 'urgent'; use low, normal or high"),
        ("status:", "status: needs a value; use todo, doing or done"),
        ("priority:", "priority: needs a value; use low, normal or high"),
        ("#", "'#' needs a tag after it, as in #errands"),
    ],
)
def test_parse_filter_leaves_out_invalid_words_and_says_why(
    word: str, message: str
) -> None:
    task_filter, errors = parse_filter(f"milk {word} #errands status:todo")

    assert task_filter == TaskFilter(
        statuses=(Status.TODO,), tags=("errands",), text="milk"
    )
    assert errors == [message]


def test_parse_filter_reports_every_invalid_word_in_order() -> None:
    assert parse_filter("priority:x # status:y")[1] == [
        "unknown priority 'x'; use low, normal or high",
        "'#' needs a tag after it, as in #errands",
        "unknown status 'y'; use todo, doing or done",
    ]


def test_task_filter_applies_its_criteria() -> None:
    tasks = [
        make_task("A", title="Buy milk", tags=("errands",)),
        make_task("B", title="Buy milk", status=Status.DONE, tags=("errands",)),
        make_task("C", title="Buy milk"),
        make_task("D", title="Buy bread", tags=("errands",)),
    ]

    assert ids(parse_filter("milk #errands status:todo")[0].apply(tasks)) == ["A"]
    assert TaskFilter().apply(tasks) == tasks


# Sorting


def test_sort_by_due_soonest_first_and_undated_last() -> None:
    tasks = [
        make_task("A"),
        make_task("B", due=date(2026, 11, 5)),
        make_task("C", due=date(2026, 11, 1)),
    ]

    assert ids(sort_tasks(tasks, SortKey.DUE)) == ["C", "B", "A"]


def test_sort_by_due_reversed_keeps_undated_last() -> None:
    tasks = [
        make_task("A"),
        make_task("B", due=date(2026, 11, 1)),
        make_task("C", due=date(2026, 11, 5)),
    ]

    assert ids(sort_tasks(tasks, SortKey.DUE, reverse=True)) == ["C", "B", "A"]


def test_sort_by_priority_highest_first() -> None:
    tasks = [
        make_task("A", priority=Priority.LOW),
        make_task("B", priority=Priority.HIGH),
        make_task("C", priority=Priority.NORMAL),
    ]

    assert ids(sort_tasks(tasks, SortKey.PRIORITY)) == ["B", "C", "A"]
    assert ids(sort_tasks(tasks, SortKey.PRIORITY, reverse=True)) == ["A", "C", "B"]


def test_sort_by_status_doing_then_todo_then_done() -> None:
    tasks = [
        make_task("A", status=Status.DONE),
        make_task("B", status=Status.TODO),
        make_task("C", status=Status.DOING),
    ]

    assert ids(sort_tasks(tasks, SortKey.STATUS)) == ["C", "B", "A"]
    assert ids(sort_tasks(tasks, SortKey.STATUS, reverse=True)) == ["A", "B", "C"]


def test_sort_by_status_breaks_ties_by_created_then_id() -> None:
    tasks = [
        make_task("B", status=Status.TODO),
        make_task("A", status=Status.TODO, created=CREATED + timedelta(hours=1)),
        make_task("C", status=Status.TODO),
        make_task("D", status=Status.DOING),
    ]

    assert ids(sort_tasks(tasks, SortKey.STATUS)) == ["D", "B", "C", "A"]
    assert ids(sort_tasks(tasks, SortKey.STATUS, reverse=True)) == [
        "B",
        "C",
        "A",
        "D",
    ]


@pytest.mark.parametrize("key", [SortKey.CREATED, SortKey.UPDATED])
def test_sort_by_timestamp_oldest_first(key: SortKey) -> None:
    later = CREATED + timedelta(days=1)
    earlier = CREATED - timedelta(days=1)
    tasks = [
        make_task("A", **{key.value: later}),
        make_task("B", **{key.value: earlier}),
        make_task("C"),
    ]

    assert ids(sort_tasks(tasks, key)) == ["B", "C", "A"]
    assert ids(sort_tasks(tasks, key, reverse=True)) == ["A", "C", "B"]


def test_sort_compares_timestamps_across_timezones() -> None:
    # 10:15 at UTC+2 is 08:15 UTC, an hour before CREATED (09:15 UTC).
    plus_two = datetime(2026, 10, 28, 10, 15, tzinfo=timezone(timedelta(hours=2)))
    tasks = [make_task("B"), make_task("A", created=plus_two)]

    assert ids(sort_tasks(tasks, SortKey.CREATED)) == ["A", "B"]


def test_sort_breaks_ties_by_created_then_id() -> None:
    due = date(2026, 11, 1)
    tasks = [
        make_task("C", due=due),
        make_task("B", due=due),
        make_task("A", due=due, created=CREATED + timedelta(hours=1)),
        make_task("Z"),
        make_task("Y"),
    ]

    assert ids(sort_tasks(tasks, SortKey.DUE)) == ["B", "C", "A", "Y", "Z"]


def test_reverse_sort_keeps_tie_breaks_ascending() -> None:
    tasks = [
        make_task("B", priority=Priority.HIGH),
        make_task("A", priority=Priority.HIGH),
        make_task("C", priority=Priority.LOW),
    ]

    assert ids(sort_tasks(tasks, SortKey.PRIORITY, reverse=True)) == ["C", "A", "B"]


def test_sort_returns_a_new_list() -> None:
    tasks = [make_task("B"), make_task("A")]

    sort_tasks(tasks, SortKey.CREATED)

    assert ids(tasks) == ["B", "A"]


# ID prefix lookup

IDS = ["01JB3K7Q2X", "01JB3M0000", "7Z9A000000"]


def test_find_by_unique_prefix() -> None:
    tasks = [make_task(task_id) for task_id in IDS]

    assert find_by_prefix(tasks, "01JB3K").id == "01JB3K7Q2X"
    assert find_by_prefix(tasks, "7").id == "7Z9A000000"


def test_find_by_full_id() -> None:
    tasks = [make_task(task_id) for task_id in IDS]

    assert find_by_prefix(tasks, "01JB3M0000").id == "01JB3M0000"


def test_find_by_prefix_ignores_case() -> None:
    tasks = [make_task(task_id) for task_id in IDS]

    assert find_by_prefix(tasks, "01jb3k").id == "01JB3K7Q2X"


def test_find_by_prefix_prefers_an_exact_match() -> None:
    tasks = [make_task("todo"), make_task("todo-old")]

    assert find_by_prefix(tasks, "TODO").id == "todo"


def test_find_by_prefix_prefers_an_exact_match_with_the_same_case() -> None:
    tasks = [make_task("abc"), make_task("ABC"), make_task("abcd")]

    assert find_by_prefix(tasks, "ABC").id == "ABC"


def test_find_by_ambiguous_prefix_lists_the_candidates() -> None:
    tasks = [make_task(task_id) for task_id in IDS]

    with pytest.raises(AmbiguousIDError) as excinfo:
        find_by_prefix(tasks, "01jb3")

    assert excinfo.value.ids == ["01JB3K7Q2X", "01JB3M0000"]
    assert "01JB3K7Q2X, 01JB3M0000" in str(excinfo.value)


def test_find_by_prefix_with_two_exact_matches_differing_in_case_is_ambiguous() -> None:
    tasks = [make_task("abc"), make_task("ABC")]

    with pytest.raises(AmbiguousIDError) as excinfo:
        find_by_prefix(tasks, "Abc")

    assert excinfo.value.ids == ["ABC", "abc"]


def test_find_by_unknown_prefix() -> None:
    tasks = [make_task(task_id) for task_id in IDS]

    with pytest.raises(TaskNotFoundError) as excinfo:
        find_by_prefix(tasks, "XYZ")

    assert excinfo.value.prefix == "XYZ"


@pytest.mark.parametrize("prefix", ["", "  "])
def test_find_by_blank_prefix_is_an_error(prefix: str) -> None:
    with pytest.raises(ValueError, match="blank"):
        find_by_prefix([make_task("A")], prefix)


def test_match_id_prefix_looks_up_plain_ids() -> None:
    assert match_id_prefix(IDS, "01jb3k") == "01JB3K7Q2X"
    assert match_id_prefix(["todo", "todo-old"], "TODO") == "todo"


def test_match_id_prefix_raises_the_same_errors() -> None:
    with pytest.raises(AmbiguousIDError):
        match_id_prefix(IDS, "01JB3")
    with pytest.raises(TaskNotFoundError):
        match_id_prefix(IDS, "XYZ")
    with pytest.raises(ValueError, match="blank"):
        match_id_prefix(IDS, "")


# Task files


def test_functions_accept_and_return_task_files() -> None:
    files = [
        TaskFile(make_task("B", priority=Priority.LOW, tags=["work"]), "b"),
        TaskFile(make_task("A", priority=Priority.HIGH, tags=["work"]), "a"),
        TaskFile(make_task("C"), "c"),
    ]

    assert filter_tasks(files, tags=["work"]) == files[:2]
    assert sort_tasks(files, SortKey.PRIORITY) == [files[1], files[2], files[0]]
    assert find_by_prefix(files, "c") is files[2]


TAGS = ("work", "errands", "home", "homework")


def test_suggest_filter_completes_the_tag_being_typed() -> None:
    assert suggest_filter("#e", TAGS) == "#errands"
    assert suggest_filter("milk #ho", TAGS) == "milk #home"


def test_suggest_filter_takes_the_first_tag_alphabetically() -> None:
    assert suggest_filter("#h", ("homework", "home")) == "#home"


def test_suggest_filter_keeps_the_text_as_typed() -> None:
    assert suggest_filter("Milk  #Er", TAGS) == "Milk  #Errands"
    assert suggest_filter("Status:D", TAGS) == "Status:Doing"
    assert suggest_filter("PRIORITY:H", TAGS) == "PRIORITY:High"


def test_suggest_filter_skips_tags_already_typed() -> None:
    assert suggest_filter("#home #ho", TAGS) == "#home #homework"
    assert suggest_filter("#Errands #e", TAGS) is None


def test_suggest_filter_completes_statuses_and_priorities() -> None:
    assert suggest_filter("status:t", ()) == "status:todo"
    assert suggest_filter("status:d", ()) == "status:doing"
    assert suggest_filter("status:don", ()) == "status:done"
    assert suggest_filter("#home priority:h", TAGS) == "#home priority:high"
    assert suggest_filter("priority:n", ()) == "priority:normal"


@pytest.mark.parametrize(
    "text", ["#home", "status:done", "priority:low", "status:Todo"]
)
def test_suggest_filter_suggests_nothing_for_a_whole_value(text: str) -> None:
    assert suggest_filter(text, TAGS) is None


@pytest.mark.parametrize(
    "text", ["#x", "status:x", "priority:x", "status:doing:", "#e"]
)
def test_suggest_filter_suggests_nothing_without_a_match(text: str) -> None:
    assert suggest_filter(text, ("home",)) is None


@pytest.mark.parametrize(
    "text",
    ["", " ", "#e ", "status:d ", "#", "milk #", "status:", "priority:"],
)
def test_suggest_filter_suggests_nothing_while_no_value_is_typed(text: str) -> None:
    assert suggest_filter(text, TAGS) is None


@pytest.mark.parametrize("text", ["mi", "milk", "due:2026", "e", "stat"])
def test_suggest_filter_suggests_nothing_for_plain_words(text: str) -> None:
    assert suggest_filter(text, TAGS) is None
