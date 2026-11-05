import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from tskmngr import gitsync
from tskmngr.gitsync import (
    PullConflict,
    RepoError,
    SyncError,
    TasksRepo,
    check_layout,
    commit_all,
    has_changes,
    has_upstream,
    is_remote,
    open_repo,
    parse_tasks_repo,
    pull,
    push,
    remote_tasks_dir,
)

# The `git` fixture from conftest.py: runs git in a folder, returns its output.
type Git = Callable[..., str]


def clone_repo(remote: Path, directory: Path) -> TasksRepo:
    """A `tasks_repo` for `remote`'s URL, cloned into `directory`."""
    return TasksRepo(remote.as_uri(), True, directory)


def cloned(remote: Path, directory: Path) -> TasksRepo:
    repo = clone_repo(remote, directory)
    assert open_repo(repo) is True
    return repo


def write(repo: TasksRepo, name: str, text: str) -> None:
    path = repo.directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def subjects(git: Git, directory: Path) -> list[str]:
    """The commit messages' first lines, newest first."""
    return git(directory, "log", "--format=%s").splitlines()


@pytest.mark.parametrize(
    "value",
    [
        "https://github.com/me/tasks.git",
        "ssh://git@example.com/tasks.git",
        "git@github.com:me/tasks.git",
        "file:///srv/tasks.git",
    ],
)
def test_urls_are_remote(value: str) -> None:
    assert is_remote(value)


@pytest.mark.parametrize(
    "value", ["tasks", "~/tasks", "/srv/tasks", "../tasks", r"C:\tasks", "a:b"]
)
def test_paths_are_local(value: str) -> None:
    assert not is_remote(value)


def test_a_remote_url_is_cloned_into_the_remote_task_dir(user_home: Path) -> None:
    repo = parse_tasks_repo("https://example.com/tasks.git", Path("/config"))

    assert repo == TasksRepo(
        "https://example.com/tasks.git",
        True,
        user_home / ".tskmngr" / "remote_task_dir",
    )
    assert remote_tasks_dir() == repo.directory


def test_a_relative_local_path_is_read_from_the_base(tmp_path: Path) -> None:
    repo = parse_tasks_repo("tasks", tmp_path)

    assert repo == TasksRepo(str(tmp_path / "tasks"), False, tmp_path / "tasks")


def test_the_tasks_directory_is_the_repositorys_tasks_folder(tmp_path: Path) -> None:
    repo = parse_tasks_repo("repo", tmp_path)

    assert repo.tasks_directory == tmp_path / "repo" / "tasks"


def test_check_layout_accepts_a_repository_with_a_tasks_folder(
    tmp_path: Path, laid_out: Path
) -> None:
    repo = cloned(laid_out, tmp_path / "clone")

    check_layout(repo)


@pytest.mark.parametrize("tasks", [None, "file"])
def test_check_layout_refuses_a_repository_without_a_tasks_folder(
    tmp_path: Path, remote: Path, tasks: str | None
) -> None:
    repo = cloned(remote, tmp_path / "clone")
    write(repo, "01JB3K7Q2X.md", "---\ntitle: At the root\n---\n")
    if tasks == "file":
        write(repo, "tasks", "not a folder")

    with pytest.raises(RepoError) as error:
        check_layout(repo)

    assert str(error.value) == (
        f"{repo.directory} has no tasks folder for the tasks; create "
        f"{repo.directory / 'tasks'} and move any task files and .trash/ in the "
        "repository into it"
    )
    # Nothing was moved or created.
    names = sorted(path.name for path in repo.directory.iterdir())
    assert names == sorted([".git", "01JB3K7Q2X.md", *(["tasks"] if tasks else [])])


def test_a_local_path_may_start_with_a_tilde(user_home: Path) -> None:
    repo = parse_tasks_repo("~/tasks", Path("/config"))

    assert repo.directory == user_home / "tasks"
    assert not repo.remote


def test_open_repo_clones_a_remote_once(tmp_path: Path, remote: Path, git: Git) -> None:
    repo = cloned(remote, tmp_path / "clone")

    assert git(repo.directory, "remote", "get-url", "origin") == remote.as_uri()
    assert open_repo(repo) is False
    # Only the clone is left, no temp folder.
    assert sorted(path.name for path in tmp_path.iterdir()) == ["clone", "remote.git"]


def test_a_failed_clone_leaves_nothing_behind(tmp_path: Path, git: Git) -> None:
    repo = clone_repo(tmp_path / "missing.git", tmp_path / "clone")

    with pytest.raises(RepoError, match="can't clone"):
        open_repo(repo)

    assert list(tmp_path.iterdir()) == []


def test_open_repo_refuses_a_folder_that_isnt_a_repository(
    tmp_path: Path, remote: Path
) -> None:
    folder = tmp_path / "clone"
    folder.mkdir()
    (folder / "T1.md").write_text("mine", encoding="utf-8")

    with pytest.raises(RepoError, match="isn't a git repository"):
        open_repo(clone_repo(remote, folder))

    assert (folder / "T1.md").read_text(encoding="utf-8") == "mine"
    assert not (folder / ".git").exists()


