# AGENTS.md

Guidance for AI coding agents (and humans) working in this repository.

## Project overview

`tskmngr` is a terminal task manager with an interactive TUI, written in Python.
Tasks are stored as plain Markdown files so they stay readable and editable
outside the app.

The development plan, what's done and what comes next, lives in
[`ROADMAP.md`](ROADMAP.md). Read it before starting any work.

## General working etiquette

- **Never make things up.** Don't invent data, file contents, API names,
  library features, command output, test results or requirements. If you
  haven't read it, run it or been told it, don't state it as fact.
- **Ask when in doubt.** If a requirement is ambiguous, information is missing,
  or there are several reasonable approaches with real trade-offs, stop and ask
  the maintainer instead of guessing. A short question is cheaper than a wrong
  implementation.
- **Verify before you claim.** Check the code, docs or command output before
  saying something works or exists. Say "done" only after the checks have
  actually passed.
- **Report honestly.** If tests fail, a step was skipped, or you're unsure
  whether something is correct, say so plainly, including the relevant output.
- **Stay in scope.** Do what was asked. Mention other improvements you notice,
  but don't make them without agreement.
- **Don't change `AGENTS.md` or `ROADMAP.md` on your own.** Before changing
  either file, tell the maintainer what you'd change and why, and change it
  only after they explicitly approve, unless they asked for that change
  themselves. This includes the `AGENTS.md` updates a roadmap step calls for.
  Two updates need no approval: marking the step you implement `[x]` with its
  PR's link, and replacing `#TBD` with the PR's link.
- **Don't destroy work.** Never delete or overwrite files, task data or git
  history (no force-push, no `reset --hard` on shared branches) without
  explicit confirmation.

## Tech stack

