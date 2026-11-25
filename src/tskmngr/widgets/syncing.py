"""Sync the TUI's tasks with the config's `tasks_repo`, in the background.

`Syncer` runs the git work (see `tskmngr.gitsync`) on a thread of its own,
one job at a time and in the order asked, so the TUI never waits for the
network. Each job ends with a `SyncFinished` message to the app, which shows
problems and reloads the screens. The thread is a daemon, so jobs still
waiting or running when the app exits may not finish; whatever they didn't
commit or push, the next sync does.
"""

import queue
import threading
from dataclasses import dataclass

from textual.message import Message
from textual.message_pump import MessagePump
from textual.widget import Widget

from tskmngr.gitsync import (
    SYNC_MESSAGE,
    RepoError,
    SyncError,
    TasksRepo,
    commit_all,
    commit_message,
    has_upstream,
    pull,
    push,
)


class SyncFinished(Message):
    """A sync job is done; `error` is what went wrong, if anything."""

    def __init__(
        self,
        *,
        pulled: bool,
        manual: bool = False,
        error: SyncError | RepoError | None = None,
        upstream: bool = True,
    ) -> None:
        super().__init__()
        # Whether the job pulled, so task files may have changed on disk.
        self.pulled = pulled
        # Whether the user asked for it with the sync key.
        self.manual = manual
        self.error = error
        # Whether the repository has a branch to pull from and push to.
        self.upstream = upstream


@dataclass(frozen=True)
class _Job:
    # None for a sync (commit what's left over, pull, push); else the message
    # of a change's commit, which is pushed.
    message: str | None
    manual: bool = False


class Syncer:
    """Runs sync jobs for `repo` in order, on a thread, reporting to `target`."""

    def __init__(self, repo: TasksRepo, target: MessagePump) -> None:
        self.repo = repo
        self._target = target
        self._jobs: queue.Queue[_Job] = queue.Queue()
        self._thread: threading.Thread | None = None

    def sync(self, *, manual: bool = False) -> None:
        """Commit any changes, pull, then push, like `tskmngr sync`."""
        self._add(_Job(None, manual))

    def change(self, message: str) -> None:
        """Commit the tasks directory's changes with `message`, then push."""
        self._add(_Job(message))

    def wait(self) -> None:
        """Block until every job asked for so far is done (for tests)."""
        self._jobs.join()

    def _add(self, job: _Job) -> None:
        self._jobs.put(job)
        if self._thread is None:
            # A daemon, so a push that hangs never keeps the app from exiting.
            self._thread = threading.Thread(
                target=self._work, name="tskmngr-sync", daemon=True
            )
            self._thread.start()

    def _work(self) -> None:
        while True:
            job = self._jobs.get()
            try:
                try:
                    finished = self._run(job)
                except Exception as error:  # noqa: BLE001
                    # Reported like a failed sync, so the thread keeps
                    # running the jobs after it.
                    failure = SyncError(f"unexpected error: {error}")
                    finished = SyncFinished(
                        pulled=job.message is None, manual=job.manual, error=failure
                    )
                self._target.post_message(finished)
            finally:
                self._jobs.task_done()

    def _run(self, job: _Job) -> SyncFinished:
        pulled = job.message is None
        try:
            if job.message is not None:
                commit_all(self.repo, job.message)
                push(self.repo)
                return SyncFinished(pulled=False)
            commit_all(self.repo, SYNC_MESSAGE)
            upstream = has_upstream(self.repo)
            pull(self.repo)
            push(self.repo)
            return SyncFinished(pulled=True, manual=job.manual, upstream=upstream)
        except (SyncError, RepoError) as error:
            return SyncFinished(pulled=pulled, manual=job.manual, error=error)


def record_change(
    widget: Widget, command: str, task_id: str, title: str | None = None
) -> None:
    """Tell the app a task changed, so it commits and pushes the change.

    `command` names the change in the commit message, like the CLI's
    commands: `add`, `edit`, `done` or `delete`. Does nothing in an app that
    doesn't sync.
    """
    syncer = getattr(widget.app, "syncer", None)
    if isinstance(syncer, Syncer):
        syncer.change(commit_message(command, task_id, title))
