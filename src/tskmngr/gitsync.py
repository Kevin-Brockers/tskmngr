"""Sync the tasks directory with a git repository, through the `git` CLI.

The config's `tasks_repo` names the repository (see `parse_tasks_repo`):

- a remote URL, cloned into `~/.tskmngr/remote_task_dir` (`REMOTE_DIR`), or
- a local folder that's already a git repository; it's pulled from and pushed
  to its upstream branch, if it has one.

Either way the tasks directory is the repository's `tasks/` folder (`TASKS`),
with the deleted tasks in `tasks/.trash/`; other files at the root, like an
`AGENTS.md`, are synced but aren't tasks.

`open_repo` clones or checks the folder and `check_layout` checks that it has
`tasks/`; `RepoError` means it can't be used at all. `init_remote` sets up a
new, empty remote repository in that layout. `commit_all`, `pull` and
`push` raise `SyncError` when git fails (no network, no access, no git
identity), and `pull` raises `PullConflict` when the same task changed on both
sides; the caller reports these as warnings, since the files on disk are
still fine. Nothing here overwrites a task: a conflicting rebase is aborted,
and uncommitted changes are never stashed.

A clone tskmngr makes, by `open_repo` or `init_remote`, gets the commit
author `tskmngr <tskmngr@localhost>` (`AUTHOR_NAME`, `AUTHOR_EMAIL`) in its
own `.git/config`, before anything is committed in it, so its commits don't
count on the user's GitHub profile: GitHub only counts a commit there when
its email is linked to the account. A local repository and a clone that
already exists are never changed.

The access token comes from `TSKMNGR_GIT_TOKEN` (`TOKEN_VAR`) and reaches git
through a credential helper that reads the variable by name, so the token is
never in a command line, `.git/config`, the remote URL or any output.
"""

import os
import re
import secrets
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
from pathlib import Path, PurePosixPath

from tskmngr.storage import SUFFIX, TRASH, parse_trash_name

TOKEN_VAR = "TSKMNGR_GIT_TOKEN"
# Where a remote `tasks_repo` is cloned, under the home folder.
REMOTE_DIR = Path(".tskmngr", "remote_task_dir")
# The folder in the repository that holds the tasks: the tasks directory.
TASKS = "tasks"
# Seconds a git command that talks to the remote may run before it's stopped
# and counts as failed, so tskmngr doesn't hang on a network that doesn't
# answer.
NETWORK_TIMEOUT = 60
# The message of a commit of changes no command made, e.g. by hand, and of a
# sync's (`tskmngr sync`, or the TUI's sync key).
SYNC_MESSAGE = "tskmngr: sync"
# The message of the commit `init_remote` sets up a repository with.
INIT_MESSAGE = "tskmngr: remote init"
# The commit author set in each clone tskmngr makes (see `_set_author`).
AUTHOR_NAME = "tskmngr"
AUTHOR_EMAIL = "tskmngr@localhost"
# The user name sent with the token; GitHub and most hosts ignore it.
TOKEN_USER = "x-access-token"
# A credential helper that answers git's `get` with the token. It reads the
# variable when git runs it, so the token itself is never in the arguments.
_CREDENTIAL_HELPER = (
    f'!f() {{ test "$1" = get || return 0; echo username={TOKEN_USER}; '
    f'echo "password=${TOKEN_VAR}"; }}; f'
)
# `scheme://…`, or scp-like `user@host:path`.
_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://|[^@/\s:]+@[^@/\s:]+:")


@dataclass(frozen=True)
class TasksRepo:
    """The config's `tasks_repo`, read."""

    # The URL as written, or the local folder's full path.
    location: str
    # Whether `location` is a remote URL (cloned) or a local folder.
    remote: bool
    # The repository's folder, where git runs: the clone's, or the local one.
    directory: Path

    @property
    def tasks_directory(self) -> Path:
        """The tasks directory: the repository's `tasks/` folder."""
        return self.directory / TASKS


class RepoError(Exception):
    """The tasks repository can't be used; commands stop."""