- **Python** 3.12+
- **[uv](https://docs.astral.sh/uv/)** for environments, dependencies and running commands
- **[Textual](https://textual.textualize.io/)** for the TUI
- **ruamel.yaml** for the frontmatter, in round-trip mode so saving a task
  keeps comments and formatting
- **pytest** with **pytest-asyncio** for tests (Textual's async
  `App.run_test()` / `Pilot` for UI tests)
- **ruff** for linting and formatting
- **[prek](https://github.com/j178/prek)** to run the pre-commit hooks
  (configured in `.pre-commit-config.yaml`)

## Commands

```bash
uv sync                     # install dependencies
uv run tskmngr              # launch the TUI
uv run pytest               # run the test suite
uv run ruff check .         # lint
uv run ruff format .        # format
uv tool install prek        # install prek (once per machine)
prek install                # install the git pre-commit hook (once per clone)
prek run --all-files        # run all pre-commit hooks manually
```

Run lint, format and tests before every commit. All must pass.

## Pre-commit hooks

The prek hook runs on every `git commit`: whitespace and end-of-file fixes,
YAML/TOML checks, merge-conflict markers, large files, private keys, ruff lint
(with auto-fix) and ruff format. It also blocks commits made directly to `main`
or `dev`.

- If a hook modifies files, review the changes, stage them and commit again.
- Never bypass the hooks (`git commit --no-verify`) unless the maintainer
  explicitly says so.
- Changes to `.pre-commit-config.yaml` (adding hooks, bumping versions) count
  as adding dependencies: ask first.

## Project layout

```
src/tskmngr/
  app.py        # Textual App (the TUI)
  cli.py        # `tskmngr` entry point; no arguments launches the TUI
  config.py     # config file (JSON)
  display.py    # format task fields for display, and the column names of the
                #   task list (`Column`) and the deleted tasks view
                #   (`TrashColumn`); shared by CLI and TUI
  editor.py     # the editors (vim, nano): find one on PATH and run it on a
                #   file
  gitsync.py    # clone, pull, commit and push the tasks directory's git repo
  models.py     # Task dataclass and enums (status, priority)
  query.py      # filter, search, sort, ID-prefix lookup; shared by CLI and TUI
  recurrence.py # next due date of a repeating task, and its next occurrence
  storage.py    # read/write task files in the tasks directory
  subtasks.py   # find and toggle the checklist items in a task's notes
  taskfile.py   # convert tasks to and from Markdown with frontmatter (no I/O)
  tasks_repo_agents.md  # the AGENTS.md `tskmngr remote init` puts in a
                #   tasks repository
  widgets/      # Textual widgets and screens
tests/          # mirrors src/ layout; test_<module>.py
scripts/
  release_notes.py  # the release workflow's tag, version and changelog
                #   checks; not part of the package
```

Keep the layers separate: `models`, `taskfile`, `storage`, `query`,
`subtasks`, `recurrence`, `display`, `editor`, `gitsync` and `config` must
not import Textual, so they can be tested without a
UI.

## Task storage format

One Markdown file per task, named after the task's ID (e.g. `01JB3K7Q2X.md`),
with YAML frontmatter for structured fields and the Markdown body for free-form
notes:

```markdown
---
title: Buy milk
status: todo          # todo | doing | done
priority: normal      # low | normal | high
due: 2026-11-01       # optional, ISO date
repeat: weekly        # optional, see below
tags: [errands]
created: 2026-10-28T09:15:00Z
updated: 2026-10-28T09:15:00Z
---

Notes go here, in **Markdown**.
```

- Files live in a tasks directory: the `tasks/` folder of the config file's
  `tasks_repo` (see "Synced tasks"), else its `tasks_dir`, else
  `TSKMNGR_DIR`, else `~/.local/share/tskmngr/tasks/`.
- A task's ID is its filename without `.md`; the frontmatter has no `id` key.
  New tasks get a random 10-character Crockford base32 ID, and a copied or
  hand-made file is a new task under its own name.
- The files are the source of truth. Any cache or index must be disposable and
  rebuildable from them.
- Write files atomically (write to a temp file, then rename) so a crash never
  leaves a half-written task.
- Deleting a task moves its file into `.trash/` inside the tasks directory,
  renamed to `<id>.<delete time>.md` in UTC (e.g.
  `01JB3K7Q2X.2026-10-30T12-00-05Z.md`) so earlier deletes are kept. Files
  there aren't loaded as tasks; the TUI only lists them, read-only, in its
  deleted tasks view (a file whose name has no delete time is reported as
  malformed). Moving one back as `<id>.md` restores the task, and the app
  never empties the folder.
- Tolerate hand-edited files: unknown frontmatter keys are preserved on save,
  and a malformed file is reported to the user, never silently deleted or
  overwritten. A value of the wrong type counts as malformed (YAML reads
  `title: 1.10` as a number); the report suggests quoting it.
- Subtasks are the Markdown checklist items in the notes, with no frontmatter
  key: a line with a list marker (`-`, `*`, `+`, `1.` or `1)`), then `[ ]`
  (open) or `[x]`/`[X]` (done), then the subtask's text, e.g.
  `- [ ] Book hotel`. Items at any indent count, as one flat list; lines in
  fenced code blocks don't. Toggling one rewrites only the character between
  its brackets. Toggling in the TUI also sets the status: checking the last
  open subtask marks the task done, and unchecking one of a done task moves it
  back to doing. Editing the notes by hand or in the form never changes the
  status.
- `repeat` makes a task recurring: `daily`, `weekly`, `monthly`, `yearly` or
  `every N days|weeks|months|years` (N ≥ 1, case and extra spaces ignored;
  written back in that shortest form when changed). When a task with a rule
  is marked done (not when it already was), a new task with a fresh ID is
  created as the next occurrence: same title, priority, tags and rule, the
  notes with every subtask unchecked, status `todo`, and the next due date.
  The rule moves to it: the done task loses `repeat` and `repeat_from`, so it
  stays as history and reopening it doesn't repeat it again. Unknown
  frontmatter keys aren't copied.
- The next due date steps from the old due date by the rule's interval until
  it's after today, so missed occurrences are skipped. A task without a due
  date counts from the day it's done. Monthly and yearly rules keep the day of
  the month: a day the month doesn't have becomes its last day (Jan 31 →
  Feb 28), and the next occurrence then gets `repeat_from` (an ISO date, the
  date the schedule counts from) so the one after is back on the 31st;
  `repeat_from` is left out once the day fits again. Daily and weekly rules
  ignore it.

## Config file

A JSON object (read with `json`) at `~/.tskmngr/config.json`, the only
place it's read from, with the keys `tasks_dir`, `tasks_repo`, `sort`,
`reverse`, `theme`, `editor`, `poll_interval`, `columns`, `trash_columns`,
`show_trash` and `keybindings`.
All are flat values except `columns` and `trash_columns`, lists of column
names, and `keybindings`, an object mapping TUI binding ids to keys as in
Textual's keymap. All are optional.

- On every run (any CLI command or the TUI), if nothing is at that path, the
  app writes the default config there: every key except `tasks_dir` and
  `tasks_repo`, at its default (`sort` `due`, `reverse` false, `theme`
  `textual-dark`, `editor` `vim`, `poll_interval` 2, `columns`
  `["id", "status", "priority", "due", "title", "tags"]`, `trash_columns`
  `["title", "tags", "deleted", "id"]`, `show_trash` true,
  `keybindings` `{}`). The write is atomic and never
  overwrites an existing file; otherwise the app only reads the file, except
  `tskmngr remote init` (see "Synced tasks"), which sets `tasks_repo` in it:
  every other key and value is kept in its order, and the file is rewritten
  atomically as indented JSON, so its spacing changes. If it can't be
  written, the CLI and the TUI stop with an error naming the file.
  `--help` and usage errors exit before this, so they don't write the file
  (or print the warning below).
- `tasks_repo` comes first for the tasks directory (see "Synced tasks"), then
  `tasks_dir`, then `TSKMNGR_DIR`, then the default. A relative `tasks_dir`
  or local `tasks_repo` is read from the config file's folder.
- `editor` is the editor `o` in the TUI and `tskmngr config edit` open files
  in: `vim` or `nano`, found on `PATH` and run in the same terminal (the TUI
  is suspended meanwhile). Any other value stops the CLI and the TUI.
  `$VISUAL` and `$EDITOR` aren't read. An editor that isn't installed is an
  error naming it, the other editor and the config file, and the TUI
  doesn't hand over the terminal. Editing inside the TUI (the form, its
  notes and every other key) doesn't use it.
- `columns` sets the TUI task list's columns in display order, from `id`,
  `status`, `priority`, `due`, `created`, `updated`, `title` and `tags`; the
  ones left out are hidden. `tags` lists a task's tags separated by commas;
  while a table has no tags column, its title ends in the `#tags` instead.
  Sorting by `created` or `updated` still shows that column, last (at the
  far right), while that sort lasts. An empty list, an unknown name or a name
  listed twice stops the CLI and the TUI.
- `trash_columns` sets the TUI's deleted tasks view's columns in display
  order, from the `columns` names plus `deleted` (the delete time), checked
  like `columns`; the view always lists the newest delete first. `show_trash`
  sets whether the view starts shown; `t` (`task_list.toggle_trash`) toggles
  it until the app exits.
- The old `~/.config/tskmngr/config.json` and `TSKMNGR_CONFIG` aren't read.
  While the old file exists, every run prints a warning on stderr; the file
  is never moved or changed.
- Invalid JSON, an unknown key or a value of the wrong type stops the CLI
  and the TUI with an error naming the file and the key, except
  `tskmngr config edit`, which opens the file anyway so it can be fixed. Only
  the TUI and `config edit` check `theme` (a theme Textual has) and
  `keybindings` (known binding ids, no two bindings on one screen sharing a
  key, none taking the app's own keys), and stop on a problem; other CLI
  commands don't use those keys and run anyway.
- `tskmngr config` prints the file's path and every setting in use, marking
  the ones the file leaves out `(default)`, or `(TSKMNGR_DIR)` for the tasks
  directory; while `tasks_repo` is set, the tasks directory is marked
  `(tasks_repo)` and `tasks_repo` notes whether it's remote or local.
  `config get KEY` prints one: plain text, `tasks_dir` as the full path,
  `tasks_repo` as its URL or full path (an empty line if not set), `columns`,
  `trash_columns` and `keybindings` as JSON. `config edit` opens the file in
  its `editor`, or vim when that can't be read (only that key is read
  first, so a file broken elsewhere keeps its editor), then runs every check
  above, the TUI's included. It
  names the key of the first problem and exits 1, and never rewrites the
  file.

## Synced tasks

The tasks directory can be a git repository, synced through the `git` CLI
(`subprocess`, no new dependency; `gitsync.py`). The config key `tasks_repo`
turns it on; without it, nothing is synced. Every command but `config` and
`remote init` (the TUI included) first clones or checks the repository and
its `tasks/` folder, and stops with an error if it can't be used.

- A remote URL (`scheme://…`, e.g. `https://github.com/me/tasks.git`, or
  `user@host:path`) is cloned into `~/.tskmngr/remote_task_dir`. If that
  folder doesn't exist, it's cloned the first time the tasks are needed, into
  a temp folder next to it that's renamed into place, so a failed clone leaves
  nothing behind. If it exists but isn't a git repository, or its `origin` is
  another URL, the command stops with an error naming the folder and nothing
  in it is changed.
- Anything else is a local path (a relative one is read from the config
  file's folder) to a folder that's already a git repository. It's pulled
  from and pushed to its upstream branch; without one, changes are only
  committed. A folder that isn't a git repository stops the command with an
  error; tskmngr never runs `git init`.
- Either way the tasks directory is the repository's `tasks/` folder, with
  the deleted tasks in `tasks/.trash/`; git runs at the repository's root, so
  files there (like an `AGENTS.md`) are synced but aren't tasks. A repository
  without `tasks/` stops every command but `config` with an error saying to
  move the task files and `.trash/` into it; nothing is created or moved.
- While `tasks_repo` is set, `tasks_dir` and `TSKMNGR_DIR` aren't used. Tasks
  in another tasks directory aren't moved; the user copies them into the
  repository's `tasks/` folder.
- `tskmngr remote init URL` sets up an existing, empty remote repository: it
  clones it into a temp folder next to `~/.tskmngr/remote_task_dir`, adds
  `AGENTS.md` (from `tasks_repo_agents.md`) and `tasks/.trash/.gitkeep`,
  commits them as `tskmngr: remote init`, pushes, renames the clone into
  place and sets `tasks_repo` to the URL. It stops, changing nothing, if that
  folder exists, the repository has any branch or tag, `tasks_repo` is
  already another URL, or the clone, commit or push fails. Only it writes the
  repository's `AGENTS.md`; it's never rewritten. A local path is a usage
  error.
- `tasks_repo` must be a string, like other keys' types; beyond that it isn't
  checked when the config is loaded. `tskmngr config` notes whether it's a
  remote URL or a local folder, and for a remote URL the clone's folder. The
  default config file leaves it out.

Which CLI commands sync:

| Command | Sync |
| ------- | ---- |
| `add`, `edit`, `done`, `delete` | Pull, then change the task files, commit and push |
| `list` | Pull, then list |
| `sync` | Commit any changes, pull, then push commits not pushed yet; an error while `tasks_repo` isn't set |
| `remote init` | Clone, then commit and push the setup |
| `show`, `config` | None |

The TUI syncs in the background (a thread in `widgets/syncing.py`, one job
at a time, so it never waits for the network): a full sync (commit leftovers,
pull, push) when it starts and on `y` (`task_list.sync`, shown only while
`tasks_repo` is set), and a commit and push after each change it makes, with
the CLI's commit messages (`add`, `edit`, `done`, `delete`). A failed sync is
a warning notification and a conflict an error one; only `y` confirms that
it worked.

- Every change is one commit, including the move into `.trash/` on delete and
  both files when `done` creates a recurring task's next occurrence. The
  message names the command, the task's ID and its title, e.g.
  `tskmngr: add 01JB3K7Q2X Buy milk`. A command that changes nothing makes
  no commit.
- Changes nobody committed (hand edits, a commit that failed) are
  committed as `tskmngr: sync` before a changing command's pull, so the pull
  never stashes anything: with `--autostash`, a conflict leaves conflict
  markers in the task file. `list` doesn't commit them.
- Pulls work like `git pull --rebase`: a fetch, then a fast-forward, or a
  rebase of the local commits if both sides have new ones. A conflict (the
  same task changed on two machines) aborts the rebase and is reported with
  the task's ID; it's never resolved by overwriting a task. The local commits
  stay until the user resolves it by hand.
- A failed or offline pull, commit or push is a warning on stderr: the
  command still works on the local files and exits 0, and commits that
  weren't pushed go out with the next push. Only `tskmngr sync` exits 1 on
  one. Git runs with `GIT_TERMINAL_PROMPT=0`, so it never waits for a
  password, and a git command that talks to the remote is stopped after 60
  seconds.
- The access token (a fine-grained one) is read from `TSKMNGR_GIT_TOKEN` and
  given to git on each command through a one-off credential helper that reads
  the variable by name, so the token never appears in a command line,
  `.git/config`, the remote URL or any output. Without the variable, git uses
  its own credentials (SSH keys, a credential manager).

## Working conventions

### Tests with every change
- Every new behavior or bug fix comes with tests. For a bug fix, write a test
  that fails before the fix.
- Storage tests use pytest's `tmp_path`, never the real tasks directory.
- Tests never touch the real home folder or config file: `tests/conftest.py`
  points `HOME` (and `USERPROFILE`) at an empty temporary folder for every
  test.
- Run `uv run pytest` before committing; do not commit with failing tests.
- CI (GitHub Actions) runs on every pull request into `dev` and `main` (into
  `main`, only the one from `dev`) and on pushes to them, and by hand:
  `ci-linux.yml` runs `ruff check`, `ruff format --check` and pytest on
  Python 3.12 to 3.14 and the newest one, `ci-macos.yml` pytest on 3.12 to
  3.14. It doesn't replace the local
  lint, format and test runs before every commit.
- `release.yml` runs when a tag like `v0.1.0` is pushed. It stops unless the
  tagged commit is on `main`, the tag is `v` followed by the version in
  `pyproject.toml` and `CHANGELOG.md` has a section with entries for that
  version (checked by `scripts/release_notes.py`), then runs ruff and pytest,
  builds the wheel and sdist with `uv build` and creates a GitHub Release
  with them attached and that section as its notes. Only the maintainer
  pushes release tags.

### Commit, push, open the pull request, then stop
The same rules apply in local and cloud sessions.
- Commit and push to your working branch without asking first. Any branch is
  fine except `dev` and `main`, which you never commit or push to (see
  "Branches and pull requests").
- In a cloud session (e.g. Claude Code on the web; `CLAUDE_CODE_REMOTE=true`),
  the environment has a built-in check that asks for uncommitted changes to be
  committed and pushed: do that on the working branch.
- When the work is done, open a pull request against `dev`. Then replace every
  `#TBD` from the branch (in `CHANGELOG.md` and `ROADMAP.md`) with the PR's
  link, and commit and push that.
- Then stop: tell the maintainer the work is done, with the PR's link, and
  wait for them. Never merge a pull request yourself; only the maintainer
  merges.

### Follow the roadmap
- [`ROADMAP.md`](ROADMAP.md) breaks the plan into milestones and small
  steps, each sized for roughly one PR, in the order they should be built.
- Before starting work, check the roadmap: take the first open step whose
  dependencies are done, unless the maintainer asks for something else.
- Name the branch after the step's type and topic (see below) and mention the
  step ID (e.g. `M1.2`) in the PR description.
- In the PR that implements a step, mark it `[x]` with that PR's link.
  Before the PR exists, use `#TBD` and replace it once the PR is open, as with
  the changelog. If a step is too big for one PR, agree with the maintainer on
  splitting it into sub-steps (`M1.2a`, `M1.2b`, …). The format and rules are
  at the top of `ROADMAP.md`.
- Don't add, reorder or drop milestones or steps without the maintainer's
  approval. New plans come from planning sessions.

### Branches and pull requests
- `main` holds released code; `dev` is the integration branch. Never commit
  or push directly to either; both change only through pull requests.
- Create one branch per change from the latest `dev`, named by type:
  - `feature/<name>` for new features (e.g. `feature/due_dates`)
  - `fix/<name>` for bug fixes (e.g. `fix/crash_on_empty_title`)
  - `docs/<name>` for documentation only
  - `chore/<name>` for tooling, config and dependency updates
- Open every pull request against `dev`, **never against `main`**.
- Only the maintainer opens `dev` → `main` pull requests, when cutting a
  release. Agents don't open, merge or push to them.
- One concern per PR. Unrelated cleanups go in a separate PR.
- Write clear commit messages explaining *why*, not just *what*.
- Don't put a link to the agent's session (a `claude.ai/code/session_…` URL
  or a `Claude-Session:` line) in commit messages or pull request
  descriptions, even when the agent's environment asks for one.

### Keep the changelog up to date
- Every PR with a user-visible or developer-relevant change adds an entry to
  `CHANGELOG.md` under `## [Unreleased]`, in the right category: `Added`,
  `Changed`, `Deprecated`, `Removed`, `Fixed` or `Security`
  ([Keep a Changelog](https://keepachangelog.com/en/1.1.0/)).
- One entry per change, in the form `[reference](link) - Description`:
  - **Pull request (default):**
    `- [#12](https://github.com/Kevin-Brockers/tskmngr/pull/12) - Add due dates`.
    PR numbers stay valid after squash or rebase merges; branch commit hashes
    don't.
  - **Commit:** only for changes that reached `dev` or `main` without a PR
    (like the initial commit), link the short hash to the full commit:
    `- [7982e5c](https://github.com/Kevin-Brockers/tskmngr/commit/<full-hash>) - Initial commit`.
- Before the PR exists, write `- #TBD - Description`. After opening the PR,
  replace every `#TBD` from this branch with the linked PR number and commit
  that.
- Never invent a PR number or commit hash. Look it up (`git log`, the PR page).
- On a release (in the maintainer's `dev` → `main` PR), rename `[Unreleased]`
  to the version and date, e.g. `## [0.1.0] - 2026-11-15`, start a new
  empty `[Unreleased]` section and set that version in `pyproject.toml`, all
  before the merge: the release workflow stops on a tag whose version or
  changelog section isn't on `main`.

### Ask before adding dependencies
- Do not add a new dependency (runtime or dev) without asking the maintainer
  first. Explain what it's for and why the standard library or an existing
  dependency isn't enough.
- Approved baseline: `textual`, `rich` (comes with Textual; pinned because
  the TUI imports it directly), `ruamel.yaml`, `pytest`, `pytest-asyncio`,
  `ruff`.

## Code style

- Follow ruff's defaults; let `ruff format` decide formatting.
- Type hints on all public functions; prefer `dataclasses` for data types.
- Keep functions small and side effects (file I/O) at the edges.