def test_open_repo_refuses_a_clone_of_another_url(
    tmp_path: Path, remote: Path, git: Git
) -> None:
    other = tmp_path / "other.git"
    git(tmp_path, "init", "--quiet", "--bare", str(other))
    cloned(other, tmp_path / "clone")

    with pytest.raises(RepoError, match=f"is a clone of {other.as_uri()}"):
        open_repo(clone_repo(remote, tmp_path / "clone"))


def test_open_repo_accepts_a_local_repository(tmp_path: Path, git: Git) -> None:
    git(tmp_path, "init", "--quiet", "tasks")

    assert open_repo(parse_tasks_repo("tasks", tmp_path)) is False


@pytest.mark.parametrize("make", ["nothing", "folder", "subfolder"])
def test_open_repo_refuses_a_local_folder_that_isnt_a_repository(
    tmp_path: Path, git: Git, make: str
) -> None:
    if make == "folder":
        (tmp_path / "tasks").mkdir()
    if make == "subfolder":
        git(tmp_path, "init", "--quiet")
        (tmp_path / "tasks").mkdir()

    with pytest.raises(RepoError, match="never runs git init"):
        open_repo(parse_tasks_repo("tasks", tmp_path))

    assert not (tmp_path / "tasks" / ".git").exists()


def test_commit_all_commits_every_change(
    tmp_path: Path, remote: Path, git: Git
) -> None:
    repo = cloned(remote, tmp_path / "clone")
    assert commit_all(repo, "nothing") is False

    write(repo, "T1.md", "one")
    write(repo, ".trash/T2.2026-10-30T12-00-05Z.md", "two")
    assert has_changes(repo)

    assert commit_all(repo, "tskmngr: add T1 One") is True
    assert not has_changes(repo)
    assert subjects(git, repo.directory) == ["tskmngr: add T1 One"]
    assert git(repo.directory, "ls-files").splitlines() == [
        ".trash/T2.2026-10-30T12-00-05Z.md",
        "T1.md",
    ]


def test_commit_all_without_a_git_identity_fails(
    tmp_path: Path, remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = cloned(remote, tmp_path / "clone")
    for name in ("AUTHOR", "COMMITTER"):
        monkeypatch.delenv(f"GIT_{name}_NAME")
        monkeypatch.delenv(f"GIT_{name}_EMAIL")
    # Without a name, git falls back to the system's user and host name,
    # which may make up a usable identity; this one it refuses.
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "")
    write(repo, "T1.md", "one")

    with pytest.raises(SyncError, match="can't commit"):
        commit_all(repo, "add")

    assert has_changes(repo)


def test_push_and_pull_carry_commits_between_clones(
    tmp_path: Path, remote: Path, git: Git
) -> None:
    first = cloned(remote, tmp_path / "first")
    second = cloned(remote, tmp_path / "second")
    # Nothing on the remote yet: nothing to pull or push.
    pull(second)
    assert push(second) is False

    write(first, "T1.md", "one")
    commit_all(first, "add T1")
    assert push(first) is True
    assert push(first) is False
    pull(second)

    assert (second.directory / "T1.md").read_text(encoding="utf-8") == "one"
    assert subjects(git, remote) == ["add T1"]


def test_pull_rebases_local_commits_onto_new_ones(
    tmp_path: Path, remote: Path, git: Git
) -> None:
    first = cloned(remote, tmp_path / "first")
    write(first, "T1.md", "one")
    commit_all(first, "add T1")
    push(first)
    second = cloned(remote, tmp_path / "second")
    write(first, "T2.md", "two")
    commit_all(first, "add T2")
    push(first)
    write(second, "T3.md", "three")
    commit_all(second, "add T3")

    pull(second)
    assert push(second) is True

    assert subjects(git, remote) == ["add T3", "add T2", "add T1"]
    assert sorted(path.name for path in second.directory.glob("*.md")) == [
        "T1.md",
        "T2.md",
        "T3.md",
    ]


def test_a_conflict_is_reported_and_undone(
    tmp_path: Path, remote: Path, git: Git
) -> None:
    first = cloned(remote, tmp_path / "first")
    write(first, "tasks/T1.md", "one")
    commit_all(first, "add T1")
    push(first)
    second = cloned(remote, tmp_path / "second")
    write(first, "tasks/T1.md", "first's")
    commit_all(first, "edit T1 there")
    push(first)
    write(second, "tasks/T1.md", "second's")
    commit_all(second, "edit T1 here")

    with pytest.raises(PullConflict, match="changed both here and there: T1") as info:
        pull(second)

    assert info.value.names == ("T1",)
    assert (second.tasks_directory / "T1.md").read_text(encoding="utf-8") == "second's"
    assert subjects(git, second.directory)[0] == "edit T1 here"
    assert not has_changes(second)
    with pytest.raises(SyncError, match="can't push"):
        push(second)


