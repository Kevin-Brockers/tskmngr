import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def user_home(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point the home folder at an empty temporary one, for every test.

    So no test reads or writes the real `~/.tskmngr/config.json` or tasks.
    `HOME` is what `Path.home()` and `~` use on Linux and macOS,
    `USERPROFILE` on Windows.
    """
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


type Git = Callable[..., str]


@pytest.fixture
def git(monkeypatch: pytest.MonkeyPatch) -> Git:
    """Run git in a folder and return its output; skips without git.

    Sets a git identity for the test's commits (the empty home folder has no
    git config), and keeps out the system's git config.
    """
    if shutil.which("git") is None:
        pytest.skip("git isn't installed")
    for name in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{name}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{name}_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("TSKMNGR_GIT_TOKEN", raising=False)

    def run(directory: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=directory,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    return run


@pytest.fixture
def remote(tmp_path: Path, git: Git) -> Path:
    """An empty bare repository, the remote a `tasks_repo` URL points to."""
    path = tmp_path / "remote.git"
    git(tmp_path, "init", "--quiet", "--bare", "--initial-branch=main", str(path))
    return path
