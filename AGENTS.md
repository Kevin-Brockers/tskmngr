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
  display.py    # format task fields for display; shared by CLI and TUI
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

- Files live in a tasks directory (default `~/.local/share/tskmngr/tasks/`,
  overridable via `TSKMNGR_DIR`).
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
  there aren't loaded, moving one back as `<id>.md` restores the task, and the
  app never empties the folder.
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

A JSON object (read with `json`) at `~/.config/tskmngr/config.json`,
overridable via `TSKMNGR_CONFIG`, with the keys `tasks_dir`, `sort`,
`reverse`, `theme`, `poll_interval` and `keybindings`. All are flat values
except `keybindings`, an object mapping TUI binding ids to keys as in Textual's
keymap. All are optional; a missing file means
the defaults, and the app never creates or writes it. A relative `tasks_dir` is
read from the config file's folder, and `TSKMNGR_DIR` comes before it. Invalid
JSON, an unknown key or a value that can't be used stops the CLI and the TUI
with an error naming the file and the key.

## Working conventions

### Tests with every change
- Every new behavior or bug fix comes with tests. For a bug fix, write a test
  that fails before the fix.
- Storage tests use pytest's `tmp_path`, never the real tasks directory.
- Run `uv run pytest` before committing; do not commit with failing tests.

### Review the diff with the maintainer before every commit
- Before each commit, stage the changes and show the maintainer the full diff
  (`git diff --staged`, plus `git status` for new or deleted files).
- Ask the maintainer whether the diff is fine, and commit only after they
  explicitly approve. If they request changes, make them and show the new diff.
- This applies to every commit, including small fixes and hook auto-fixes.
- For Claude Code this is enforced by a project hook
  (`.claude/settings.json` → `.claude/hooks/review-diff.sh`): every
  `git commit` triggers an approval prompt showing `git status` and the staged
  diff. Never work around it (e.g. by committing via another tool or script).

#### Local vs. cloud sessions
- **Local session:** strictly follow the diff-review hook. Commit only after
  the maintainer approves the prompt. Nothing else overrides this.
- **Cloud session** (e.g. Claude Code on the web; `CLAUDE_CODE_REMOTE=true`):
  the environment has a built-in check that asks for uncommitted changes to be
  committed and pushed. Handle it in this order:
  1. First run the diff review: show the staged diff and wait for the
     maintainer's explicit approval, exactly as in a local session.
  2. Only after approval, satisfy the built-in check: commit and push to the
     working branch.
  If the built-in check fires while approval is still pending, do not commit;
  tell the maintainer the changes are waiting for their review.

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
  directly to either; both change only through pull requests.
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
