# Roadmap

The development plan for `tskmngr`, broken down into small, traceable steps in
the order they should be built. It's filled from planning sessions with the
maintainer and kept up to date as work lands.

- **What's planned** and in which order: milestones, top to bottom.
- **What's done**: checked steps, each linked to the PR that finished it.
- **What's next**: the first unchecked step whose dependencies are done.

## How to read and update this file

### Structure

- A **milestone** (`M1`, `M2`, …) is a meaningful, usable stage of the app,
  with a one-line goal.
- A **step** (`M1.1`, `M1.2`, …) is one unit of work, sized to fit roughly one
  pull request (see the PR policy in `AGENTS.md`).
- Step IDs are permanent. Never renumber or reuse them; if a step is dropped,
  mark it as dropped instead of deleting it.

### Step format

```markdown
- [ ] **M1.2** Short description · `feature/<name>` · depends on M1.1
```

| Status | Meaning |
| ------ | ------- |
| `[ ]`  | To do |
| `[x]`  | Done, with a link to the PR that finished it |
| `[-]`  | Dropped, with a short reason |

Finished steps keep their line and get the PR link appended, in the same
`[reference](link)` form as `CHANGELOG.md`:

```markdown
- [x] **M1.2** Short description · `feature/<name>` · [#7](https://github.com/Kevin-Brockers/tskmngr/pull/7)
```

### Rules

- Work top to bottom: take the first open step whose dependencies are done.
  Don't skip ahead without the maintainer's agreement.
- Update the step's status in the PR that implements it: mark it `[x]` with
  that PR's link (it becomes true when the PR is merged).
- New milestones and steps come from planning sessions with the maintainer.
  Agents may suggest additions, reorderings or splits, but don't make them
  without approval.
- If a step turns out bigger than one PR, split it into sub-steps
  (`M1.2a`, `M1.2b`, …) after agreeing with the maintainer.

## Milestones

### M0 · Project setup

Goal: conventions, tooling and documentation in place before any app code.

