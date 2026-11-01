import sys
from pathlib import Path

import pytest

from tskmngr.editor import EditorSettingError, editor_command, run_editor


def test_visual_comes_before_editor() -> None:
    assert editor_command({"VISUAL": "code --wait", "EDITOR": "vi"}) == [
        "code",
        "--wait",
    ]


def test_editor_is_used_without_visual() -> None:
    assert editor_command({"EDITOR": "nano"}) == ["nano"]


@pytest.mark.parametrize("visual", ["", "   ", '""'])
def test_empty_visual_counts_as_unset(visual: str) -> None:
    assert editor_command({"VISUAL": visual, "EDITOR": "nano"}) == ["nano"]


def test_neither_set_is_none() -> None:
    assert editor_command({}) is None
    assert editor_command({"VISUAL": "", "EDITOR": " "}) is None


def test_value_is_split_like_a_shell_command_line() -> None:
    command = editor_command({"EDITOR": "'/opt/My Editor/edit' -n --wait"})

    assert command == ["/opt/My Editor/edit", "-n", "--wait"]


def test_unsplittable_value_names_the_variable() -> None:
    with pytest.raises(EditorSettingError) as info:
        editor_command({"VISUAL": "'vi", "EDITOR": "nano"})

    assert info.value.name == "VISUAL"
    assert info.value.value == "'vi"
    assert str(info.value).startswith("$VISUAL can't be read as a command (")


def test_reads_the_environment_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.setenv("EDITOR", "nano -w")

    assert editor_command() == ["nano", "-w"]


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
