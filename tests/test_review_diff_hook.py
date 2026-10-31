"""The Claude Code hook that asks for a diff review before every commit."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).parent.parent / ".claude" / "hooks" / "review-diff.sh"
BASH = shutil.which("bash")
COMMIT = "git commit -m 'Add a file'"

pytestmark = pytest.mark.skipif(
    not (BASH and shutil.which("jq") and shutil.which("git")),
    reason="the hook needs bash, jq and git",
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repository with one staged file."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "staged.txt").write_text("staged\n")
    subprocess.run(["git", "add", "staged.txt"], cwd=tmp_path, check=True)
    return tmp_path


@pytest.fixture
def path_without_jq(tmp_path_factory: pytest.TempPathFactory) -> str:
    """A PATH with the other tools the hook uses, but not jq."""
    bin_dir = tmp_path_factory.mktemp("bin")
    for tool in ("cat", "git", "grep"):
        (bin_dir / tool).symlink_to(shutil.which(tool))
    return str(bin_dir)


def run_hook(
    command: str, cwd: Path, path: str | None = None
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if path is not None:
        env["PATH"] = path
    return subprocess.run(
        [BASH, str(HOOK)],
        input=json.dumps({"tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        check=False,
    )


def hook_output(result: subprocess.CompletedProcess[str]) -> dict[str, str]:
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["hookSpecificOutput"]


@pytest.mark.parametrize(
    "command",
    [
        COMMIT,
        "cd /repo && git commit -m msg",
        "git -C /repo commit -m msg",
        'git -C "/my repo" commit -m msg',
        "git -c user.name=me commit -m msg",
        "git --no-pager commit -m msg",
        "(git commit -m msg)",
        "echo $(git commit -m msg)",
        "/usr/bin/git commit -m msg",
    ],
)
def test_commit_asks_for_review(repo: Path, command: str) -> None:
    assert hook_output(run_hook(command, repo))["permissionDecision"] == "ask"


def test_review_shows_status_and_staged_diff(repo: Path) -> None:
    reason = hook_output(run_hook(COMMIT, repo))["permissionDecisionReason"]

    assert "A  staged.txt" in reason
    assert "+staged" in reason


@pytest.mark.parametrize(
    "command",
    [
        "ls",
        "git status",
        "git log --grep commit",
        "git commit-tree HEAD",
        "echo commit",
    ],
)
def test_other_commands_pass(repo: Path, command: str) -> None:
    result = run_hook(command, repo)

    assert result.returncode == 0
    assert result.stdout == ""


@pytest.mark.parametrize(
    "command",
    [
        "git add -A && git commit -m msg",
        "git add . ; git commit -m msg",
        "git stage new.txt && git commit -m msg",
        "git rm old.txt && git -C /repo commit -m msg",
    ],
)
def test_staging_and_committing_in_one_command_is_denied(
    repo: Path, command: str
) -> None:
    # The hook runs before the command, so it can't preview what it stages.
    output = hook_output(run_hook(command, repo))

    assert output["permissionDecision"] == "deny"
    assert "separate command" in output["permissionDecisionReason"]


def test_commit_is_blocked_without_jq(repo: Path, path_without_jq: str) -> None:
    result = run_hook(COMMIT, repo, path=path_without_jq)

    assert result.returncode == 2
    assert "jq is not installed" in result.stderr


def test_other_commands_pass_without_jq(repo: Path, path_without_jq: str) -> None:
    assert run_hook("ls", repo, path=path_without_jq).returncode == 0


def test_commit_is_blocked_when_git_fails(tmp_path: Path) -> None:
    # Not a git repository, so the hook can't build the preview.
    result = run_hook(COMMIT, tmp_path)

    assert result.returncode == 2
    assert "blocked" in result.stderr
