import dataclasses
import os
import stat
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from tskmngr import storage
from tskmngr.models import Status, Task, new_task
from tskmngr.storage import (
    ConflictError,
    ConflictReason,
    delete_task,
    load_tasks,
    save_task,
    tasks_dir,
)
from tskmngr.taskfile import TaskFile

CREATED = datetime(2026, 10, 28, 9, 15, tzinfo=UTC)
DELETED = datetime(2026, 10, 30, 12, 0, 5, tzinfo=UTC)

TASK_TEXT = """\
---
title: Buy milk
status: todo          # todo | doing | done
priority: normal
tags: [errands]
created: 2026-10-28T09:15:00Z
updated: 2026-10-28T09:15:00Z
x-custom: kept
---

Notes go here.
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


def write(directory: Path, name: str, text: str = TASK_TEXT) -> Path:
    path = directory / name
    path.write_bytes(text.encode())
    return path


def load_one(directory: Path) -> TaskFile:
    result = load_tasks(directory)
    assert result.bad_files == []
    [source] = result.tasks
    return source


# Tasks directory


def test_tasks_dir_uses_env_var(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TSKMNGR_DIR", str(tmp_path))
    assert tasks_dir() == tmp_path


def test_tasks_dir_expands_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TSKMNGR_DIR", "~/my-tasks")
    assert tasks_dir() == Path.home() / "my-tasks"


@pytest.mark.parametrize("value", [None, ""])
def test_tasks_dir_default(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    if value is None:
        monkeypatch.delenv("TSKMNGR_DIR", raising=False)
    else:
        monkeypatch.setenv("TSKMNGR_DIR", value)
    assert tasks_dir() == Path.home() / ".local" / "share" / "tskmngr" / "tasks"


# Loading


def test_load_missing_directory(tmp_path: Path) -> None:
    result = load_tasks(tmp_path / "missing")
    assert result.tasks == []
    assert result.bad_files == []


def test_load_takes_id_from_filename(tmp_path: Path) -> None:
    write(tmp_path, "01JB3K7Q2X.md")
    source = load_one(tmp_path)
    assert source.task.id == "01JB3K7Q2X"
    assert source.task.title == "Buy milk"
    assert source.text == TASK_TEXT


def test_load_accepts_hand_made_filename(tmp_path: Path) -> None:
    write(tmp_path, "shopping.md")
    assert load_one(tmp_path).task.id == "shopping"


def test_load_sorts_by_filename(tmp_path: Path) -> None:
    for name in ("b.md", "c.md", "a.md"):
        write(tmp_path, name)
    assert [s.task.id for s in load_tasks(tmp_path).tasks] == ["a", "b", "c"]


def test_load_skips_other_files(tmp_path: Path) -> None:
    write(tmp_path, "01JB3K7Q2X.md")
    write(tmp_path, ".hidden.md")
    write(tmp_path, "notes.txt")
    write(tmp_path, ".01JB3K7Q2X.md.1a2b3c4d.tmp")
    (tmp_path / "folder.md").mkdir()
    (tmp_path / ".trash").mkdir()
    write(tmp_path / ".trash", "OLD.2026-10-30T12-00-00Z.md")
    assert [s.task.id for s in load_tasks(tmp_path).tasks] == ["01JB3K7Q2X"]


def test_load_keeps_crlf_line_endings(tmp_path: Path) -> None:
    text = TASK_TEXT.replace("\n", "\r\n")
    write(tmp_path, "01JB3K7Q2X.md", text)
    assert load_one(tmp_path).text == text


def test_load_keeps_cr_line_endings(tmp_path: Path) -> None:
    text = TASK_TEXT.replace("\n", "\r")
    write(tmp_path, "01JB3K7Q2X.md", text)
    assert load_one(tmp_path).text == text


def test_load_keeps_utf8_byte_order_mark(tmp_path: Path) -> None:
    path = tmp_path / "01JB3K7Q2X.md"
    path.write_bytes(b"\xef\xbb\xbf" + TASK_TEXT.encode())
    source = load_one(tmp_path)
    assert source.task.title == "Buy milk"
    save_task(tmp_path, source.task, source)
    assert path.read_bytes().startswith(b"\xef\xbb\xbf---\n")


def test_load_uses_mtime_for_missing_timestamps(tmp_path: Path) -> None:
    path = write(tmp_path, "a.md", "---\ntitle: Buy milk\n---\n")
    mtime = datetime(2026, 10, 29, 8, 30, 15, tzinfo=UTC)
    os.utime(path, (mtime.timestamp() + 0.5, mtime.timestamp() + 0.5))
    task = load_one(tmp_path).task
    assert task.created == mtime
    assert task.updated == mtime


def test_load_reports_malformed_files(tmp_path: Path) -> None:
    write(tmp_path, "good.md")
    bad = write(tmp_path, "bad.md", "---\ntitle: 1.10\n---\n")
    result = load_tasks(tmp_path)
    assert [s.task.id for s in result.tasks] == ["good"]
    [bad_file] = result.bad_files
    assert bad_file.path == bad
    assert bad_file.error.field == "title"
    assert bad_file.error.line == 2
    # A malformed file is reported, never changed.
    assert bad.read_text() == "---\ntitle: 1.10\n---\n"


def test_load_reports_non_utf8_file(tmp_path: Path) -> None:
    path = tmp_path / "bad.md"
    path.write_bytes(b"---\ntitle: caf\xe9\n---\n")
    [bad_file] = load_tasks(tmp_path).bad_files
    assert bad_file.path == path
    assert "UTF-8" in str(bad_file.error)


def test_ids_include_bad_files(tmp_path: Path) -> None:
    write(tmp_path, "good.md")
    write(tmp_path, "bad.md", "not a task\n")
    assert load_tasks(tmp_path).ids == {"good", "bad"}


# Saving


def test_save_new_task_creates_directory_and_file(tmp_path: Path) -> None:
    directory = tmp_path / "tasks"
    task = new_task("Buy milk", existing_ids=())
    saved = save_task(directory, task, None)
    path = directory / f"{task.id}.md"
    assert path.read_text() == saved.text
    assert saved.task == task
    assert load_one(directory) == saved


def test_save_new_task_refuses_existing_file(tmp_path: Path) -> None:
    path = write(tmp_path, "01JB3K7Q2X.md")
    with pytest.raises(ConflictError) as excinfo:
        save_task(tmp_path, make_task(), None)
    assert excinfo.value.path == path
    assert excinfo.value.reason is ConflictReason.EXISTS
    assert path.read_text() == TASK_TEXT


def test_save_edit_keeps_unknown_keys_and_comments(tmp_path: Path) -> None:
    path = write(tmp_path, "01JB3K7Q2X.md")
    source = load_one(tmp_path)
    saved = save_task(
        tmp_path, dataclasses.replace(source.task, status=Status.DONE), source
    )
    assert path.read_text() == saved.text
    assert "status: done          # todo | doing | done\n" in saved.text
    assert "x-custom: kept\n" in saved.text


def test_save_unchanged_task_keeps_file_byte_for_byte(tmp_path: Path) -> None:
    text = TASK_TEXT.replace("\n", "\r\n")
    path = write(tmp_path, "01JB3K7Q2X.md", text)
    source = load_one(tmp_path)
    saved = save_task(tmp_path, source.task, source)
    assert saved == source
    assert path.read_bytes() == text.encode()


def test_saved_result_is_baseline_for_next_save(tmp_path: Path) -> None:
    write(tmp_path, "01JB3K7Q2X.md")
    source = load_one(tmp_path)
    first = save_task(tmp_path, dataclasses.replace(source.task, title="A"), source)
    second = save_task(tmp_path, dataclasses.replace(first.task, title="B"), first)
    assert load_one(tmp_path) == second


def test_save_refuses_file_changed_on_disk(tmp_path: Path) -> None:
    path = write(tmp_path, "01JB3K7Q2X.md")
    source = load_one(tmp_path)
    path.write_text(TASK_TEXT.replace("Buy milk", "Buy oat milk"))
    with pytest.raises(ConflictError) as excinfo:
        save_task(tmp_path, dataclasses.replace(source.task, title="X"), source)
    assert excinfo.value.reason is ConflictReason.CHANGED
    assert "Buy oat milk" in path.read_text()


def test_save_refuses_file_deleted_on_disk(tmp_path: Path) -> None:
    path = write(tmp_path, "01JB3K7Q2X.md")
    source = load_one(tmp_path)
    path.unlink()
    with pytest.raises(ConflictError) as excinfo:
        save_task(tmp_path, source.task, source)
    assert excinfo.value.reason is ConflictReason.DELETED
    assert not path.exists()


def test_save_refuses_mismatched_id(tmp_path: Path) -> None:
    write(tmp_path, "01JB3K7Q2X.md")
    source = load_one(tmp_path)
    with pytest.raises(ValueError, match="doesn't match"):
        save_task(tmp_path, make_task(id="OTHER"), source)


def test_save_leaves_no_temp_files(tmp_path: Path) -> None:
    save_task(tmp_path, make_task(), None)
    assert [p.name for p in tmp_path.iterdir()] == ["01JB3K7Q2X.md"]


def test_failed_write_keeps_old_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write(tmp_path, "01JB3K7Q2X.md")
    source = load_one(tmp_path)

    def fail(*args: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(storage.os, "replace", fail)
    with pytest.raises(OSError, match="disk full"):
        save_task(tmp_path, dataclasses.replace(source.task, title="X"), source)
    assert path.read_text() == TASK_TEXT
    assert [p.name for p in tmp_path.iterdir()] == ["01JB3K7Q2X.md"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")
def test_save_keeps_file_mode(tmp_path: Path) -> None:
    path = write(tmp_path, "01JB3K7Q2X.md")
    path.chmod(0o600)
    source = load_one(tmp_path)
    save_task(tmp_path, dataclasses.replace(source.task, title="X"), source)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


# Deleting


def test_delete_moves_file_to_trash(tmp_path: Path) -> None:
    path = write(tmp_path, "01JB3K7Q2X.md")
    source = load_one(tmp_path)
    target = delete_task(tmp_path, source, now=DELETED)
    assert target == tmp_path / ".trash" / "01JB3K7Q2X.2026-10-30T12-00-05Z.md"
    assert target.read_text() == TASK_TEXT
    assert not path.exists()
    assert load_tasks(tmp_path).tasks == []


def test_delete_uses_utc_time(tmp_path: Path) -> None:
    write(tmp_path, "a.md")
    local = DELETED.astimezone(timezone(timedelta(hours=2)))
    target = delete_task(tmp_path, load_one(tmp_path), now=local)
    assert target.name == "a.2026-10-30T12-00-05Z.md"


def test_delete_keeps_earlier_trash_files(tmp_path: Path) -> None:
    trash = tmp_path / ".trash"
    trash.mkdir()
    old = write(trash, "a.2026-10-30T12-00-05Z.md", "old\n")
    write(tmp_path, "a.md")
    target = delete_task(tmp_path, load_one(tmp_path), now=DELETED)
    assert target.name == "a.2026-10-30T12-00-05Z-1.md"
    assert old.read_text() == "old\n"
    assert target.read_text() == TASK_TEXT


def test_moving_trash_file_back_restores_task(tmp_path: Path) -> None:
    write(tmp_path, "a.md")
    source = load_one(tmp_path)
    target = delete_task(tmp_path, source, now=DELETED)
    target.rename(tmp_path / "a.md")
    assert load_one(tmp_path) == source


def test_delete_refuses_file_changed_on_disk(tmp_path: Path) -> None:
    path = write(tmp_path, "a.md")
    source = load_one(tmp_path)
    path.write_text(TASK_TEXT.replace("Buy milk", "Buy oat milk"))
    with pytest.raises(ConflictError) as excinfo:
        delete_task(tmp_path, source, now=DELETED)
    assert excinfo.value.reason is ConflictReason.CHANGED
    assert path.exists()
    assert not (tmp_path / ".trash").exists()


def test_delete_refuses_file_deleted_on_disk(tmp_path: Path) -> None:
    path = write(tmp_path, "a.md")
    source = load_one(tmp_path)
    path.unlink()
    with pytest.raises(ConflictError) as excinfo:
        delete_task(tmp_path, source, now=DELETED)
    assert excinfo.value.reason is ConflictReason.DELETED


def test_storage_does_not_import_textual() -> None:
    code = "import sys, tskmngr.storage; sys.exit('textual' in sys.modules)"

    subprocess.run([sys.executable, "-c", code], check=True)
