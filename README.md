# tskmngr

[![CI Linux (main)](https://img.shields.io/github/actions/workflow/status/Kevin-Brockers/tskmngr/ci-linux.yml?branch=main&label=Linux%20%28main%29)](https://github.com/Kevin-Brockers/tskmngr/actions/workflows/ci-linux.yml?query=branch%3Amain)
[![CI macOS (main)](https://img.shields.io/github/actions/workflow/status/Kevin-Brockers/tskmngr/ci-macos.yml?branch=main&label=macOS%20%28main%29)](https://github.com/Kevin-Brockers/tskmngr/actions/workflows/ci-macos.yml?query=branch%3Amain)
[![CI Linux (dev)](https://img.shields.io/github/actions/workflow/status/Kevin-Brockers/tskmngr/ci-linux.yml?branch=dev&label=Linux%20%28dev%29)](https://github.com/Kevin-Brockers/tskmngr/actions/workflows/ci-linux.yml?query=branch%3Adev)
[![CI macOS (dev)](https://img.shields.io/github/actions/workflow/status/Kevin-Brockers/tskmngr/ci-macos.yml?branch=dev&label=macOS%20%28dev%29)](https://github.com/Kevin-Brockers/tskmngr/actions/workflows/ci-macos.yml?query=branch%3Adev)
![Python 3.12 | 3.13 | 3.14](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue)

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
  editor, editing in vim or nano, filtering and sorting
- **External edits and configuration** (done): the TUI picks up changes
  made to the files while it runs, and a config file sets the tasks
  directory, the default sort, the theme, how often the TUI checks the files
  and the TUI's keys
- **Next**: subtasks and recurring tasks

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
| `add TITLE` | Add a task and print its ID. Options: `-p/--priority low\|normal\|high` (default `normal`), `-d/--due YYYY-MM-DD`, `--repeat RULE` to make it [recurring](#recurring-tasks), `-t/--tag TAG` (repeat for more tags) |
| `list [WORD ...]` | List tasks, by default the ones not done yet, soonest due first. Words are searched in titles and notes; a task needs all of them. Options: `-s/--status` (repeat for more), `-a/--all` to include done tasks, `-p/--priority` (repeat for more), `-t/--tag` (repeat to require more tags); each also takes the start of a value, like `-s do` for doing and done, `-p hi` for high or `-t err` for `#errands`, and words and tags may have [typos](#tui-keys), `--sort due\|priority\|created\|updated` (default: the config file's `sort`, else `due`), `-r/--reverse` to reverse that order |
| `show ID` | Show all fields of a task, including its subtasks done and total, then its notes |
| `edit ID` | Change the given fields: `--title`, `-s/--status`, `-p/--priority`, `-d/--due` or `--no-due`, `--repeat RULE` or `--no-repeat`, `-t/--tag` to add a tag, `--untag` to remove one or `--clear-tags` to remove all (each tag option can be repeated) |
| `done ID` | Mark a task as done. If it [repeats](#recurring-tasks), its next occurrence is added and its ID and due date printed |
| `delete ID` | Move a task's file into `.trash/` (see [Deleted tasks](#deleted-tasks)) after asking; `-y/--yes` skips the question, and is required when there's no terminal to ask on |
| `sync` | Sync the tasks with the git repository `tasks_repo` names: commit any changes, pull, then push (see [Synced tasks](#synced-tasks)); an error if `tasks_repo` isn't set |
| `remote init URL` | Set up an existing, empty remote repository to keep the tasks in, and set `tasks_repo` to it (see [Synced tasks](#synced-tasks)) |
| `config` | Print the [config file](#config-file)'s path and every setting in use; a setting the file leaves out is marked `(default)`, or `(TSKMNGR_DIR)` for a tasks directory that comes from it; while `tasks_repo` is set, the tasks directory is marked `(tasks_repo)` and `tasks_repo` says whether it's a remote URL, and where it's cloned, or a local folder |
| `config get KEY` | Print the value in use of one setting: `tasks_dir` as the full path of the tasks directory, `tasks_repo` as its URL or full path (an empty line if it isn't set), `columns`, `trash_columns` and `keybindings` as JSON, the rest as plain text |
| `config edit` | Open the config file in the [editor](#editor), even if it can't be used, then check it like the TUI does and name the key of any problem |

`ID` can be any unique prefix of a task's ID, in any case: `m2p` above is
`M2PT707MDG`. Sorting by priority puts the highest first, by created or updated
the oldest first, and tasks without a due date always come last. `list`
reports task files it can't load on stderr and lists the rest.

Commands exit with 0 on success, 2 for invalid arguments and 1 for any other
error: no task or several tasks match the ID, a task file can't be loaded,
saved or deleted, a delete isn't confirmed, `config edit` leaves a config
file that can't be used, `tasks_repo` can't be used, `remote init` can't set
up the repository, or `sync` fails. A
failed sync in any other command is only a warning.

## TUI keys

The TUI opens on a list of all tasks, done ones included, soonest due first.
The footer shows the keys of the current screen; `Ctrl+Q` quits from anywhere.
The keys below are the defaults; `keybindings` in the
[config file](#config-file) changes them.
Task files that can't be loaded are named, with their error, in a warning
panel above the list.

**Task list**

| Key | Action |
| --- | ------ |
| `Enter` | Open the task under the cursor in the detail view |
| `n` | New task |
| `e` | Edit the task under the cursor |
| `s` | Move the task to the next status (todo → doing → done → todo) and save it; a [repeating](#recurring-tasks) task that becomes done gets its next occurrence |
| `d` | Delete the task, after asking (`y` deletes, `n` or `Escape` doesn't) |
| `o` | Open the task's file in the [editor](#editor), vim or nano; the task is reloaded when the editor exits |
| `/` | Filter the list (see below) |
| `Escape` | Clear the filter |
| `S` | Sort by the next key: due date, priority, created, updated |
| `R` | Reverse the sort order |
| `t` | Hide or show the deleted tasks below the list |
| `y` | Sync with the git repository, like `tskmngr sync`; only there while `tasks_repo` is set (see [Synced tasks](#synced-tasks)) |

The filter narrows the list as you type. Words are searched in titles and
notes, `#tag` needs a tag, and `status:` and `priority:` restrict to a value;
repeat them for any of several, as in `status:todo status:doing`. All three
take the start of one too: `#err` finds `#errands`, `status:do` finds doing
and done, and `priority:hi` finds high.

Words and tags may have typos: `mlik` finds "Buy milk" and `#erands` finds
`#errands`. A typo is a wrong, missing or extra letter, or two neighbouring
letters swapped. A word of 4 to 7 letters may have one, a longer word two, and
a word of 3 letters or fewer must be exact. A typo matches a whole word, so
`mlik` doesn't find "milkshake", and like any typo tolerance it also finds
real words one letter apart (`milk` finds "mile"). `tskmngr list` matches its
words and `-t` the same way. `Enter`
goes back to the list and keeps the filter. Filter and sort last until the app
exits; the list starts with the config file's sort.

The list has the columns ID, Status, Priority, Due, Title and Tags; sorting by
created or updated adds that column at the far right while it lasts. `columns` in
the [config file](#config-file) changes which columns are shown and in which
order. Tasks with [subtasks](#subtasks) show how many are done after the
title, like `Plan trip [1/3]`, and [repeating](#recurring-tasks) tasks are
marked with `↻`, like `Pay rent ↻`. The Tags column lists a task's tags
separated by commas, like `errands, home`; without it, they follow the title
as `#tag`.

Below the list, the bottom quarter of the screen shows the
[deleted tasks](#deleted-tasks), newest delete first, with their title, tags,
delete time and ID. Files in `.trash/` that can't be loaded are named above them.
The view only lists them: it never takes the cursor, so the keys above always
act on the task list, and it scrolls with the mouse. `t` hides and shows it
until the app exits; `show_trash` in the [config file](#config-file) sets
whether it starts shown, and `trash_columns` its columns. It's updated when
you delete a task and when files in `.trash/` change.

**Detail view**

| Key | Action |
| --- | ------ |
| `Space` | Check or uncheck the subtask under the cursor and save the task (`Enter` or a click works too) |
| `e` | Edit the task |
| `o` | Open the task's file in the [editor](#editor) |
| `Escape` | Back to the list |

The detail view lists the task's subtasks above its notes, with the cursor on
them, so the arrow keys move between them; `Tab` moves to the notes.

**Task form** (title, status, priority, due date, repeat rule, tags and notes)

| Key | Action |
| --- | ------ |
| `Tab`, `Shift+Tab` | Next or previous field; `Enter` also moves to the next field, except in the notes |
| `Ctrl+S` | Save; problems are shown under their field |
| `Escape` | Cancel, after asking if there are unsaved changes |

Tags are separated by spaces or commas. While you type a tag, the rest of an
existing tag that starts with it is shown greyed out (the first one
alphabetically, leaving out tags already in the field), and `→` accepts it. In
the notes, `Enter` starts a new line.

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
| `repeat` | A [repeat rule](#recurring-tasks), like `weekly` or `every 2 weeks` | Doesn't repeat |
| `repeat_from` | A date a monthly or yearly rule counts from, set by tskmngr (see [recurring tasks](#recurring-tasks)) | Counts from `due` |
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

### Subtasks

A task's subtasks are the checklist items in its notes, so you add, rename,
reorder and remove them by editing the notes, in the form or in your editor:

```markdown
Some notes.

- [x] Book flights
- [ ] Book hotel
  - [ ] Pack
```

A checklist item is a list item (`-`, `*`, `+`, `1.` or `1)`) starting with
`[ ]`, or `[x]` or `[X]` when it's done, followed by its text. Indented items
count too, and items in fenced code blocks don't.

Checking or unchecking a subtask in the TUI's detail view also updates the
task's status: checking the last open subtask marks the task done, and
unchecking one of a done task moves it back to doing. Editing the notes never
changes the status.

### Recurring tasks

A task with a `repeat` rule comes back when it's done. The rule is `daily`,
`weekly`, `monthly`, `yearly`, or `every N days`, `weeks`, `months` or `years`,
like `every 2 weeks`. Set it in the TUI's form, with `tskmngr add --repeat` or
`tskmngr edit --repeat`, or in the file:

```markdown
---
title: Pay rent
due: 2026-01-31
repeat: monthly
---
```

Marking it done adds the next occurrence as a new task, whether with
`tskmngr done` or `tskmngr edit --status done`, or in the TUI with `s`, by
saving the form with status done or by checking its last open subtask: same title, priority, tags, notes and rule,
with every subtask unchecked, status `todo` and the next due date. The done
task stays as it is, without the rule, so reopening it doesn't create another
one.

The next due date is one interval after the old one, skipping any that are
already past, so it's always after today. Without a due date, it's one
interval after the day the task is done. Monthly and yearly rules keep the
day of the month: Jan 31 is followed by Feb 28, then Mar 31. To remember the
31st, the Feb 28 task gets `repeat_from: 2026-01-31`, which is left out again
once the day fits.

### Where the files live

Tasks are stored in `~/.local/share/tskmngr/tasks/`. To use another directory,
set `tasks_dir` in the [config file](#config-file), or set `TSKMNGR_DIR`:

```bash
export TSKMNGR_DIR=~/tasks
```

tskmngr picks the first of these that is set:

1. `tasks_repo` in the config file (see [Synced tasks](#synced-tasks))
2. `tasks_dir` in the config file
3. `TSKMNGR_DIR`
4. `~/.local/share/tskmngr/tasks/`

The config file tskmngr writes on first run leaves `tasks_dir` out, so
`TSKMNGR_DIR` works until you add it.

The directory is created when the first task is saved.

### Synced tasks

To keep your tasks in a git repository, usually a private one, and sync them
between computers, set `tasks_repo` in the [config file](#config-file).
tskmngr runs `git`, so git needs to be installed.

The quickest way to start is a new, empty repository, without a README or a
license: create it on GitHub (or another host), then run

```bash
tskmngr remote init git@github.com:me/tasks.git
```

It clones the repository into `~/.tskmngr/remote_task_dir`, adds an
`AGENTS.md` that tells AI coding agents how the task files work and that they
must not delete any, and `tasks/.trash/.gitkeep`, commits them as
`tskmngr: remote init` and pushes that, then sets `tasks_repo` to the URL in
the config file. If the folder already exists, the repository isn't empty or
`tasks_repo` is already another repository, it stops without changing
anything. tskmngr writes the `AGENTS.md` only then, so it's yours to change
afterwards.

`tasks_repo` is one of:

- **A remote URL**, like `https://github.com/me/tasks.git` or
  `git@github.com:me/tasks.git`. tskmngr clones it into
  `~/.tskmngr/remote_task_dir` the first time it needs the tasks. If that
  folder already exists but isn't a clone of this URL, tskmngr stops with an
  error and leaves the folder alone; move it away to clone there.
- **A local folder** that's already a git repository: `~` is your home, and a
  relative path is read from the config file's folder. It's synced with its
  upstream branch (the one `git push` would use). Without one, changes are
  only committed. tskmngr never runs `git init`, so a folder that isn't a
  repository is an error.

Either way, the tasks directory is the repository's `tasks/` folder, with the
deleted tasks in `tasks/.trash/`. Files at the repository's root, like a
README or an `AGENTS.md`, are synced but aren't tasks:

```
repo/
  AGENTS.md
  tasks/
    01JB3K7Q2X.md
    .trash/
```

A repository without `tasks/` stops every command but `config` with an error,
and tskmngr doesn't create or move anything: set up a new repository with
`tskmngr remote init`, or create the folder yourself, or move the task files
and `.trash/` of a repository whose tasks are at its root into it, then
commit. Git doesn't keep empty folders, so in a new repository put a file in
it, like `tasks/.gitkeep`, for other clones to have it too.

While `tasks_repo` is set, `tasks_dir` and `TSKMNGR_DIR` aren't used. Tasks
already in another tasks directory aren't moved: copy their files into the
repository's `tasks/` folder yourself, and the next command that changes a
task commits them.

These commands sync:

| Command | Sync |
| ------- | ---- |
| `add`, `edit`, `done`, `delete` | Pull, then change the task files, commit and push |
| `list` | Pull, then list |
| `sync` | Commit any changes, pull, then push the commits not pushed yet |
| `remote init` | Clone, then commit and push the setup |
| `show`, `config` | None |

The TUI syncs too, in the background, so it never waits for the network:

- When it starts, it syncs like `tskmngr sync`: commit any changes, pull, then
  push. Tasks the pull brings in show up when it's done.
- Each change you make in it (a new task, an edit in the form or in your
  editor, a status, a subtask, a delete) is committed and pushed right away.
  It doesn't pull before a change, so press `y` to bring in changes made
  elsewhere while it runs.
- `y` on the task list syncs by hand, like `tskmngr sync`, and says when it's
  done. Without `tasks_repo`, the key isn't there.
- A sync that fails, for example offline, shows a warning, and a conflict an
  error naming the task; it never interrupts what you're doing. If you quit
  while a sync is still running, it may not finish; whatever wasn't
  committed or pushed goes out with the next sync.

- Each change is one commit, named after the command, the task's ID and its
  title, like `tskmngr: add 01JB3K7Q2X Buy milk`; marking a recurring task
  done commits both files, and a delete commits the move into `.trash/`.
- Changes no command committed, like a file you edited by hand, are committed
  as `tskmngr: sync` before the pull.
- A pull rebases your commits onto the new ones from the remote. If the same
  task was changed on both sides, the pull is undone and tskmngr names the
  task: nothing is overwritten, and you resolve it with git in the
  repository.
- If a pull or push fails, for example offline, tskmngr warns on stderr and
  the command still works on the files on disk. The commits that weren't
  pushed go out with the next push. Each git command that talks to the
  remote is stopped after 60 seconds, and git never asks for a password.

For an HTTPS remote, put a fine-grained access token (with read and write
access to the repository's contents) in `TSKMNGR_GIT_TOKEN`:

```bash
export TSKMNGR_GIT_TOKEN=github_pat_...
```

tskmngr hands it to git on each command and never writes it to the
repository's `.git/config`, the remote URL or any output. Without it, git uses
its own credentials, like your SSH key or a credential manager.

### Deleted tasks

Deleting a task moves its file into `.trash/` inside the tasks directory,
renamed to `<id>.<delete time>.md` in UTC, for example
`01JB3K7Q2X.2026-10-30T12-00-05Z.md`. To restore the task, move the file back
as `<id>.md`. tskmngr never empties `.trash/`. The TUI lists the deleted tasks
below the task list (see [TUI keys](#tui-keys)).

## Config file

Settings go in `~/.tskmngr/config.json`, a JSON object. If the file doesn't
exist, tskmngr creates it the first time it runs (any command, or the TUI),
with every setting except `tasks_dir` and `tasks_repo` at its default:

```json
{
  "sort": "due",
  "reverse": false,
  "theme": "textual-dark",
  "editor": "vim",
  "poll_interval": 2,
  "columns": [
    "id",
    "status",
    "priority",
    "due",
    "title",
    "tags"
  ],
  "trash_columns": [
    "title",
    "tags",
    "deleted",
    "id"
  ],
  "show_trash": true,
  "keybindings": {}
}
```

After that tskmngr only reads the file, except that
[`tskmngr remote init`](#synced-tasks) sets `tasks_repo` in it (keeping the
other settings, but rewriting the file's spacing); edit it to change your
settings. Every setting is optional, so you can also remove the
ones you don't need. If the file can't be created, tskmngr says why and exits.

`tskmngr config` shows where the file is and the settings in use, and
`tskmngr config get KEY` prints one of them, for example
`cd "$(tskmngr config get tasks_dir)"`:

```console
$ tskmngr config
Config file: /home/me/.tskmngr/config.json

tasks_dir      /home/me/.local/share/tskmngr/tasks (default)
tasks_repo     not set (default)
sort           due
reverse        false
theme          textual-dark
editor         vim
poll_interval  2
columns        ["id", "status", "priority", "due", "title", "tags"]
trash_columns  ["title", "tags", "deleted", "id"]
show_trash     true
keybindings    {}
```

`tskmngr config edit` opens the file in the [editor](#editor). When the
editor exits, it checks the file the way the TUI does, theme and keybindings
included, and names the key of the first problem it finds; the file is kept
as you saved it, so run `config edit` again to fix it. It's the one command
that still runs when the file can't be used. If the editor exits with an
error, it says so and exits with 1, after checking the file.

A file with every setting looks like this:

```json
{
  "tasks_dir": "~/tasks",
  "sort": "priority",
  "reverse": false,
  "theme": "nord",
  "poll_interval": 2,
  "columns": ["id", "due", "title"],
  "trash_columns": ["title", "deleted"],
  "show_trash": false,
  "keybindings": {"task_list.new": "a", "task_form.save": "ctrl+s,f2"}
}
```

Earlier versions read `~/.config/tskmngr/config.json`, or the file
`TSKMNGR_CONFIG` pointed to. Neither is read any more. While the old file
exists, tskmngr warns about it on every run: move your settings to
`~/.tskmngr/config.json`, then delete the old file to stop the warning.

| Setting | Value | Default |
| ------- | ----- | ------- |
| `tasks_dir` | The tasks directory; `~` is your home, and a relative path is read from the config file's folder (`~/.tskmngr`). Comes before `TSKMNGR_DIR` | `TSKMNGR_DIR`, else `~/.local/share/tskmngr/tasks` |
| `tasks_repo` | A git repository to keep the tasks in, in its `tasks/` folder: a remote URL, cloned into `~/.tskmngr/remote_task_dir`, or a local folder that's a repository; while it's set, `tasks_dir` and `TSKMNGR_DIR` aren't used (see [Synced tasks](#synced-tasks)) | not set: no sync |
| `sort` | How the TUI list and `tskmngr list` are sorted: `due`, `priority`, `created` or `updated` | `due` |
| `reverse` | `true` reverses that order | `false` |
| `theme` | A [Textual theme](https://textual.textualize.io/guide/design/) name for the TUI, like `nord`, `gruvbox` or `textual-light` | `textual-dark` |
| `editor` | The [editor](#editor) `o` in the TUI and `tskmngr config edit` open files in: `vim` or `nano` | `vim` |
| `poll_interval` | Seconds between the TUI's checks for task files changed on disk; `0` turns them off | `2` |
| `columns` | The TUI task list's columns, in the order shown, from `id`, `status`, `priority`, `due`, `created`, `updated`, `title` and `tags`; the ones left out are hidden (see below) | `["id", "status", "priority", "due", "title", "tags"]` |
| `trash_columns` | The TUI's deleted tasks view's columns, in the order shown: the `columns` names and `deleted`, the delete time; the ones left out are hidden | `["title", "tags", "deleted", "id"]` |
| `show_trash` | `false` starts the TUI with the deleted tasks view hidden; `t` shows it | `true` |
| `keybindings` | New keys for the TUI, an object of binding ids and their keys (see below) | the keys under [TUI keys](#tui-keys) |

`tskmngr list --sort` replaces `sort` and `reverse`; `--reverse` reverses the
configured order. If the file isn't valid JSON, has a key tskmngr doesn't know
or a value it can't use, tskmngr says what's wrong and exits instead of
guessing. A theme name or binding id that doesn't exist only stops the TUI.

`columns` needs at least one column, and each only once. Sorting by created
or updated shows that column even when `columns` leaves it out, last, at the
far right, as long as that sort lasts. A hidden due
date or priority column stays hidden when the list is sorted by it. The title
column also holds the repeat marker and the subtasks done, and the tags while
`tags` isn't listed, so a config file written before the tags column existed
still shows them; add `tags` to show them in their own column.
`trash_columns` follows the same rules, with `deleted` as one more name; the
deleted tasks are always newest delete first.

### Editor

Tasks are edited inside the TUI: the form (`n`, `e`) holds every field and
the notes, and `s`, `d` and `Space` change a task right away. Only `o` in the
TUI and `tskmngr config edit` open a file in an editor, in the same terminal,
and the `editor` setting picks which:

- **`vim`**, the default. Press `i` to type, `Esc` to stop typing, then `:wq`
  and `Enter` to save and quit, or `:q!` and `Enter` to quit without saving.
- **`nano`**, which lists its keys at the bottom: type right away, `Ctrl+O`
  saves and `Ctrl+X` quits.

```json
{
  "editor": "nano"
}
```

While the editor runs, the TUI waits; when you quit it, the task is loaded
again from the file, and a file you left broken is reported, never
overwritten. If the editor isn't installed, tskmngr says so and names the
setting, so install it (for example with `brew install nano` on macOS or
`sudo apt install nano` on Debian and Ubuntu) or pick the other one.
`$VISUAL` and `$EDITOR` aren't used. `tskmngr config edit` opens a file whose
`editor` it can't read in vim, so a broken config file can still be fixed.

### Keybindings

Each entry in `keybindings` replaces the keys of one TUI binding. The keys
are Textual key names, like `a`, `A`, `f2`, `ctrl+s`, `escape` or `slash`
(a single character such as `/` works too); separate several with commas, as in
`"ctrl+s,f2"`. The footer shows the new keys.

| Binding id | Default | Action |
| ---------- | ------- | ------ |
| `task_list.open` | `Enter` | Open the task in the detail view |
| `task_list.new` | `n` | New task |
| `task_list.edit` | `e` | Edit the task |
| `task_list.cycle_status` | `s` | Move the task to the next status |
| `task_list.delete` | `d` | Delete the task |
| `task_list.external_editor` | `o` | Open the task's file in the editor |
| `task_list.sort` | `S` | Sort by the next key |
| `task_list.reverse_sort` | `R` | Reverse the sort order |
| `task_list.filter` | `/` | Filter the list |
| `task_list.clear_filter` | `Escape` | Clear the filter |
| `task_list.toggle_trash` | `t` | Hide or show the deleted tasks |
| `task_detail.close` | `Escape` | Back to the list |
| `task_detail.edit` | `e` | Edit the task |
| `task_detail.external_editor` | `o` | Open the task's file in the editor |
| `task_detail.toggle_subtask` | `Space` | Check or uncheck the subtask |
| `task_form.save` | `Ctrl+S` | Save the task |
| `task_form.cancel` | `Escape` | Cancel |
| `confirm_delete.yes` | `y` | Delete, in the delete question |
| `confirm_delete.no` | `n`, `Escape` | Don't delete |
| `confirm_discard.yes` | `y` | Discard the changes, when cancelling a changed form |
| `confirm_discard.no` | `n`, `Escape` | Keep editing |

Two bindings on the same screen can't share a key, and none can take
`Ctrl+Q` (quit) or `Ctrl+C`; swapping two keys is fine. Textual's own keys,
like `Ctrl+Q`, and `Tab` and the arrow keys in forms and lists, can't be
changed, and only those two are checked: a binding moved to `Tab` takes it
over on its screen. tskmngr doesn't check the key names either: a misspelled
key, like `ctlr+s`, never fires.

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

CI runs on GitHub Actions for every pull request into `dev` and `main` (into
`main`, only the release pull request from `dev`) and every push to them, and
can be started by hand from the Actions tab: `ci-linux.yml` lints and runs
the tests on Linux with Python 3.12, 3.13, 3.14 and the newest release, and
`ci-macos.yml` runs the tests on macOS with Python 3.12, 3.13 and 3.14. The
badges at the top show their last result on `main`, the released code, and on
`dev`, the work towards the next release. Run the checks above
before every commit too, so a pull request doesn't wait for CI to find a
problem.

Releases are made by `release.yml` when the maintainer pushes a tag like
`v0.1.0` on `main`. It checks that the tagged commit is on `main`, that the
tag matches the version in `pyproject.toml` and that `CHANGELOG.md` has a
section with entries for that version, and stops if not. It then lints and
tests that commit, builds the wheel and sdist with `uv build` and creates a
GitHub Release with them attached and the changelog section as its notes.

## License

[MIT](LICENSE)
