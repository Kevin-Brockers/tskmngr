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
  editor.py     # find $VISUAL/$EDITOR and run it on a file
  models.py     # Task dataclass and enums (status, priority)
  query.py      # filter, search, sort, ID-prefix lookup; shared by CLI and TUI
  recurrence.py # next due date of a repeating task, and its next occurrence
  storage.py    # read/write task files in the tasks directory
  subtasks.py   # find and toggle the checklist items in a task's notes
  taskfile.py   # convert tasks to and from Markdown with frontmatter (no I/O)
  widgets/      # Textual widgets and screens
tests/          # mirrors src/ layout; test_<module>.py
```

Keep the layers separate: `models`, `taskfile`, `storage`, `query`,
`subtasks`, `recurrence`, `display`, `editor` and `config` must not import
Textual, so they can be tested without a
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

- Files live in a tasks directory: the config file's `tasks_dir`, else
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
place it's read from, with the keys `tasks_dir`, `sort`, `reverse`, `theme`,
`poll_interval`, `columns`, `trash_columns`, `show_trash` and `keybindings`.
All are flat values except `columns` and `trash_columns`, lists of column
names, and `keybindings`, an object mapping TUI binding ids to keys as in
Textual's keymap. All are optional.

- On every run (any CLI command or the TUI), if nothing is at that path, the
  app writes the default config there: every key except `tasks_dir`, at its
  default (`sort` `due`, `reverse` false, `theme` `textual-dark`,
  `poll_interval` 2, `columns` `["id", "status", "priority", "due", "title"]`,
  `trash_columns` `["title", "deleted", "id"]`, `show_trash` true,
  `keybindings` `{}`). The write is atomic and never
  overwrites an existing file; otherwise the app only reads the file. If it
  can't be written, the CLI and the TUI stop with an error naming the file.
  `--help` and usage errors exit before this, so they don't write the file
  (or print the warning below).
- `tasks_dir` comes first for the tasks directory, then `TSKMNGR_DIR`, then
  the default. A relative `tasks_dir` is read from the config file's folder.
- `columns` sets the TUI task list's columns in display order, from `id`,
  `status`, `priority`, `due`, `created`, `updated` and `title`; the ones
  left out are hidden. Sorting by `created` or `updated` still shows that
  column, last (at the far right), while that sort lasts. An empty list, an
  unknown name or a name listed twice stops the CLI and the TUI.
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
  directory. `config get KEY` prints one: plain text, `tasks_dir` as the full
  path, `columns` and `keybindings` as JSON. `config edit` opens the file in
  `$VISUAL`/`$EDITOR`, then runs every check above, the TUI's included. It
  names the key of the first problem and exits 1, and never rewrites the
  file.

## Working conventions

### Tests with every change
- Every new behavior or bug fix comes with tests. For a bug fix, write a test
  that fails before the fix.
- Storage tests use pytest's `tmp_path`, never the real tasks directory.
- Tests never touch the real home folder or config file: `tests/conftest.py`
  points `HOME` (and `USERPROFILE`) at an empty temporary folder for every
  test.
- Run `uv run pytest` before committing; do not commit with failing tests.

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
  to the version and date, e.g. `## [0.1.0] - 2026-11-15`, and start a new
  empty `[Unreleased]` section.

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