class SyncError(Exception):
    """A pull, commit or push failed; the files on disk are still fine."""


class PullConflict(SyncError):
    """The same task changed here and in the remote; the pull was undone."""

    def __init__(self, message: str, names: Sequence[str]) -> None:
        super().__init__(message)
        # The IDs of the tasks in conflict, or a file's path if it isn't one.
        self.names = tuple(names)


def commit_message(command: str, task_id: str, title: str | None = None) -> str:
    """A change's commit message, e.g. `tskmngr: add 01JB3K7Q2X Buy milk`."""
    return " ".join(["tskmngr:", command, task_id, *([title] if title else [])])


def remote_tasks_dir() -> Path:
    """Where a remote `tasks_repo` is cloned: `~/.tskmngr/remote_task_dir`."""
    return Path.home() / REMOTE_DIR


def is_remote(value: str) -> bool:
    """Whether a `tasks_repo` value is a URL (`scheme://…` or `user@host:path`)."""
    return _URL.match(value) is not None


def parse_tasks_repo(value: str, base: Path) -> TasksRepo:
    """Read a `tasks_repo` value; a relative local path is read from `base`."""
    if is_remote(value):
        return TasksRepo(value, True, remote_tasks_dir())
    directory = Path(value).expanduser()
    if not directory.is_absolute():
        directory = base / directory
    return TasksRepo(str(directory), False, directory)


def open_repo(repo: TasksRepo) -> bool:
    """Make sure the tasks directory is the repository; returns whether it cloned.

    A remote URL is cloned into its folder if that doesn't exist, with
    tskmngr as its commit author (`_set_author`); the clone is made next to it
    and renamed into place, so a failed clone leaves nothing behind. Raises `RepoError` if the clone fails, if the folder isn't
    a git repository (tskmngr never runs `git init`), or if a clone's
    `origin` is another URL.
    """
    directory = repo.directory
    if repo.remote and not os.path.lexists(directory):
        _clone(repo)
        return True
    if not _is_repo_root(directory):
        what = "the clone of tasks_repo" if repo.remote else "tasks_repo"
        raise RepoError(
            f"{directory} isn't a git repository, so it can't be {what}; "
            "tskmngr never runs git init"
        )
    if repo.remote:
        origin = _output(directory, "remote", "get-url", "origin")
        if origin != repo.location:
            raise RepoError(
                f"{directory} is a clone of {origin or 'no origin'}, not of "
                f"{repo.location}; move it away to clone tasks_repo there"
            )
    return False


def check_layout(repo: TasksRepo) -> None:
    """Make sure the repository has its `tasks/` folder, the tasks directory.

    Raises `RepoError` if it doesn't, saying to move the task files there.
    Nothing is created or moved.
    """
    tasks = repo.tasks_directory
    if not tasks.is_dir():
        raise RepoError(
            f"{repo.directory} has no {TASKS} folder for the tasks; create "
            f"{tasks} and move any task files and {TRASH}/ in the repository "
            "into it"
        )


def has_changes(repo: TasksRepo) -> bool:
    """Whether the repository has changes that aren't committed."""
    result = _git(repo.directory, "status", "--porcelain", "--untracked-files=all")
    if result.returncode != 0:
        raise SyncError(f"can't read the state of {repo.directory}: {_why(result)}")
    return bool(result.stdout.strip())


def commit_all(repo: TasksRepo, message: str) -> bool:
    """Commit every change in the repository; returns whether it committed.

    Nothing to commit isn't an error. Raises `SyncError` if git can't commit,
    e.g. without a `user.name` and `user.email`.
    """
    if not has_changes(repo):
        return False
    for args in (("add", "--all"), ("commit", "--quiet", "-m", message)):
        result = _git(repo.directory, *args)
        if result.returncode != 0:
            raise SyncError(f"can't commit in {repo.directory}: {_why(result)}")
    return True


