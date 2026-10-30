# tskmngr

A terminal task manager with an interactive TUI, written in Python. Tasks are
plain Markdown files, so they stay readable and editable outside the app.

## Status

Early development, not usable yet. [`ROADMAP.md`](ROADMAP.md) has the full
plan; in short:

- **Core** (done): task model, Markdown file format, storage, filtering,
  search and sorting
- **Command-line interface** (next): add, list, show, edit, complete and
  delete tasks from the shell
- **TUI**: the full app, with a task list, detail view, forms, a notes editor
  and editing in `$EDITOR`
- **Later**: picking up changes made to the files while the app runs, a
  config file with custom keybindings, subtasks and recurring tasks

The core, the command-line interface and the TUI together make the first
usable release. [`CHANGELOG.md`](CHANGELOG.md) lists what has changed so far.

## Running it from source

There's no release yet, and the code lives on the `dev` branch. You need
Python 3.12 or newer and [uv](https://docs.astral.sh/uv/):

```bash
git clone --branch dev https://github.com/Kevin-Brockers/tskmngr
cd tskmngr
uv sync
uv run tskmngr    # opens the TUI, still empty for now; quit with Ctrl+Q
```

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
set `TSKMNGR_DIR`:

```bash
export TSKMNGR_DIR=~/tasks
```

The directory is created when the first task is saved.

### Deleted tasks

Deleting a task moves its file into `.trash/` inside the tasks directory,
renamed to `<id>.<delete time>.md` in UTC, for example
`01JB3K7Q2X.2026-10-30T12-00-05Z.md`. To restore the task, move the file back
as `<id>.md`. tskmngr never empties `.trash/`.

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
