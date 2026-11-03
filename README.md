# tskmngr

A terminal task manager with an interactive TUI, written in Python. Tasks are
plain Markdown files, so they stay readable and editable outside the app.

## Status

Usable, but not released yet. [`ROADMAP.md`](ROADMAP.md) has the full plan;
in short:

- **Core** (done): task model, Markdown file format, storage, filtering,
  search and sorting
- **Command-line interface** (done): add, list, show, edit, complete and
  delete tasks from the shell
- **TUI** (done): the full app, with a task list, detail view, forms, a notes
  editor, editing in `$EDITOR`, filtering and sorting
- **External edits and configuration** (in progress): the TUI picks up
  changes made to the files while it runs, and a config file sets the tasks
  directory, the default sort, the theme and how often the TUI checks the
  files
- **Next**: custom keybindings, subtasks and recurring tasks

The core, the command-line interface and the TUI together make the first
usable release. [`CHANGELOG.md`](CHANGELOG.md) lists what has changed so far.

## Installation

There's no release yet; the code lives on the `dev` branch. You need
[uv](https://docs.astral.sh/uv/), which also fetches Python 3.12 or newer if
you don't have it.

To install the `tskmngr` command:

```bash
uv tool install git+https://github.com/Kevin-Brockers/tskmngr@dev
tskmngr           # opens the TUI; quit with Ctrl+Q
```

Or run it from a clone of the repository:

```bash
git clone --branch dev https://github.com/Kevin-Brockers/tskmngr
cd tskmngr
uv sync
uv run tskmngr
```

## Command-line usage

`tskmngr` without a command opens the TUI. The commands manage tasks from the
shell; `tskmngr <command> --help` lists all options of a command.

```console
$ tskmngr add "Write report" --priority high --due 2026-11-03 --tag work
K4H1V07PDV
$ tskmngr add "Buy milk" -d 2026-11-05 -t errands
M2PT707MDG
$ tskmngr list
ID          STATUS  PRIORITY  DUE         TITLE
K4H1V07PDV  todo    high      2026-11-03  Write report #work
M2PT707MDG  todo    normal    2026-11-05  Buy milk #errands
$ tskmngr show m2p
ID:        M2PT707MDG
Title:     Buy milk
Status:    todo
Priority:  normal
Due:       2026-11-05
Tags:      errands
Created:   2026-11-02T06:45:49Z
Updated:   2026-11-02T06:45:49Z
$ tskmngr done m2p
```

| Command | What it does |
| ------- | ------------ |
| `add TITLE` | Add a task and print its ID. Options: `-p/--priority low\|normal\|high` (default `normal`), `-d/--due YYYY-MM-DD`, `-t/--tag TAG` (repeat for more tags) |
| `list [WORD ...]` | List tasks, by default the ones not done yet, soonest due first. Words are searched in titles and notes; a task needs all of them. Options: `-s/--status` (repeat for more), `-a/--all` to include done tasks, `-p/--priority` (repeat for more), `-t/--tag` (repeat to require more tags), `--sort due\|priority\|created\|updated` (default: the config file's `sort`, else `due`), `-r/--reverse` to reverse that order |
| `show ID` | Show all fields of a task, then its notes |
| `edit ID` | Change the given fields: `--title`, `-s/--status`, `-p/--priority`, `-d/--due` or `--no-due`, `-t/--tag` to add a tag, `--untag` to remove one or `--clear-tags` to remove all (each tag option can be repeated) |
| `done ID` | Mark a task as done |
| `delete ID` | Move a task's file into `.trash/` (see [Deleted tasks](#deleted-tasks)) after asking; `-y/--yes` skips the question, and is required when there's no terminal to ask on |

`ID` can be any unique prefix of a task's ID, in any case: `m2p` above is
`M2PT707MDG`. Sorting by priority puts the highest first, by created or updated
the oldest first, and tasks without a due date always come last. `list`
reports task files it can't load on stderr and lists the rest.

Commands exit with 0 on success, 2 for invalid arguments and 1 for any other
error: no task or several tasks match the ID, a task file can't be loaded,
saved or deleted, or a delete isn't confirmed.

## TUI keys

The TUI opens on a list of all tasks, done ones included, soonest due first.
The footer shows the keys of the current screen; `Ctrl+Q` quits from anywhere.
Task files that can't be loaded are named, with their error, in a warning
panel above the list.

**Task list**

| Key | Action |
| --- | ------ |
| `Enter` | Open the task under the cursor in the detail view |
| `n` | New task |
| `e` | Edit the task under the cursor |
| `s` | Move the task to the next status (todo → doing → done → todo) and save it |
| `d` | Delete the task, after asking (`y` deletes, `n` or `Escape` doesn't) |
| `o` | Open the task's file in `$VISUAL` or `$EDITOR`; the task is reloaded when the editor exits |
| `/` | Filter the list (see below) |
| `Escape` | Clear the filter |
| `S` | Sort by the next key: due date, priority, created, updated |
| `R` | Reverse the sort order |

The filter narrows the list as you type. Words are searched in titles and
notes, `#tag` needs a tag, and `status:` and `priority:` restrict to a value;
repeat them for any of several, as in `status:todo status:doing`. `Enter`
goes back to the list and keeps the filter. Filter and sort last until the app
exits; the list starts with the config file's sort.

**Detail view**

| Key | Action |
| --- | ------ |
| `e` | Edit the task |
| `o` | Open the task's file in `$VISUAL` or `$EDITOR` |
| `Escape` | Back to the list |

**Task form** (title, status, priority, due date, tags and notes)

| Key | Action |
| --- | ------ |
| `Tab`, `Shift+Tab` | Next or previous field; `Enter` also moves to the next field, except in the notes |
| `Ctrl+S` | Save; problems are shown under their field |
| `Escape` | Cancel, after asking if there are unsaved changes |

Tags are separated by spaces or commas. In the notes, `Enter` starts a new
line.

If a task's file changed or was deleted on disk since the app loaded it, a
save, status change or delete doesn't overwrite it: the error is shown and the
task is reloaded from disk.

The TUI looks for task files changed, added or removed on disk every two
seconds (see `poll_interval` in the [config file](#config-file)), for example
by another `tskmngr` command or a text editor, and
reloads the list and the task shown in the detail view. A form is never
reloaded, so nothing typed is lost: if the task being edited changed or was
deleted on disk, that's shown right away, and saving the form is refused like
any other conflict.

## Task files

Each task is one Markdown file in the tasks directory, named after the task's
ID, for example `01JB3K7Q2X.md`. The YAML frontmatter holds the fields and the
body holds free-form notes:

```markdown
---
title: Buy milk
status: todo
priority: normal
due: 2026-11-01
tags: [errands]
created: 2026-10-28T09:15:00Z
updated: 2026-10-28T09:15:00Z
---

Notes go here, in **Markdown**.
```

| Field | Value | When missing |
| ----- | ----- | ------------ |
| `title` | One line of text | Required |
| `status` | `todo`, `doing` or `done` | `todo` |
| `priority` | `low`, `normal` or `high` | `normal` |
| `due` | A date, like `2026-11-01` | No due date |
| `tags` | A list, like `[errands, home]`; tags can't contain spaces and are case-insensitive | No tags |
| `created`, `updated` | A time with a timezone, like `2026-10-28T09:15:00Z` | The file's modification time |

The files are meant to be edited by hand too:

- The file name is the ID, so there's no `id` field. New tasks get a random
  10-character ID, but any `.md` file with frontmatter and a `title` is a
  task: `shopping.md` is the task `shopping`.
- Files whose names start with a dot, files not ending in `.md` and
  subfolders are ignored.
- YAML reads some unquoted values as numbers, booleans or dates:
  `title: 1.10` is the number 1.1. Quote them to keep them as text:
  `title: "1.10"`.
- Fields tskmngr doesn't know and comments in the frontmatter are kept when a
  task is saved, and a file is only rewritten when its task changed.
- A file that isn't a valid task is reported, with the line and field at
  fault when known, and never changed or deleted.
- Saves are atomic, and a save is refused if the file changed on disk since
  it was loaded.

### Where the files live

Tasks are stored in `~/.local/share/tskmngr/tasks/`. To use another directory,
set `tasks_dir` in the [config file](#config-file), or set `TSKMNGR_DIR`,
which comes first:

```bash
export TSKMNGR_DIR=~/tasks
```

The directory is created when the first task is saved.

### Deleted tasks

Deleting a task moves its file into `.trash/` inside the tasks directory,
renamed to `<id>.<delete time>.md` in UTC, for example
`01JB3K7Q2X.2026-10-30T12-00-05Z.md`. To restore the task, move the file back
as `<id>.md`. tskmngr never empties `.trash/`.

## Config file

Settings go in `~/.config/tskmngr/config.json`, a JSON object; set
`TSKMNGR_CONFIG` to use another file. Every setting is optional, and without
the file tskmngr uses the defaults. tskmngr never creates or changes it.

```json
{
  "tasks_dir": "~/tasks",
  "sort": "priority",
  "reverse": false,
  "theme": "nord",
  "poll_interval": 2
}
```

| Setting | Value | Default |
| ------- | ----- | ------- |
| `tasks_dir` | The tasks directory; `~` is your home, and a relative path is read from the config file's folder. `TSKMNGR_DIR` comes first | `~/.local/share/tskmngr/tasks` |
| `sort` | How the TUI list and `tskmngr list` are sorted: `due`, `priority`, `created` or `updated` | `due` |
| `reverse` | `true` reverses that order | `false` |
| `theme` | A [Textual theme](https://textual.textualize.io/guide/design/) name for the TUI, like `nord`, `gruvbox` or `textual-light` | `textual-dark` |
| `poll_interval` | Seconds between the TUI's checks for task files changed on disk; `0` turns them off | `2` |

`tskmngr list --sort` replaces `sort` and `reverse`; `--reverse` reverses the
configured order. If the file isn't valid JSON, has a key tskmngr doesn't know
or a value it can't use, tskmngr says what's wrong and exits instead of
guessing. A theme name that doesn't exist only stops the TUI.

## Development

```bash
uv sync                  # install dependencies
uv run pytest            # run the tests
uv run ruff check .      # lint
uv run ruff format .     # format
uv tool install prek     # install prek (once per machine)
prek install             # install the git pre-commit hook (once per clone)
```

Changes go through pull requests against `dev`. [`AGENTS.md`](AGENTS.md)
describes how to work on the code, for people and coding agents alike:
branches, tests, the changelog and the roadmap.

## License

[MIT](LICENSE)
