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

### M1 · Core

Goal: tasks can be created, saved, loaded, filtered and sorted in code, with no
UI. `models`, `storage` and `query` don't import Textual.

- [ ] **M1.1** Package skeleton: `pyproject.toml` (uv, approved baseline
  dependencies), `src/tskmngr` layout, `tskmngr` entry point that starts an
  empty Textual app, smoke test · `chore/project_skeleton` · depends on M0.2
- [ ] **M1.2** `Task` dataclass, `Status` and `Priority` enums, ID generation
  and field validation · `feature/task_model` · depends on M1.1
- [ ] **M1.3** Markdown serialization: parse and render frontmatter and body,
  keep unknown frontmatter keys, raise a clear error for malformed files ·
  `feature/task_markdown` · depends on M1.2
- [ ] **M1.4** Storage: resolve the tasks directory (`TSKMNGR_DIR` or the
  default), load all tasks and report malformed files, atomic save, delete ·
  `feature/task_storage` · depends on M1.3
- [ ] **M1.5** Query functions: filter by status, priority and tag, text
  search over title and notes, sort by due date, priority, created or updated
  (shared by CLI and TUI) · `feature/task_query` · depends on M1.2

### M2 · Command-line interface

Goal: tasks can be managed from the shell without the TUI. `tskmngr` with no
arguments still launches the TUI.

- [ ] **M2.1** CLI with subcommands (`argparse`) and `tskmngr add` with title,
  priority, due date and tags · `feature/cli_add` · depends on M1.4
- [ ] **M2.2** `tskmngr list` with filter, search and sort options ·
  `feature/cli_list` · depends on M2.1, M1.5
- [ ] **M2.3** `tskmngr show`, `edit` (fields) and `done` ·
  `feature/cli_show_edit` · depends on M2.1
- [ ] **M2.4** `tskmngr delete` with a confirmation prompt (`--yes` to skip) ·
  `feature/cli_delete` · depends on M2.1

### M3 · TUI

Goal: the full MVP in the interactive TUI. M1 to M3 together are the first
usable release.

- [ ] **M3.1** Task list screen loaded from storage; malformed files shown as a
  warning, not hidden · `feature/tui_task_list` · depends on M1.4
- [ ] **M3.2** Task detail view with all fields and rendered notes ·
  `feature/tui_task_detail` · depends on M3.1
- [ ] **M3.3** Form to create and edit a task (title, status, priority, due
  date, tags) with validation · `feature/tui_task_form` · depends on M3.2
- [ ] **M3.4** Quick status change and delete with confirmation from the list ·
  `feature/tui_task_actions` · depends on M3.1
- [ ] **M3.5** Edit notes in a built-in text area ·
  `feature/tui_notes_editor` · depends on M3.3
- [ ] **M3.6** Open the task file in `$EDITOR` (TUI suspended) and reload it
  afterwards · `feature/tui_external_editor` · depends on M3.2
- [ ] **M3.7** Filter and search the task list · `feature/tui_filter_search` ·
  depends on M3.1, M1.5
- [ ] **M3.8** Sort the task list · `feature/tui_sorting` · depends on M3.1,
  M1.5

### M4 · External edits and configuration

Goal: the app stays in sync with hand-edited files and can be configured.

- [ ] **M4.1** Detect task files changed, added or removed on disk while the
  app runs and reload them · `feature/watch_tasks_dir` · depends on M3.1
- [ ] **M4.2** Config file (TOML via `tomllib`): tasks directory, default sort,
  theme · `feature/config_file` · depends on M1.4
- [ ] **M4.3** Custom keybindings from the config file ·
  `feature/custom_keybindings` · depends on M4.2, M3.8

### M5 · Subtasks and recurring tasks

Goal: richer task structure. The storage format for both must be agreed with
the maintainer before starting, and `AGENTS.md` updated to match.

- [ ] **M5.1** Subtasks as a checklist within a task, shown and toggled in the
  TUI · `feature/subtasks` · depends on M3.5
- [ ] **M5.2** Recurring tasks: a repeat rule that creates the next occurrence
  when a task is marked done · `feature/recurring_tasks` · depends on M3.4