@pytest.mark.parametrize(
    ("path", "name"),
    [
        ("tasks/01JB3K7Q2X.md", "01JB3K7Q2X"),
        ("tasks/.trash/01JB3K7Q2X.2026-10-30T12-00-05Z-1.md", "01JB3K7Q2X"),
        # Outside tasks/, nothing is a task, like files at the root.
        ("01JB3K7Q2X.md", "01JB3K7Q2X.md"),
        (
            ".trash/01JB3K7Q2X.2026-10-30T12-00-05Z-1.md",
            ".trash/01JB3K7Q2X.2026-10-30T12-00-05Z-1.md",
        ),
        ("AGENTS.md", "AGENTS.md"),
        ("tasks/notes/readme.md", "tasks/notes/readme.md"),
        ("tasks/.trash/malformed.md", "tasks/.trash/malformed.md"),
        ("README", "README"),
    ],
)
def test_conflicts_name_the_task(path: str, name: str) -> None:
    assert gitsync._task_name(path) == name


def test_pull_fails_without_the_remote(tmp_path: Path, remote: Path) -> None:
    repo = cloned(remote, tmp_path / "clone")
    remote.rename(tmp_path / "gone.git")

    with pytest.raises(SyncError, match="can't pull from origin"):
        pull(repo)


def test_a_slow_remote_counts_as_a_failure(
    tmp_path: Path, remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = cloned(remote, tmp_path / "clone")
    run = subprocess.run

    def slow(command: list[str], **kwargs: object) -> object:
        if "fetch" in command:
            raise subprocess.TimeoutExpired(command, gitsync.NETWORK_TIMEOUT)
        return run(command, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(subprocess, "run", slow)

    with pytest.raises(SyncError, match="no answer within 60 seconds"):
        pull(repo)


def test_a_local_repository_without_an_upstream_only_commits(
    tmp_path: Path, git: Git
) -> None:
    git(tmp_path, "init", "--quiet", "tasks")
    repo = parse_tasks_repo("tasks", tmp_path)
    write(repo, "T1.md", "one")
    commit_all(repo, "add T1")

    assert not has_upstream(repo)
    pull(repo)
    assert push(repo) is False


def test_a_local_repository_syncs_with_its_upstream(
    tmp_path: Path, remote: Path, git: Git
) -> None:
    git(tmp_path, "clone", "--quiet", str(remote), "tasks")
    repo = parse_tasks_repo("tasks", tmp_path)
    write(repo, "T1.md", "one")
    commit_all(repo, "add T1")

    # A clone tracks the remote's branch even before it exists there.
    assert has_upstream(repo)
    assert push(repo) is True
    write(repo, "T2.md", "two")
    commit_all(repo, "add T2")
    pull(repo)
    assert push(repo) is True
    assert subjects(git, remote) == ["add T2", "add T1"]


def test_without_git_the_repository_cant_be_used(
    tmp_path: Path, remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))

    with pytest.raises(RepoError, match="git isn't installed"):
        open_repo(clone_repo(remote, tmp_path / "clone"))


def test_the_token_reaches_git_through_the_credential_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, git: Git
) -> None:
    monkeypatch.setenv("TSKMNGR_GIT_TOKEN", "s3cret-token")
    options = gitsync._token_config()

    assert "s3cret-token" not in " ".join(options)
    filled = subprocess.run(
        ["git", *options, "credential", "fill"],
        cwd=tmp_path,
        input="protocol=https\nhost=example.com\n\n",
        capture_output=True,
        text=True,
        check=True,
    )
    assert "username=x-access-token\n" in filled.stdout
    assert "password=s3cret-token\n" in filled.stdout


def test_without_a_token_git_uses_its_own_credentials(git: Git) -> None:
    assert gitsync._token_config() == []


def test_the_token_isnt_stored_or_shown(
    tmp_path: Path, remote: Path, git: Git, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TSKMNGR_GIT_TOKEN", "s3cret-token")
    repo = cloned(remote, tmp_path / "clone")
    write(repo, "T1.md", "one")
    commit_all(repo, "add T1")
    push(repo)
    remote.rename(tmp_path / "gone.git")

    with pytest.raises(SyncError) as info:
        pull(repo)

    config = (repo.directory / ".git" / "config").read_text(encoding="utf-8")
    assert "s3cret-token" not in config
    assert "s3cret-token" not in git(repo.directory, "remote", "get-url", "origin")
    assert "s3cret-token" not in str(info.value)


def test_git_errors_never_show_the_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TSKMNGR_GIT_TOKEN", "s3cret-token")
    result = subprocess.CompletedProcess(
        [], 1, "", "fatal: bad\n  https://s3cret-token@example.com\n"
    )

    assert gitsync._why(result) == "fatal: bad https://***@example.com"


def test_a_tasks_directory_thats_gone_fails_the_sync(
    tmp_path: Path, remote: Path
) -> None:
    repo = cloned(remote, tmp_path / "clone")
    (tmp_path / "clone").rename(tmp_path / "moved")

    with pytest.raises(SyncError, match="is gone"):
        commit_all(repo, "add")
