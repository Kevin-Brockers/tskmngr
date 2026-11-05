# AGENTS.md

This repository holds the tasks of
[tskmngr](https://github.com/Kevin-Brockers/tskmngr), a terminal task manager
that keeps each task in a Markdown file. tskmngr pulls, commits and pushes
here by itself, so what you commit and push here shows up in it. Read this
before you change anything.

## Layout

- `tasks/` holds the tasks, one file each.
- `tasks/.trash/` holds the deleted tasks.
- Files outside `tasks/`, like this one, aren't tasks.

## Rules

- Never delete a task file, in `tasks/` or in `tasks/.trash/`. To delete a
  task, move its file into `tasks/.trash/` (see "Deleted tasks").
- Never rename a task file: its name is the task's ID.
- Keep frontmatter keys you don't know, and comments, as they are.
- Leave a file that isn't a valid task as it is; tskmngr reports it.
- Commit each change on its own, with a message that names the task's ID.

## Task files

Each task is a file in `tasks/` named after the task's ID, like
`tasks/01JB3K7Q2X.md`. The YAML frontmatter holds the fields and the body
holds free-form notes, in Markdown:

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
| `repeat` | A repeat rule, like `weekly` (see "Recurring tasks") | Doesn't repeat |
| `repeat_from` | A date, set by tskmngr (see "Recurring tasks") | Counts from `due` |
| `tags` | A list, like `[errands, home]`; no spaces in a tag, case-insensitive | No tags |
| `created`, `updated` | A time with a timezone, like `2026-10-28T09:15:00Z` | The file's modification time |

- The file name without `.md` is the ID, so the frontmatter has no `id` key.
  A new task gets a random 10-character ID made of
  `0123456789ABCDEFGHJKMNPQRSTVWXYZ` that no file in `tasks/` has yet.
- Set `updated` to the current time when you change a task.
- YAML reads some unquoted values as numbers, booleans or dates: `title: 1.10`
  is the number 1.1. Quote them to keep them as text: `title: "1.10"`.
- Files whose names start with a dot, files not ending in `.md` and
  subfolders of `tasks/` aren't tasks.

## Subtasks

A task's subtasks are the checklist items in its notes: a list item (`-`,
`*`, `+`, `1.` or `1)`) starting with `[ ]`, or `[x]` or `[X]` when it's done,
then its text. Indented items count too, as one flat list; items in fenced
code blocks don't.

```markdown
- [x] Book flights
- [ ] Book hotel
```

To check or uncheck one, change only the character between its brackets.

## Recurring tasks

`repeat` is `daily`, `weekly`, `monthly`, `yearly` or `every N days`,
`weeks`, `months` or `years` (N is 1 or more), like `every 2 weeks`. When
tskmngr marks such a task done, it adds the next occurrence as a new task and
moves the rule to it. Setting `status: done` in the file doesn't do that, so
mark a repeating task done with `tskmngr done <id>` when you can. Leave
`repeat_from` to tskmngr.

## Deleted tasks

To delete a task, move its file from `tasks/` into `tasks/.trash/`, renamed to
`<id>.<delete time>.md` with the delete time in UTC, like
`tasks/.trash/01JB3K7Q2X.2026-10-30T12-00-05Z.md`. Moving it back as
`tasks/<id>.md` restores the task. Never empty `tasks/.trash/`.
