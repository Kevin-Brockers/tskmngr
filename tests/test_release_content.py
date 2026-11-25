"""Tests for `scripts/release_content.py`, used by the release workflow."""

import importlib.util
import io
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "release_content.py"
_spec = importlib.util.spec_from_file_location("release_content", SCRIPT)
assert _spec is not None and _spec.loader is not None
release_content = importlib.util.module_from_spec(_spec)
sys.modules["release_content"] = release_content
_spec.loader.exec_module(release_content)


def make_tar(path: Path, names: list[str]) -> Path:
    with tarfile.open(path, "w:gz") as archive:
        for name in names:
            info = tarfile.TarInfo(name)
            info.size = 1
            archive.addfile(info, io.BytesIO(b"x"))
    return path


def make_wheel(path: Path, names: list[str]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, "x")
    return path


@pytest.mark.parametrize(
    "name",
    [
        "AGENTS.md",
        "ROADMAP.md",
        "docs/finished_roadmap.md",
        "RELEASING.md",
        ".claude",
        ".claude/settings.json",
        ".claude/skills/init-work/SKILL.md",
    ],
)
def test_the_working_files_are_left_out(name: str) -> None:
    assert release_content.left_out_names([name]) == [name]


@pytest.mark.parametrize(
    "name",
    [
        "README.md",
        "CHANGELOG.md",
        "src/tskmngr/tasks_repo_agents.md",
        "src/tskmngr/AGENTS.md",
        "docs/other.md",
        ".claude-notes.md",
        "tskmngr/cli.py",
    ],
)
def test_other_files_stay(name: str) -> None:
    assert release_content.left_out_names([name]) == []


def test_a_tar_archives_top_folder_is_dropped(tmp_path: Path) -> None:
    path = make_tar(
        tmp_path / "tskmngr-0.1.0.tar.gz",
        ["tskmngr-0.1.0/README.md", "tskmngr-0.1.0/src/tskmngr/cli.py"],
    )

    assert release_content.archive_names(path) == ["README.md", "src/tskmngr/cli.py"]


def test_a_wheels_names_are_kept(tmp_path: Path) -> None:
    path = make_wheel(tmp_path / "tskmngr-0.1.0-py3-none-any.whl", ["tskmngr/cli.py"])

    assert release_content.archive_names(path) == ["tskmngr/cli.py"]


def test_main_names_each_archive_and_left_out_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    good = make_wheel(tmp_path / "good.whl", ["tskmngr/cli.py"])
    bad = make_tar(tmp_path / "bad.tar.gz", ["top/README.md", "top/AGENTS.md"])

    assert release_content.main([str(good), str(bad)]) == 1

    assert capsys.readouterr().err == f"error: {bad} holds AGENTS.md\n"


def test_main_passes_archives_without_them(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path / "a.whl", ["tskmngr/cli.py"])
    sdist = make_tar(tmp_path / "a.tar.gz", ["top/README.md", "top/LICENSE"])

    assert release_content.main([str(wheel), str(sdist)]) == 0


def test_gitattributes_leaves_out_every_working_file() -> None:
    lines = (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
    ignored = {
        line.split()[0].lstrip("/")
        for line in lines
        if line.strip() and not line.startswith("#") and "export-ignore" in line
    }

    assert ignored == {name.rstrip("/") for name in release_content.LEFT_OUT}


def test_git_archive_of_this_repository_leaves_them_out(tmp_path: Path) -> None:
    path = tmp_path / "source.tar.gz"
    subprocess.run(
        [
            "git",
            "archive",
            "--worktree-attributes",
            "--prefix=tskmngr/",
            "-o",
            str(path),
            "HEAD",
        ],
        cwd=ROOT,
        check=True,
    )

    names = release_content.archive_names(path)
    assert "README.md" in names
    assert release_content.left_out_names(names) == []
