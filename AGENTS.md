# AGENTS.md

Guidance for AI coding agents (and humans) working in this repository.

## Project overview

`tskmngr` is a terminal task manager with an interactive TUI, written in Python.
Tasks are stored as plain Markdown files so they stay readable and editable
outside the app.

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
- **pytest** for tests (Textual's `App.run_test()` / `Pilot` for UI tests)
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
(with auto-fix) and ruff format. It also blocks commits made directly to `main`.

- If a hook modifies files, review the changes, stage them and commit again.
- Never bypass the hooks (`git commit --no-verify`) unless the maintainer
  explicitly says so.
- Changes to `.pre-commit-config.yaml` (adding hooks, bumping versions) count
  as adding dependencies: ask first.

## Project layout

```
src/tskmngr/
  app.py        # Textual App entry point
  models.py     # Task dataclass and enums (status, priority)
  storage.py    # read/write tasks as Markdown files
  widgets/      # Textual widgets and screens
tests/          # mirrors src/ layout; test_<module>.py
```

Keep the layers separate: `models` and `storage` must not import Textual, so
they can be tested without a UI.

## Task storage format

One Markdown file per task, with YAML frontmatter for structured fields and the
Markdown body for free-form notes:

```markdown
---
id: 01JB3K7Q2X
title: Buy milk
status: todo          # todo | doing | done
priority: normal      # low | normal | high
due: 2026-11-01       # optional, ISO date
tags: [errands]
created: 2026-10-28T09:15:00Z
updated: 2026-10-28T09:15:00Z
---

Notes go here, in **Markdown**.
```

- Files live in a tasks directory (default `~/.local/share/tskmngr/tasks/`,
  overridable via `TSKMNGR_DIR`); filename is `<id>.md`.
- The files are the source of truth. Any cache or index must be disposable and
  rebuildable from them.
- Write files atomically (write to a temp file, then rename) so a crash never
  leaves a half-written task.
- Tolerate hand-edited files: unknown frontmatter keys are preserved on save,
  and a malformed file is reported to the user, never silently deleted or
  overwritten.

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

### Small PRs via branches
- Never commit directly to `main`. Create a branch per change
  (e.g. `feat/add-due-dates`, `fix/crash-on-empty-title`).
- One concern per PR. Unrelated cleanups go in a separate PR.
- Write clear commit messages explaining *why*, not just *what*.

### Ask before adding dependencies
- Do not add a new dependency (runtime or dev) without asking the maintainer
  first. Explain what it's for and why the standard library or an existing
  dependency isn't enough.
- Approved baseline: `textual`, `pyyaml`, `pytest`, `ruff`.

## Code style

- Follow ruff's defaults; let `ruff format` decide formatting.
- Type hints on all public functions; prefer `dataclasses` for data types.
- Keep functions small and side effects (file I/O) at the edges.