def has_upstream(repo: TasksRepo) -> bool:
    """Whether the tasks directory's branch has a branch to pull from and push to.

    A clone always has one (origin's branch of the same name), and a local
    folder one if its branch tracks a remote's, even before the first push.
    Raises `SyncError` if the folder isn't on a branch.
    """
    if repo.remote:
        return True
    return _branch_remote(repo.directory, _branch(repo.directory)) is not None


def pull(repo: TasksRepo) -> None:
    """Bring in the commits from the upstream branch, like `git pull --rebase`.

    Fetches, then fast-forwards, or rebases the local commits onto the
    upstream ones if both have new commits. A local folder without an
    upstream branch has nothing to pull. Raises `SyncError` if git fails
    (offline, no access, uncommitted changes in the way of a rebase), or
    `PullConflict` if the same file changed on both sides; then the rebase is
    aborted, so the local commits and files stay as they were.
    """
    directory = repo.directory
    branch = _branch(directory)
    remote = "origin" if repo.remote else _branch_remote(directory, branch)
    if remote is None:
        return
    fetched = _git(directory, "fetch", "--quiet", remote, network=True)
    if fetched.returncode != 0:
        raise SyncError(f"can't pull from {remote}: {_why(fetched)}")
    upstream = _upstream(directory)
    if upstream is None:
        # A clone of an empty repository, before anything was pushed.
        return
    if _has_head(directory) and not _succeeds(
        directory, "merge-base", "--is-ancestor", "HEAD", upstream
    ):
        if _succeeds(directory, "merge-base", "--is-ancestor", upstream, "HEAD"):
            # Only local commits are new; push sends them.
            return
        _rebase(directory, upstream)
        return
    merged = _git(
        directory, "merge", "--quiet", "--ff-only", "--no-autostash", upstream
    )
    if merged.returncode != 0:
        raise SyncError(f"can't pull from {upstream}: {_why(merged)}")


def push(repo: TasksRepo) -> bool:
    """Push the commits not pushed yet; returns whether there were any.

    A clone pushes to origin's branch of the same name, a local folder to its
    upstream branch; without one, or without commits, nothing is pushed.
    Raises `SyncError` if git fails (offline, no access, or the remote has
    commits that couldn't be pulled).
    """
    directory = repo.directory
    if not _has_head(directory):
        return False
    branch = _branch(directory)
    upstream = _upstream(directory)
    if upstream is not None and not _ahead_of(directory, upstream):
        return False
    if repo.remote:
        args = ["push", "--quiet", "--set-upstream", "origin", f"HEAD:{branch}"]
    else:
        remote = _branch_remote(directory, branch)
        merge = _output(directory, "config", f"branch.{branch}.merge")
        if remote is None or not merge:
            return False
        args = ["push", "--quiet", remote, f"HEAD:{merge}"]
    result = _git(directory, *args, network=True)
    if result.returncode != 0:
        raise SyncError(f"can't push to {args[-2]}: {_why(result)}")
    return True


