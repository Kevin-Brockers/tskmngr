import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tskmngr.config import (
    DEFAULT_POLL_INTERVAL,
    DEFAULT_SETTINGS,
    DEFAULT_THEME,
    Config,
    ConfigError,
    config_path,
    create_default_config,
    default_config_text,
    load_config,
    old_config_path,
    parse_config,
)
from tskmngr.query import SortKey

PATH = Path("/home/me/.tskmngr/config.json")

SORT = "sort: expected one of due, priority, created, updated, got "
POLL = "poll_interval: expected a number of seconds, 0 or more, got "
KEYS = (
    "keybindings: task_list.new: expected one or more keys, separated by commas, got "
)


def error_message(text: str) -> str:
    with pytest.raises(ConfigError) as excinfo:
        parse_config(text, PATH)
    assert str(excinfo.value) == f"{PATH}: {excinfo.value.message}"
    return excinfo.value.message


# Where the file is


def test_config_path_is_in_dot_tskmngr(user_home: Path) -> None:
    assert config_path() == user_home / ".tskmngr" / "config.json"


def test_tskmngr_config_is_no_longer_read(
    user_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TSKMNGR_CONFIG", str(tmp_path / "my.json"))
    assert config_path() == user_home / ".tskmngr" / "config.json"


def test_old_config_path_is_in_dot_config(user_home: Path) -> None:
    assert old_config_path() == user_home / ".config" / "tskmngr" / "config.json"


# Writing the default file


def test_the_default_file_has_every_setting_but_tasks_dir() -> None:
    assert json.loads(default_config_text()) == DEFAULT_SETTINGS
    assert set(DEFAULT_SETTINGS) == {
        "sort",
        "reverse",
        "theme",
        "poll_interval",
        "keybindings",
    }


def test_the_default_file_reads_as_the_defaults() -> None:
    config = parse_config(default_config_text(), PATH)

    assert config == Config(path=PATH, theme=DEFAULT_THEME)
    assert config.tasks_dir is None
    assert config.poll_interval == DEFAULT_POLL_INTERVAL


def test_the_default_file_is_indented_json() -> None:
    assert default_config_text() == (
        "{\n"
        '  "sort": "due",\n'
        '  "reverse": false,\n'
        '  "theme": "textual-dark",\n'
        '  "poll_interval": 2,\n'
        '  "keybindings": {}\n'
        "}\n"
    )


def test_create_default_config_writes_the_file_and_its_folders(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".tskmngr" / "config.json"

    assert create_default_config(path) is True

    assert path.read_text(encoding="utf-8") == default_config_text()
    assert list(path.parent.iterdir()) == [path]


def test_create_default_config_never_overwrites_a_file(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"sort": "priority"}', encoding="utf-8")

    assert create_default_config(path) is False

    assert path.read_text(encoding="utf-8") == '{"sort": "priority"}'
    assert list(tmp_path.iterdir()) == [path]


def test_create_default_config_leaves_a_folder_in_its_place(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.mkdir()

    assert create_default_config(path) is False

    assert path.is_dir()


def test_create_default_config_keeps_a_file_made_meanwhile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.json"
    real_link = os.link

    def made_meanwhile(source: Path, target: Path) -> None:
        path.write_text("{}", encoding="utf-8")
        real_link(source, target)

    monkeypatch.setattr(os, "link", made_meanwhile)

    assert create_default_config(path) is False

    assert path.read_text(encoding="utf-8") == "{}"
    assert list(tmp_path.iterdir()) == [path]


def test_create_default_config_reports_a_folder_it_cant_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.json"

    def unwritable(*args: object, **kwargs: object) -> int:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(os, "open", unwritable)

    with pytest.raises(ConfigError) as excinfo:
        create_default_config(path)

    assert str(excinfo.value) == f"{path}: can't be created: Permission denied"
    assert list(tmp_path.iterdir()) == []


def test_create_default_config_cleans_up_when_linking_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.json"

    def no_links(source: Path, target: Path) -> None:
        raise OSError(1, "Operation not permitted")

    monkeypatch.setattr(os, "link", no_links)

    with pytest.raises(ConfigError) as excinfo:
        create_default_config(path)

    assert excinfo.value.message == "can't be created: Operation not permitted"
    assert list(tmp_path.iterdir()) == []


def test_create_default_config_reports_a_file_in_place_of_its_folder(
    tmp_path: Path,
) -> None:
    (tmp_path / ".tskmngr").write_text("", encoding="utf-8")
    path = tmp_path / ".tskmngr" / "config.json"

    with pytest.raises(ConfigError) as excinfo:
        create_default_config(path)

    assert excinfo.value.path == path
    assert excinfo.value.message.startswith("can't be created: ")


# Reading it


def test_missing_file_gives_the_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path / "config.json")

    assert config == Config()
    assert config.tasks_dir is None
    assert config.sort is SortKey.DUE
    assert config.reverse is False
    assert config.theme is None
    assert config.poll_interval == DEFAULT_POLL_INTERVAL == 2.0


def test_load_reads_the_file_at_config_path() -> None:
    path = config_path()
    path.parent.mkdir()
    path.write_text('{"sort": "updated"}', encoding="utf-8")

    assert load_config() == Config(path=path, sort=SortKey.UPDATED)


def test_every_setting_is_read() -> None:
    config = parse_config(
        """{
          "tasks_dir": "/srv/tasks",
          "sort": "priority",
          "reverse": true,
          "theme": "nord",
          "poll_interval": 0.5,
          "keybindings": {"task_list.new": "a", "task_form.save": "ctrl+s,f2"}
        }""",
        PATH,
    )

    assert config == Config(
        path=PATH,
        tasks_dir=Path("/srv/tasks"),
        sort=SortKey.PRIORITY,
        reverse=True,
        theme="nord",
        poll_interval=0.5,
        keybindings={"task_list.new": "a", "task_form.save": "ctrl+s,f2"},
    )


def test_an_empty_object_gives_the_defaults() -> None:
    assert parse_config("{}", PATH) == Config(path=PATH)


def test_no_keybindings_by_default() -> None:
    assert Config().keybindings == {}


def test_spaces_around_keybinding_keys_are_dropped() -> None:
    config = parse_config('{"keybindings": {"task_list.new": " a , f2 "}}', PATH)
    assert config.keybindings == {"task_list.new": "a,f2"}


def test_tasks_dir_expands_home() -> None:
    config = parse_config('{"tasks_dir": "~/tasks"}', PATH)
    assert config.tasks_dir == Path.home() / "tasks"


def test_relative_tasks_dir_is_read_from_the_config_folder() -> None:
    config = parse_config('{"tasks_dir": "tasks/mine"}', PATH)
    assert config.tasks_dir == PATH.parent / "tasks" / "mine"


@pytest.mark.parametrize(("value", "seconds"), [("0", 0.0), ("5", 5.0)])
def test_poll_interval_may_be_a_whole_number(value: str, seconds: float) -> None:
    interval = parse_config(f'{{"poll_interval": {value}}}', PATH).poll_interval
    assert interval == seconds
    assert isinstance(interval, float)


# Broken files


def test_invalid_json_names_line_and_column() -> None:
    message = error_message('{\n  "sort": "due"\n  "reverse": true\n}')
    assert message == "line 3, column 3: Expecting ',' delimiter"


def test_an_empty_file_is_invalid() -> None:
    assert error_message("") == "line 1, column 1: Expecting value"


@pytest.mark.parametrize(
    ("text", "got"), [("[]", "a list"), ('"due"', "the text 'due'"), ("null", "null")]
)
def test_the_file_must_hold_an_object(text: str, got: str) -> None:
    assert error_message(text) == f"expected an object of settings, got {got}"


def test_unknown_keys_are_refused() -> None:
    assert error_message('{"sort": "due", "colour": "red"}') == (
        "unknown key 'colour'; the known keys are tasks_dir, sort, reverse, "
        "theme, poll_interval, keybindings"
    )


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('{"tasks_dir": 5}', "tasks_dir: expected a folder path, got the number 5"),
        ('{"tasks_dir": " "}', "tasks_dir: expected a folder path, got the text ' '"),
        ('{"sort": "size"}', SORT + "the text 'size'"),
        ('{"sort": ["due"]}', SORT + "a list"),
        ('{"reverse": "yes"}', "reverse: expected true or false, got the text 'yes'"),
        ('{"reverse": 1}', "reverse: expected true or false, got the number 1"),
        ('{"theme": ""}', "theme: expected a theme name, got the text ''"),
        ('{"theme": {}}', "theme: expected a theme name, got an object"),
        ('{"poll_interval": -1}', POLL + "the number -1"),
        ('{"poll_interval": "2"}', POLL + "the text '2'"),
        ('{"poll_interval": true}', POLL + "the boolean true"),
        ('{"poll_interval": NaN}', POLL + "the number nan"),
        ('{"poll_interval": Infinity}', POLL + "the number inf"),
        ('{"poll_interval": null}', POLL + "null"),
        (
            '{"keybindings": ["task_list.new"]}',
            "keybindings: expected an object of binding ids and keys, got a list",
        ),
        ('{"keybindings": {"task_list.new": ""}}', KEYS + "the text ''"),
        ('{"keybindings": {"task_list.new": " "}}', KEYS + "the text ' '"),
        ('{"keybindings": {"task_list.new": "a,,b"}}', KEYS + "the text 'a,,b'"),
        ('{"keybindings": {"task_list.new": "a,"}}', KEYS + "the text 'a,'"),
        ('{"keybindings": {"task_list.new": ["a"]}}', KEYS + "a list"),
        ('{"keybindings": {"task_list.new": null}}', KEYS + "null"),
    ],
)
def test_values_of_the_wrong_kind_are_refused(text: str, message: str) -> None:
    assert error_message(text) == message


def test_a_file_that_isnt_utf8_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_bytes(b'{"theme": "\xff"}')

    with pytest.raises(ConfigError) as excinfo:
        load_config(path)
    assert str(excinfo.value) == f"{path}: not UTF-8 text"


def test_a_file_that_cant_be_read_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.mkdir()

    with pytest.raises(ConfigError) as excinfo:
        load_config(path)
    assert excinfo.value.message.startswith("can't be read: ")


def test_config_does_not_import_textual() -> None:
    code = "import sys, tskmngr.config; sys.exit('textual' in sys.modules)"

    subprocess.run([sys.executable, "-c", code], check=True)
