import sys
from pathlib import Path

import pytest

from tskmngr.editor import (
    DEFAULT_EDITOR,
    Editor,
    EditorNotFound,
    editor_command,
    not_found_hint,
    run_editor,
)


def fake_program(folder: Path, name: str) -> Path:
    """An executable called `name` in `folder`, to put on `PATH`."""
    folder.mkdir(exist_ok=True)
    program = folder / name
    program.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    program.chmod(0o755)
    return program


def test_the_editors_are_vim_and_nano_with_vim_the_default() -> None:
    assert [editor.value for editor in Editor] == ["vim", "nano"]
    assert DEFAULT_EDITOR is Editor.VIM


@pytest.mark.parametrize("editor", list(Editor))
def test_editor_command_is_the_program_found_on_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, editor: Editor
) -> None:
    program = fake_program(tmp_path / "bin", editor.value)
    monkeypatch.setenv("PATH", str(program.parent))

    assert editor_command(editor) == [str(program)]


def test_visual_and_editor_are_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program = fake_program(tmp_path / "bin", "vim")
    fake_program(tmp_path / "bin", "emacs")
    monkeypatch.setenv("PATH", str(program.parent))
    monkeypatch.setenv("VISUAL", "emacs")
    monkeypatch.setenv("EDITOR", "emacs")

    assert editor_command(Editor.VIM) == [str(program)]


def test_an_editor_that_isnt_installed_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))

    with pytest.raises(EditorNotFound) as info:
        editor_command(Editor.NANO)

    assert info.value.editor is Editor.NANO
    assert str(info.value) == "nano isn't installed"


def test_not_found_hint_names_the_other_editor_and_the_file() -> None:
    path = Path("/home/me/.tskmngr/config.json")

    assert not_found_hint(Editor.VIM, path) == (
        f"vim isn't installed; install it, or set editor to nano in {path}"
    )
    assert not_found_hint(Editor.NANO, path).endswith(f"set editor to vim in {path}")


def test_run_editor_passes_the_path_and_returns_the_exit_status(
    tmp_path: Path,
) -> None:
    path = tmp_path / "AAAA.md"
    path.write_text("before\n", encoding="utf-8")
    script = (
        "import sys; from pathlib import Path; "
        "Path(sys.argv[2]).write_text(sys.argv[1] + '\\n'); sys.exit(3)"
    )

    status = run_editor([sys.executable, "-c", script, "after"], path)

    assert status == 3
    assert path.read_text(encoding="utf-8") == "after\n"


def test_run_editor_raises_for_a_missing_program(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run_editor([str(tmp_path / "no-such-editor")], tmp_path / "AAAA.md")