def init_remote(location: str, files: Mapping[str, str]) -> TasksRepo:
    """Set up the empty remote repository at `location` for tskmngr.

    Clones it, sets the clone's commit author (`_set_author`), writes `files`
    (text by path relative to the repository's root, with `/` between
    folders), commits them as `INIT_MESSAGE` and pushes that
    to the clone's branch; the clone is then `remote_tasks_dir()`, as
    `open_repo` would have made it. It's all done in a temp folder next to
    that, renamed into place only once the push worked, so on any error
    nothing is changed, here or in the remote. Raises `RepoError` if the
    folder already exists, if the repository can't be cloned or isn't empty
    (it has any branch or tag), or if setting the author, the commit or the
    push fails.
    """
    repo = TasksRepo(location, True, remote_tasks_dir())
    directory = repo.directory
    if os.path.lexists(directory):
        raise RepoError(
            f"{directory} already exists; move it away to set up {location} there"
        )
    temp = directory.with_name(f".{directory.name}.{secrets.token_hex(4)}.tmp")
    try:
        _clone_into(location, temp)
        if _output(temp, "for-each-ref"):
            raise RepoError(
                f"{location} isn't empty; remote init only sets up an empty repository"
            )
        _set_author(temp)
        for name, text in files.items():
            path = temp / PurePosixPath(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        for args in (("add", "--all"), ("commit", "--quiet", "-m", INIT_MESSAGE)):
            result = _git(temp, *args)
            if result.returncode != 0:
                raise RepoError(f"can't commit the setup: {_why(result)}")
        branch = _branch(temp)
        result = _git(
            temp,
            "push",
            "--quiet",
            "--set-upstream",
            "origin",
            f"HEAD:{branch}",
            network=True,
        )
        if result.returncode != 0:
            raise RepoError(f"can't push to {location}: {_why(result)}")
        os.rename(temp, directory)
    except SyncError as error:
        raise RepoError(str(error)) from error
    except OSError as error:
        reason = error.strerror or str(error)
        raise RepoError(f"can't set up {location} in {directory}: {reason}") from error
    finally:
        # Only ever the folder this made, never anyone else's.
        shutil.rmtree(temp, ignore_errors=True)
    return repo


def setup_files() -> dict[str, str]:
    """The files `tskmngr remote init` sets up a repository with, by path.

    `AGENTS.md` at the root, from the template shipped with tskmngr, telling
    agents how the task files work, and `tasks/.trash/.gitkeep`, since git
    doesn't keep empty folders.
    """
    agents = resources.files("tskmngr").joinpath("tasks_repo_agents.md")
    return {
        "AGENTS.md": agents.read_text(encoding="utf-8"),
        f"{TASKS}/{TRASH}/.gitkeep": "",
    }


def _clone_into(location: str, folder: Path) -> None:
    """Clone `location` into the new `folder`, making its parent folders."""
    folder.parent.mkdir(parents=True, exist_ok=True)
    result = _git(
        folder.parent, "clone", "--quiet", "--", location, str(folder), network=True
    )
    if result.returncode != 0:
        raise RepoError(f"can't clone {location}: {_why(result)}")


def _set_author(directory: Path) -> None:
    """Make tskmngr the author and committer of the commits in `directory`.

    Sets `user.name` and `user.email` in the repository's own `.git/config`,
    never the global one. Git's `GIT_AUTHOR_*` and `GIT_COMMITTER_*`
    environment variables still come first. Raises `RepoError` if git can't
    write them.
    """
    for key, value in (("user.name", AUTHOR_NAME), ("user.email", AUTHOR_EMAIL)):
        result = _git(directory, "config", "--local", key, value)
        if result.returncode != 0:
            raise RepoError(f"can't set the commit author: {_why(result)}")


def _clone(repo: TasksRepo) -> None:
    directory = repo.directory
    temp = directory.with_name(f".{directory.name}.{secrets.token_hex(4)}.tmp")
    try:
        _clone_into(repo.location, temp)
        _set_author(temp)
        os.rename(temp, directory)
    except OSError as error:
        reason = error.strerror or str(error)
        raise RepoError(
            f"can't clone {repo.location} into {directory}: {reason}"
        ) from error
    finally:
        # Only ever the folder this clone made, never anyone else's.
        shutil.rmtree(temp, ignore_errors=True)


def _rebase(directory: Path, upstream: str) -> None:
    """Rebase the local commits onto `upstream`, aborting on a conflict."""
    result = _git(directory, "rebase", "--quiet", "--no-autostash", upstream)
    if result.returncode == 0:
        return
    if not _rebasing(directory):
        raise SyncError(f"can't pull from {upstream}: {_why(result)}")
    conflicts = _output(directory, "diff", "--name-only", "--diff-filter=U")
    _git(directory, "rebase", "--abort")
    names = [_task_name(path) for path in conflicts.splitlines() if path]
    which = ", ".join(names) or "unknown files"
    raise PullConflict(
        f"can't pull from {upstream}: changed both here and there: {which}. "
        f"Nothing was overwritten; resolve it with git in {directory}",
        names,
    )


def _task_name(path: str) -> str:
    """The task ID a changed file belongs to, or the path if it's no task file.

    `path` is relative to the repository's root, as git prints it.
    """
    parts = PurePosixPath(path).parts
    name = parts[-1]
    if len(parts) == 2 and parts[0] == TASKS and name.endswith(SUFFIX):
        return name.removesuffix(SUFFIX)
    if len(parts) == 3 and parts[:2] == (TASKS, TRASH):
        trashed = parse_trash_name(name)
        if trashed is not None:
            return trashed[0]
    return path


def _rebasing(directory: Path) -> bool:
    for name in ("rebase-merge", "rebase-apply"):
        path = _output(directory, "rev-parse", "--git-path", name)
        if path and (directory / path).exists():
            return True
    return False


def _is_repo_root(directory: Path) -> bool:
    if not directory.is_dir():
        return False
    top = _output(directory, "rev-parse", "--show-toplevel")
    try:
        return bool(top) and Path(top).resolve() == directory.resolve()
    except OSError:
        return False


def _branch(directory: Path) -> str:
    branch = _output(directory, "symbolic-ref", "--quiet", "--short", "HEAD")
    if not branch:
        raise SyncError(f"{directory} isn't on a branch, so it can't be synced")
    return branch


def _branch_remote(directory: Path, branch: str) -> str | None:
    remote = _output(directory, "config", f"branch.{branch}.remote")
    # "." means another local branch, which isn't a remote to sync with.
    return remote if remote and remote != "." else None


def _upstream(directory: Path) -> str | None:
    """The upstream branch's ref, if it's set and was fetched."""
    name = _output(
        directory, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"
    )
    if not name or not _succeeds(directory, "rev-parse", "--verify", "--quiet", name):
        return None
    return name


def _has_head(directory: Path) -> bool:
    return _succeeds(directory, "rev-parse", "--verify", "--quiet", "HEAD")


def _ahead_of(directory: Path, upstream: str) -> bool:
    count = _output(directory, "rev-list", "--count", f"{upstream}..HEAD")
    return count != "0"


def _succeeds(directory: Path, *args: str) -> bool:
    return _git(directory, *args).returncode == 0


def _output(directory: Path, *args: str) -> str:
    """Git's output, stripped; empty if the command failed."""
    result = _git(directory, *args)
    return result.stdout.strip() if result.returncode == 0 else ""


def _git(
    directory: Path, *args: str, network: bool = False
) -> subprocess.CompletedProcess[str]:
    """Run git in `directory` without prompting; never raises for git's errors.

    A network command that takes longer than `NETWORK_TIMEOUT` seconds is
    stopped and fails, and so does any command in a folder that's gone.
    Raises `RepoError` if git isn't installed.
    """
    command = ["git", *_token_config(), *args]
    if not directory.is_dir():
        return subprocess.CompletedProcess(command, 1, "", f"{directory} is gone")
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        return subprocess.run(
            command,
            check=False,
            cwd=directory,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=NETWORK_TIMEOUT if network else None,
        )
    except subprocess.TimeoutExpired:
        message = f"no answer within {NETWORK_TIMEOUT} seconds"
        return subprocess.CompletedProcess(command, 1, "", message)
    except FileNotFoundError as error:
        raise RepoError("git isn't installed, so tasks_repo can't be used") from error


def _token_config() -> list[str]:
    """Git options that give it the token, if `TSKMNGR_GIT_TOKEN` is set.

    The empty helper first drops any others, so the token is the one used.
    """
    if not os.environ.get(TOKEN_VAR):
        return []
    return ["-c", "credential.helper=", "-c", f"credential.helper={_CREDENTIAL_HELPER}"]


def _why(result: subprocess.CompletedProcess[str]) -> str:
    """Git's error message, on one line, without the token."""
    text = " ".join((result.stderr or result.stdout).split()) or "git failed"
    token = os.environ.get(TOKEN_VAR)
    return text.replace(token, "***") if token else text