- [x] **M0.1** `AGENTS.md`, prek hooks, diff-review hook, branching policy
  and `CHANGELOG.md` · `docs/agents-md` · [#1](https://github.com/Kevin-Brockers/tskmngr/pull/1)
- [x] **M0.2** `ROADMAP.md` and its policy in `AGENTS.md` · `docs/roadmap` · [#2](https://github.com/Kevin-Brockers/tskmngr/pull/2)
- [x] **M0.3** Plan milestones M1 to M5, refined after review, and the storage
  format decisions in `AGENTS.md` · `docs/roadmap_mvp` · [#3](https://github.com/Kevin-Brockers/tskmngr/pull/3)

### M1 · Core

Goal: tasks can be created, saved, loaded, filtered and sorted in code, with no
UI. `models`, `taskfile`, `storage` and `query` don't import Textual.

- [x] **M1.1** Package skeleton: `pyproject.toml` (uv, approved baseline
  dependencies), committed `uv.lock`, `.gitignore`, `src/tskmngr` layout,
  `tskmngr` entry point that starts an empty Textual app, smoke test, and a
  GitHub Actions workflow running `ruff check`, `ruff format --check` and
  `pytest` on Python 3.12 to 3.14 and the newest stable release, started
  manually for now · `chore/project_skeleton` · [#5](https://github.com/Kevin-Brockers/tskmngr/pull/5)
- [x] **M1.2** `Task` dataclass, `Status` and `Priority` enums, ID generation
  (random 10-character Crockford base32, regenerated on collision with an
  existing ID) and field validation · `feature/task_model` · [#8](https://github.com/Kevin-Brockers/tskmngr/pull/8)
- [x] **M1.3** Markdown serialization with `ruamel.yaml` in round-trip mode:
  parse and render frontmatter and body in the documented format, keep unknown
  frontmatter keys, comments and formatting so an unchanged file saves back
  byte for byte, raise a clear error for malformed files (including values of
  the wrong type) · `feature/task_markdown` · [#10](https://github.com/Kevin-Brockers/tskmngr/pull/10)
- [x] **M1.4** Storage: resolve the tasks directory (`TSKMNGR_DIR` or the
  default), load all tasks with the ID taken from the filename and report
  malformed files, atomic save that refuses to overwrite a file changed on disk
  since it was loaded (reported as a conflict), delete by moving the file to
  `.trash/` · `feature/task_storage` · [#11](https://github.com/Kevin-Brockers/tskmngr/pull/11)
- [x] **M1.5** Query functions: filter by status, priority and tag, text
  search over title and notes, sort by due date, priority, created or updated,
  find a task by a unique ID prefix (shared by CLI and TUI) ·
  `feature/task_query` · [#12](https://github.com/Kevin-Brockers/tskmngr/pull/12)

### M2 · Command-line interface

Goal: tasks can be managed from the shell without the TUI. `tskmngr` with no
arguments still launches the TUI. Commands that act on one task take any
unique prefix of its ID.

- [x] **M2.1** CLI with subcommands (`argparse`) and `tskmngr add` with title,
  priority, due date and tags · `feature/cli_add` · [#18](https://github.com/Kevin-Brockers/tskmngr/pull/18)
- [x] **M2.2** `tskmngr list` with filter, search and sort options; malformed
  files reported on stderr · `feature/cli_list` · [#19](https://github.com/Kevin-Brockers/tskmngr/pull/19)
- [x] **M2.3** `tskmngr show`, `edit` (fields) and `done` ·
  `feature/cli_show_edit` · [#20](https://github.com/Kevin-Brockers/tskmngr/pull/20)
- [x] **M2.4** `tskmngr delete` with a confirmation prompt (`--yes` to skip) ·
  `feature/cli_delete` · [#22](https://github.com/Kevin-Brockers/tskmngr/pull/22)

### M3 · TUI

Goal: the full MVP in the interactive TUI. M1 to M3 together are the first
usable release. Every key binding gets a stable `id`, so M4.3 can remap it
through Textual's keymap. A save that hits a conflict (see M1.4) is shown to
the user and the task reloaded, never overwritten.

- [x] **M3.1** Task list screen loaded from storage; malformed files shown as a
  warning, not hidden · `feature/tui_task_list` · [#23](https://github.com/Kevin-Brockers/tskmngr/pull/23)
- [x] **M3.2** Task detail view with all fields and rendered notes ·
  `feature/tui_task_detail` · [#25](https://github.com/Kevin-Brockers/tskmngr/pull/25)
- [x] **M3.3** Form to create and edit a task (title, status, priority, due
  date, tags) with validation · `feature/tui_task_form` · [#26](https://github.com/Kevin-Brockers/tskmngr/pull/26)
- [x] **M3.4** Quick status change and delete with confirmation from the list ·
  `feature/tui_task_actions` · [#27](https://github.com/Kevin-Brockers/tskmngr/pull/27)
- [x] **M3.5** Edit notes in a built-in text area ·
  `feature/tui_notes_editor` · [#29](https://github.com/Kevin-Brockers/tskmngr/pull/29)
- [x] **M3.6** Open the task file in `$EDITOR` (TUI suspended) and reload it
  afterwards · `feature/tui_external_editor` · [#30](https://github.com/Kevin-Brockers/tskmngr/pull/30)
- [x] **M3.7** Filter and search the task list · `feature/tui_filter_search` ·
  [#31](https://github.com/Kevin-Brockers/tskmngr/pull/31)
- [ ] **M3.8** Sort the task list · `feature/tui_sorting` · depends on M3.1,
  M1.5
- [ ] **M3.9** README: installation, CLI usage, TUI keys and the task file
  format · `docs/readme_usage` · depends on all of M2, M3.1–M3.8

### M4 · External edits and configuration

Goal: the app stays in sync with hand-edited files and can be configured.

- [ ] **M4.1** Detect task files changed, added or removed on disk while the
  app runs, by polling the tasks directory's file times and sizes on a timer,
  and reload them · `feature/watch_tasks_dir` · depends on M3.1
- [ ] **M4.2** Config file (TOML via `tomllib`): tasks directory
  (`TSKMNGR_DIR` first, then the config file, then the default), default sort,
  theme · `feature/config_file` · depends on M1.4, M2.2, M3.8
- [ ] **M4.3** Custom keybindings from the config file, applied through
  Textual's keymap · `feature/custom_keybindings` · depends on M4.2, all of M3

### M5 · Subtasks and recurring tasks

Goal: richer task structure. The storage format for both must be agreed with
the maintainer before starting, and `AGENTS.md` updated to match.

- [ ] **M5.1** Subtasks as a checklist within a task, shown and toggled in the
  TUI · `feature/subtasks` · depends on M3.5
- [ ] **M5.2** Recurring tasks: a repeat rule, and core logic that creates the
  next occurrence when a task is marked done, used by both `tskmngr done` and
  the TUI · `feature/recurring_tasks` · depends on M2.3, M3.4
