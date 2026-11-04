# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Each entry starts with a link to its pull request, e.g.
`[#12](https://github.com/Kevin-Brockers/tskmngr/pull/12) - Description`, or to
its commit for changes that reached `dev` or `main` without a pull request.

## [Unreleased]

### Added

- [#1](https://github.com/Kevin-Brockers/tskmngr/pull/1) - `AGENTS.md` with project overview, working etiquette, tech stack, task
  storage format and working conventions for coding agents
- [#1](https://github.com/Kevin-Brockers/tskmngr/pull/1) - prek pre-commit hooks: file hygiene checks, ruff lint/format and a
  guard against committing to `main` and `dev`
- [#1](https://github.com/Kevin-Brockers/tskmngr/pull/1) - Claude Code hook that shows the staged diff and asks for approval
  before every `git commit`
- [#1](https://github.com/Kevin-Brockers/tskmngr/pull/1) - `CHANGELOG.md` and the changelog policy in `AGENTS.md`
- [#1](https://github.com/Kevin-Brockers/tskmngr/pull/1) - Branching policy: `feature/`, `fix/`, `docs/` and `chore/` branches
  with pull requests against `dev`; `dev` → `main` only for releases
- [#2](https://github.com/Kevin-Brockers/tskmngr/pull/2) - `ROADMAP.md` with milestones and traceable steps, and the roadmap
  policy in `AGENTS.md`
- [#3](https://github.com/Kevin-Brockers/tskmngr/pull/3) - Roadmap milestones M1 to M5: core, CLI, TUI, external edits and
  configuration, subtasks and recurring tasks, with the planned modules in the
  `AGENTS.md` project layout
- [#5](https://github.com/Kevin-Brockers/tskmngr/pull/5) - Package skeleton: `pyproject.toml` with pinned dependencies, `uv.lock`,
  `src/tskmngr` layout, `tskmngr` entry point that starts an empty Textual app,
  smoke tests and a GitHub Actions workflow, started manually for now, that runs
  ruff and the tests on Python 3.12 to 3.14 and the newest stable release
- [#8](https://github.com/Kevin-Brockers/tskmngr/pull/8) - Task model: `Task` dataclass with `Status` and `Priority` enums,
  field validation and random 10-character Crockford base32 IDs
- [#10](https://github.com/Kevin-Brockers/tskmngr/pull/10) - Task file format: convert tasks to and from Markdown with YAML
  frontmatter, keeping unknown keys, comments and formatting on save, and
  reporting malformed files with the field, line and a hint to quote values of
  the wrong type
- [#11](https://github.com/Kevin-Brockers/tskmngr/pull/11) - Task storage: tasks directory from `TSKMNGR_DIR` or the default, load
  all tasks with malformed files reported, atomic saves that refuse to
  overwrite a file changed on disk since it was loaded, and delete by moving the
  file to `.trash/` under a name with the delete time
- [#12](https://github.com/Kevin-Brockers/tskmngr/pull/12) - Task queries: filter by status, priority and tags, search title
  and notes for every word of a query, sort by due date, priority, created
  or updated time, and find a task by a unique, case-insensitive ID prefix
- [#13](https://github.com/Kevin-Brockers/tskmngr/pull/13) - `README.md` with an overview, the project status, how to run it from
  source, the task file format and the development commands
- [#18](https://github.com/Kevin-Brockers/tskmngr/pull/18) - `tskmngr add` to add a task from the shell, with a title and
  optional `--priority`, `--due` (YYYY-MM-DD) and repeatable `--tag`; it
  prints the new task's ID. `tskmngr` without a command still opens the TUI
- [#19](https://github.com/Kevin-Brockers/tskmngr/pull/19) - `tskmngr list` to list tasks in aligned columns, by default the
  ones not done yet, soonest due first; filter with `--status`, `--all`,
  `--priority` and `--tag`, search title and notes by giving words, and pick
  the order with `--sort` and `--reverse`. Malformed task files are reported
  on stderr
- [#20](https://github.com/Kevin-Brockers/tskmngr/pull/20) - `tskmngr show` to print all fields and the notes of a task,
  `tskmngr edit` to change its title, status, priority, due date (`--no-due`
  removes it) and tags (`--tag`, `--untag`, `--clear-tags`), and
  `tskmngr done` to mark it done. Each takes any unique prefix of the task's
  ID; a prefix that picks a malformed file reports that file's error
- [#22](https://github.com/Kevin-Brockers/tskmngr/pull/22) - `tskmngr delete` to move a task's file into `.trash/`, taking any
  unique prefix of its ID. It asks for confirmation first; `--yes` skips the
  question, and without a terminal to ask on (piped input, scripts) it refuses
  unless `--yes` is given
- [#23](https://github.com/Kevin-Brockers/tskmngr/pull/23) - The TUI opens on a list of all tasks, done ones included, soonest
  due first, with their ID, status, priority, due date, title and tags. Task
  files that can't be loaded are named with their error in a warning panel
  above the list instead of being hidden. The header shows the tasks directory
- [#25](https://github.com/Kevin-Brockers/tskmngr/pull/25) - Enter on a task in the TUI list, or clicking its highlighted row,
  opens a detail view with all its fields and its notes rendered as Markdown;
  the header shows the task's file. Escape goes back to the list
- [#26](https://github.com/Kevin-Brockers/tskmngr/pull/26) - A form in the TUI to create a task (`n` on the list) or edit
  one (`e` on the list or the detail view): title, status, priority, due date
  (YYYY-MM-DD) and tags (separated by spaces or commas). Problems are shown
  under their field when saving with ctrl+s; Escape cancels. If the task's file
  changed or was deleted on disk meanwhile, nothing is overwritten: the error
  is shown and the task reloaded from disk
- [#27](https://github.com/Kevin-Brockers/tskmngr/pull/27) - On the TUI task list, `s` moves the task under the cursor to the
  next status (todo → doing → done → todo) and saves it right away, and `d`
  asks whether to delete it (No has the focus; `y` or the Yes button deletes)
  and moves its file into `.trash/`. If the file changed or was deleted on
  disk meanwhile, nothing is overwritten or deleted: the error is shown and
  the list reloaded from disk
- [#21](https://github.com/Kevin-Brockers/tskmngr/pull/21) - `init-work` Claude Code skill that reads `AGENTS.md` and `ROADMAP.md`
  and summarizes the next open roadmap step
- [#28](https://github.com/Kevin-Brockers/tskmngr/pull/28) - `sync-dev` Claude Code skill that updates `dev` from GitHub and
  deletes local branches fully merged into it, keeping `main` and `dev`;
  branches on GitHub are left alone
- [#29](https://github.com/Kevin-Brockers/tskmngr/pull/29) - The TUI task form has a Notes text area below the tags, to write a
  new task's notes or edit a task's notes as plain text (Enter starts a new
  line, Tab moves on, ctrl+s saves). Whitespace-only notes are saved as no
  notes, and edited notes end with a newline; notes left untouched are saved
  byte for byte. Escape on a form with changes asks before discarding them
  (No has the focus), and Enter on the tags now moves to the notes instead of
  saving
- [#30](https://github.com/Kevin-Brockers/tskmngr/pull/30) - `o` on the TUI task list or detail view opens the task's file in
  `$VISUAL` or `$EDITOR` (with any arguments, e.g. `code --wait`) while the TUI
  is suspended, and reloads the task when the editor exits. The app never
  writes the file afterwards; a file left malformed is reported and shown in
  the list's warning panel. If neither variable is set, the editor can't be
  started or the file is gone, that's shown instead
- [#31](https://github.com/Kevin-Brockers/tskmngr/pull/31) - `/` on the TUI task list opens a filter bar that narrows the list
  as you type: words are searched in titles and notes, `#tag` needs a tag, and
  `status:` and `priority:` restrict to a value (repeat for any of several).
  A word with an unknown or missing value is named below the bar and left out
  of the filter. Enter goes back to the list and keeps the filter, Escape
  clears it, and the filter stays applied when the list reloads
- [#32](https://github.com/Kevin-Brockers/tskmngr/pull/32) - `S` on the TUI task list sorts it by the next key (due date,
  priority, created, updated), each in its default direction, and `R` reverses
  the order; tasks without a due date stay last. The sorted column's header
  shows ▲ or ▼, a Created or Updated column is shown while sorting by it, and
  the cursor stays on the same task. The sort lasts until the app exits
- [#33](https://github.com/Kevin-Brockers/tskmngr/pull/33) - README: installing with `uv tool install`, command-line usage with
  every command and its options, the TUI keys of each screen, and an updated
  project status
- [#35](https://github.com/Kevin-Brockers/tskmngr/pull/35) - The TUI notices task files changed, added or removed on disk
  while it runs, by checking their modification times and sizes every two
  seconds, and reloads the list (the cursor stays on the same task) and the
  task in the detail view; a task deleted on disk closes the detail view. An
  open form isn't reloaded and keeps what was typed: if its task's file
  changed or was deleted, the conflict is shown right away, and saving is
  refused as before
- [#36](https://github.com/Kevin-Brockers/tskmngr/pull/36) - Config file `~/.config/tskmngr/config.json` (`TSKMNGR_CONFIG`
  points to another file), a JSON object with optional `tasks_dir` (a relative
  path is read from the config file's folder; `TSKMNGR_DIR` still comes
  first), `sort` and `reverse` for the TUI list and `tskmngr list`, the TUI's
  `theme`, and `poll_interval`, the seconds between the TUI's checks for
  changed task files (0 turns them off). Invalid JSON, unknown keys and
  unusable values stop the CLI and the TUI with an error naming the file and
  the key
- [#37](https://github.com/Kevin-Brockers/tskmngr/pull/37) - `keybindings` in the config file changes the TUI's keys: an object of
  binding ids (like `task_list.new`) and their keys, applied through Textual's
  keymap and shown in the footer. An unknown binding id, or two bindings on
  one screen sharing a key (or taking `Ctrl+Q` or `Ctrl+C`), stops the TUI with
  an error naming the file and the binding
- [#38](https://github.com/Kevin-Brockers/tskmngr/pull/38) - Subtasks: the checklist items (`- [ ]`, `- [x]`) in a task's notes.
  The TUI's task list shows their progress after the title, like `[1/3]`, and
  `tskmngr show` and the detail view show it as a `Subtasks` field. In the
  detail view, Space, Enter or a click checks or unchecks one and saves the
  task; checking the last open one marks the task done, and unchecking one of
  a done task moves it back to doing
- [#39](https://github.com/Kevin-Brockers/tskmngr/pull/39) - Recurring tasks: a `repeat` rule (`daily`, `weekly`, `monthly`,
  `yearly` or `every N days|weeks|months|years`), set with `tskmngr add
  --repeat` and `tskmngr edit --repeat`/`--no-repeat` and shown by `tskmngr
  show` and the TUI's detail view. `tskmngr done` and `tskmngr edit --status
  done` add the next occurrence as a new task, due one interval after the old
  due date (skipping past ones), and print its ID; monthly and yearly rules
  keep the day of the month via `repeat_from`
- [#40](https://github.com/Kevin-Brockers/tskmngr/pull/40) - Recurring tasks in the TUI: a Repeat field in the task form, `↻`
  after the title of repeating tasks in the task list, and the next
  occurrence added (and shown in a notification) when `s`, saving the form or
  checking the last open subtask marks a repeating task done
- [#41](https://github.com/Kevin-Brockers/tskmngr/pull/41) - Roadmap milestone M6: the config file in `~/.tskmngr/`, created on
  first run, with its `tasks_dir` before `TSKMNGR_DIR`, and the tasks
  directory in a separate git repository
- [7982e5c](https://github.com/Kevin-Brockers/tskmngr/commit/7982e5c9b62c955e9fe1f08a551be97f5dabf555) - Initial repository with `README.md` and MIT license

### Changed

- [#3](https://github.com/Kevin-Brockers/tskmngr/pull/3) - Approved dependency baseline: `ruamel.yaml` replaces `pyyaml` so
  saving a task keeps frontmatter comments and formatting, and `pytest-asyncio`
  is added for Textual's async UI tests
- [#3](https://github.com/Kevin-Brockers/tskmngr/pull/3) - Task storage format in `AGENTS.md`: the filename is the task's ID (no
  `id` key in the frontmatter), deleted tasks move to `.trash/`, and a value of
  the wrong type makes a file malformed
- [#23](https://github.com/Kevin-Brockers/tskmngr/pull/23) - `rich` is a pinned direct dependency and part of the approved
  dependency baseline, since the TUI imports it; it was already installed
  with Textual, at the same version
- [#34](https://github.com/Kevin-Brockers/tskmngr/pull/34) - Roadmap M4.2: the config file lives at
  `~/.config/tskmngr/config.toml` (`TSKMNGR_CONFIG` overrides the path) and
  sets how often the TUI polls the tasks directory for changes; the path is
  also in `AGENTS.md`
- [#36](https://github.com/Kevin-Brockers/tskmngr/pull/36) - The config file is JSON (`config.json`, read with the standard
  library's `json`) instead of the planned TOML, in `ROADMAP.md` and
  `AGENTS.md`; `config` joins the modules that don't import Textual
- [#42](https://github.com/Kevin-Brockers/tskmngr/pull/42) - The config file is `~/.tskmngr/config.json`, and tskmngr writes it
  with the default settings (all but `tasks_dir`) on first run if it doesn't
  exist, never overwriting one; `~/.config/tskmngr/config.json` and
  `TSKMNGR_CONFIG` are no longer read, with a warning on stderr while the old
  file exists. The config's `tasks_dir` now comes before `TSKMNGR_DIR`

### Fixed

- [#14](https://github.com/Kevin-Brockers/tskmngr/pull/14) - A task file with old Mac line endings (`\r` only) no longer crashes
  loading the tasks directory; such files now load like LF and CRLF files
- [#15](https://github.com/Kevin-Brockers/tskmngr/pull/15) - The diff-review hook now catches commits written as `git -C <path>
  commit`, `git -c <key>=<value> commit`, `(git commit …)` or with a path to
  `git`, refuses staging and committing in one command (its preview would
  miss what gets staged), and blocks the commit instead of letting it through
  when `jq` is missing or the preview fails
- [#16](https://github.com/Kevin-Brockers/tskmngr/pull/16) - Malformed task files are reported in plain words instead of Python
  type names, e.g. `due: expected a date like 2026-11-01, got the number 5`
  instead of `due: expected date or None, got int`
- [#17](https://github.com/Kevin-Brockers/tskmngr/pull/17) - Task files starting with a UTF-8 byte order mark, or with spaces or
  tabs after a `---` line, load instead of being reported as malformed; the
  byte order mark is kept when the task is saved
