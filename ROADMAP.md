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
  and `CHANGELOG.md` · `docs/agents-md` · [#1](https://github.com/Kevin-Brockers/tskmngr/pull/1).
  Changed in [#45](https://github.com/Kevin-Brockers/tskmngr/pull/45): the
  diff review before every commit and its hook are gone; agents commit and
  push to their working branch without asking
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
- [x] **M3.8** Sort the task list · `feature/tui_sorting` · [#32](https://github.com/Kevin-Brockers/tskmngr/pull/32)
- [x] **M3.9** README: installation, CLI usage, TUI keys and the task file
  format · `docs/readme_usage` · [#33](https://github.com/Kevin-Brockers/tskmngr/pull/33)

### M4 · External edits and configuration

Goal: the app stays in sync with hand-edited files and can be configured.

- [x] **M4.1** Detect task files changed, added or removed on disk while the
  app runs, by polling the tasks directory's file times and sizes on a timer,
  and reload them · `feature/watch_tasks_dir` · [#35](https://github.com/Kevin-Brockers/tskmngr/pull/35)
- [x] **M4.2** Config file (JSON via `json`) at `~/.tskmngr/config.json`:
  tasks directory (the config's `tasks_dir` first, then `TSKMNGR_DIR`, then
  the default), default sort, theme, and how often M4.1 polls the tasks
  directory · `feature/config_file` · [#36](https://github.com/Kevin-Brockers/tskmngr/pull/36)
- [x] **M4.3** Custom keybindings from the config file, applied through
  Textual's keymap · `feature/custom_keybindings` · [#37](https://github.com/Kevin-Brockers/tskmngr/pull/37)

### M5 · Subtasks and recurring tasks

Goal: richer task structure. The storage format for both must be agreed with
the maintainer before starting, and `AGENTS.md` updated to match.

- [x] **M5.1** Subtasks as a checklist within a task, shown and toggled in the
  TUI · `feature/subtasks` · [#38](https://github.com/Kevin-Brockers/tskmngr/pull/38)
- [x] **M5.2** Recurring tasks: a repeat rule, and core logic that creates the
  next occurrence when a task is marked done, used by both `tskmngr done` and
  the TUI · `feature/recurring_tasks` ·
  [#39](https://github.com/Kevin-Brockers/tskmngr/pull/39), [#40](https://github.com/Kevin-Brockers/tskmngr/pull/40). Split into:
  - [x] **M5.2a** Core and CLI: `repeat` and `repeat_from` in the task file,
    the next-occurrence logic, `tskmngr done` and `edit --status done`,
    `add`/`edit --repeat`, and the rule in `tskmngr show` ·
    `feature/recurring_tasks_core` · [#39](https://github.com/Kevin-Brockers/tskmngr/pull/39)
  - [x] **M5.2b** TUI: repeat field in the form, a marker in the task list, the
    rule in the detail view, and the next occurrence created by `s`, the form
    and the subtask auto-done · `feature/recurring_tasks_tui` · [#40](https://github.com/Kevin-Brockers/tskmngr/pull/40)

### M6 · Settings

Goal: the TUI's task list columns can be arranged, and the config file can be viewed and edited from the CLI.

- [x] **M6.1** Order of the TUI task list columns: a `columns` config key,
  a list of column names whose order is the display order, with columns
  left out hidden; document it in the README and update `AGENTS.md` to
  match · `feature/tui_column_order` · [#50](https://github.com/Kevin-Brockers/tskmngr/pull/50)
- [x] **M6.2** `tskmngr config` prints the config file's path and its
  settings, `tskmngr config get <key>` prints one setting, and
  `tskmngr config edit` opens the file in `$VISUAL`/`$EDITOR`, then checks it
  the way loading does and reports any error naming the key; document the
  command in the README and update `AGENTS.md` to match ·
  `feature/cli_config` · [#52](https://github.com/Kevin-Brockers/tskmngr/pull/52)

### M8 · Deleted tasks view

Goal: the tasks deleted into `.trash/` can be seen in the TUI, in a view below
the task list that can be hidden. Listed before M7 and built first; the step
IDs keep their numbers. The view only lists them: restoring a task stays
moving its file back by hand.

- [x] **M8.1** Core: list the deleted tasks in `.trash/`, with the delete
  time taken from each file's name (`<id>.<delete time>.md`, including the
  `-N` that tells deletes in the same second apart), newest delete first;
  each delete of a task is its own entry, and files that can't be read are
  reported, never hidden; no Textual · `feature/trash_listing` · [#54](https://github.com/Kevin-Brockers/tskmngr/pull/54)
- [x] **M8.2** TUI: a read-only view of the deleted tasks in the bottom
  quarter of the task list screen's height, newest delete first, reloaded
  when files in `.trash/` change on disk; `t` (binding id
  `task_list.toggle_trash`, remappable through `keybindings`) shows or hides
  it until the app exits, and it starts shown · `feature/tui_trash_view` ·
  [#55](https://github.com/Kevin-Brockers/tskmngr/pull/55)
- [x] **M8.3** Config keys `trash_columns`, the view's columns in display
  order from the `columns` names plus `deleted` (the delete time), checked
  like `columns`, default `["title", "deleted", "id"]`; and `show_trash`,
  whether the view starts shown, default `true`; both in the default config
  file; document them and the view in the README and update `AGENTS.md` to
  match · `feature/trash_view_config` · [#56](https://github.com/Kevin-Brockers/tskmngr/pull/56).
  Changed in [#61](https://github.com/Kevin-Brockers/tskmngr/pull/61) (M9.3):
  the default `trash_columns` is `["title", "tags", "deleted", "id"]`

### M9 · Filtering and task list columns

Goal: the filter also finds tasks from partial or misspelled input, and the
TUI's tables are easier to read. Listed before M7 and built first, after M8;
the step IDs keep their numbers.

- [x] **M9.1** Partial matches in the filter, the same in the TUI's filter
  bar and `tskmngr list` (shared in `query.py`) · `feature/partial_filter` ·
  [#58](https://github.com/Kevin-Brockers/tskmngr/pull/58), [#59](https://github.com/Kevin-Brockers/tskmngr/pull/59). Split into:
  - [x] **M9.1a** Prefixes: `#tag` matches every tag that starts with it
    (`#err` finds `errands`), and `status:` and `priority:` take the start of
    a value (`status:do` finds doing and done, `priority:hi` finds high); a
    value nothing starts with is still an error · `feature/filter_prefixes` ·
    [#58](https://github.com/Kevin-Brockers/tskmngr/pull/58)
  - [x] **M9.1b** Typo-tolerant words: a word also matches a word in the
    title or notes that's close to it (`mlik` finds milk), and `#tag` a tag;
    as agreed with the maintainer, a typo is a wrong, missing or extra letter
    or two swapped neighbours (counted in plain Python rather than with
    `difflib`, whose scores can't tell typos from different short words),
    with 1 allowed for 4 to 7 letters, 2 for more and none for 3 or fewer ·
    `feature/filter_typos` · [#59](https://github.com/Kevin-Brockers/tskmngr/pull/59)
- [x] **M9.2** The columns the TUI task list shows only while it's sorted by
  them (created, updated) go last, at the far right, instead of before
  Title; update the README and `AGENTS.md` to match ·
  `feature/sort_column_last` · [#60](https://github.com/Kevin-Brockers/tskmngr/pull/60)
- [x] **M9.3** Tags column in the TUI: `tags` joins the column names of
  `columns` and `trash_columns` and shows a task's tags separated by commas;
  the defaults gain it after `title` (`["id", "status", "priority", "due",
  "title", "tags"]` and `["title", "tags", "deleted", "id"]`), and while it
  isn't shown the title keeps its `#tags`, so config files without it still
  show them; document it in the README and update `AGENTS.md` to match ·
  `feature/tags_column` · [#61](https://github.com/Kevin-Brockers/tskmngr/pull/61)

### M7 · Config home and synced tasks

Goal: settings live in `~/.tskmngr/`, and the tasks directory can be kept in a
separate, usually private, git repository. How that repository is set up and
synced must be agreed with the maintainer before starting M7.2, and
`AGENTS.md` updated to match.

- [x] **M7.1** Config file at `~/.tskmngr/config.json` only: drop
  `~/.config/tskmngr/config.json` and `TSKMNGR_CONFIG`; on first run, if the
  file doesn't exist, write a default config there (never overwriting an
  existing one); the config's `tasks_dir` comes first for the tasks
  directory, with `TSKMNGR_DIR` only as a fallback when it isn't set, then
  the default (so the default config leaves `tasks_dir` out); document the
  location, that it's created on first run, what the default file contains
  and the tasks directory order in the README, and update `AGENTS.md` to
  match · `feature/config_home` · [#42](https://github.com/Kevin-Brockers/tskmngr/pull/42)
- [x] **M7.2** Tasks directory in a separate git repository, through the `git`
  CLI (`subprocess`, no new dependency), as agreed with the maintainer and
  described in `AGENTS.md` ("Synced tasks"): pull before changing or listing
  tasks, commit and push after every change, and `tskmngr sync` to sync by
  hand · `feature/git_sync` · depends on M6.1 ·
  [#64](https://github.com/Kevin-Brockers/tskmngr/pull/64), [#65](https://github.com/Kevin-Brockers/tskmngr/pull/65). Split into:
  - [x] **M7.2a** Core and CLI: a `tasks_repo` config key, either a remote
    URL cloned into `~/.tskmngr/remote_task_dir` or a local folder that's
    already a git repository, used as the tasks directory; while it's set,
    `tasks_dir` and `TSKMNGR_DIR` aren't used, and `tskmngr config` notes
    whether it's local or remote; a fine-grained access token read from the
    `TSKMNGR_GIT_TOKEN` env var and handed to git per command, never written
    to `.git/config`, the remote URL or any output; `add`, `edit`, `done` and
    `delete` pull, commit and push, `list` pulls, and `tskmngr sync` pulls
    and pushes (an error while `tasks_repo` isn't set); a failed or offline
    sync is a warning and catches up on the next one, and a pull conflict is
    reported, never resolved by overwriting a task; document it in the
    README and move it in `AGENTS.md` from planned to the config file and
    storage sections · `feature/git_sync_core` · [#64](https://github.com/Kevin-Brockers/tskmngr/pull/64)
  - [x] **M7.2b** TUI: pull at start, commit and push after each change, a
    sync key, and sync errors and conflicts shown to the user ·
    `feature/git_sync_tui` · depends on M7.2a · [#65](https://github.com/Kevin-Brockers/tskmngr/pull/65)

### M10 · Documentation fixes

Goal: `AGENTS.md` and `ROADMAP.md` match the code and each other.

- [x] **M10.1** `AGENTS.md`'s `config get` line: `trash_columns` is printed as
  JSON too, as the code and README already do · `docs/config_get_trash_columns` ·
  [#67](https://github.com/Kevin-Brockers/tskmngr/pull/67)
- [x] **M10.2** M8.3 still gives the old default for `trash_columns`
  (`["title", "deleted", "id"]`); note on it that M9.3 changed it, the way
  M0.1 notes #45 · `docs/roadmap_trash_default` ·
  [#70](https://github.com/Kevin-Brockers/tskmngr/pull/70)

### M11 · Tag suggestions

Goal: the TUI helps reuse existing tags instead of creating near-duplicates.

- [x] **M11.1** Suggest existing tags in the TUI form's Tags field, for new
  and edited tasks alike: while a tag is being typed, the rest of the first
  existing tag (alphabetically, from the loaded tasks) that starts with it is
  shown greyed out and → accepts it, through Textual's `Suggester` (no new
  dependency); document it in the README · `feature/tui_tag_suggestions` ·
  [#74](https://github.com/Kevin-Brockers/tskmngr/pull/74)

### M12 · Tasks repository layout and setup

Goal: a tasks repository has a fixed layout, `AGENTS.md` at its root and the
tasks in `tasks/`, and `tskmngr remote init` sets up a new one.

- [x] **M12.1** Repository layout: while `tasks_repo` is set, the tasks
  directory is the repository's `tasks/` folder (deleted tasks in
  `tasks/.trash/`), for remote URLs and local folders alike; a repository
  without `tasks/` stops every command but `config` with an error saying to
  move the task files and `.trash/` into `tasks/`, and nothing is moved;
  document it in the README and update `AGENTS.md` ("Synced tasks") to match
  · `feature/tasks_repo_layout` ·
  [#75](https://github.com/Kevin-Brockers/tskmngr/pull/75)
- [x] **M12.2** `tskmngr remote init URL` sets up an existing, empty remote
  repository: clones it into `~/.tskmngr/remote_task_dir`, adds `AGENTS.md`
  and `tasks/.trash/.gitkeep` (git doesn't keep empty folders), commits and
  pushes them, then writes `tasks_repo` into the config file with `json`
  (keys and values kept, whitespace rewritten); it stops, changing nothing,
  if the clone folder exists, the repository isn't empty or the config
  already has another `tasks_repo`. The repository's `AGENTS.md` comes from a
  template shipped with tskmngr, is written only by this command and never
  rewritten, and describes the task file format (frontmatter fields, the
  filename as ID, `.trash/`, subtasks, `repeat`) and that agents don't delete
  task files. Document it in the README and update `AGENTS.md` (the config
  file is no longer only read) · `feature/remote_init` · depends on M12.1 ·
  [#76](https://github.com/Kevin-Brockers/tskmngr/pull/76)

### M13 · Editor setting

Goal: opening a task or the config file in an editor works out of the box on
macOS and Linux, and the editor is set in the config file. Editing tasks
inside the TUI (the form, its notes and every other key) stays as it is; the
editor is only for `o` and `tskmngr config edit`.

- [x] **M13.1** `editor` config key, `vim` (the default) or `nano`: the
  editor the TUI's `o` and `tskmngr config edit` open files in, run in the
  same terminal; `$VISUAL` and `$EDITOR` are no longer read; the default
  config file gains `"editor": "vim"`, and any other value stops the CLI and
  the TUI like other invalid settings (`config edit` opens the file in vim
  when it can't be read, so it can be fixed); an editor that isn't
  installed is an error naming it and the `editor` key; find and fix why
  opening an editor fails on the maintainer's Mac; shown by `tskmngr config`
  and `config get`; document both editors in the README and update
  `AGENTS.md` to match · `feature/editor_setting` ·
  [#78](https://github.com/Kevin-Brockers/tskmngr/pull/78)

### M14 · First release

Goal: tskmngr 0.1.0 is released from `main`, checked by CI, with a GitHub
Release to install it from.

- [x] **M14.1** CI runs on its own, on Linux and macOS: the workflow is split
  into `ci-linux.yml` (ruff, and pytest on Python 3.12 to 3.14 and the newest
  one) and `ci-macos.yml` (pytest on Python 3.12 to 3.14); both run on pull
  requests into `dev` and `main` (into `main`, only from `dev`) and on pushes
  to them, and can still be started by hand; the README shows a badge per
  workflow (its last result on `main`) and one listing the tested Python
  versions; document the CI in `AGENTS.md`, next to the local checks it
  doesn't replace · `chore/ci_triggers` ·
  [#79](https://github.com/Kevin-Brockers/tskmngr/pull/79)
- [ ] **M14.2** Release workflow: pushing a tag like `v0.1.0` builds the
  wheel and sdist with `uv build` and creates a GitHub Release with them
  attached and that version's changelog section as its notes, using the `gh`
  CLI on the runner (no new action); it stops if the tag doesn't match the
  version in `pyproject.toml` · `chore/release_workflow` · depends on M14.1
- [ ] **M14.3** Prepare 0.1.0: version `0.1.0` in `pyproject.toml` and
  `uv.lock`; the README's status and installation updated (install with
  `uv tool install` from the release's tag); a `RELEASING.md` with the steps
  (the maintainer's `dev` → `main` PR with the changelog's `[Unreleased]`
  renamed to `[0.1.0] - <date>`, merge, tag `v0.1.0` on `main`, push the
  tag, then move `dev` to `0.2.0.dev0`) · `chore/release_0_1_0` · depends on
  M13.1, M14.2
