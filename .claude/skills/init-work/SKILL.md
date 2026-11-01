---
name: init-work
description: Load the project's working rules and plan before starting work on tskmngr. Reads AGENTS.md and ROADMAP.md in full. Use at the start of a session or before picking up a new task or roadmap step.
---

# init-work

Get up to speed on how this project is worked on and what comes next.

1. Read `AGENTS.md` at the repository root in full, using the Read tool. It
   holds the working etiquette, tech stack, commands, task storage format and
   working conventions (branches, diff review before commits, changelog,
   dependencies).
2. Read `ROADMAP.md` at the repository root in full, using the Read tool. It
   holds the milestones and steps, which are done and which are open.
3. Give the maintainer a short summary:
   - the first open step whose dependencies are done, with its ID, description
     and branch name, as given in `ROADMAP.md`;
   - anything in the two files that looks inconsistent or unclear.

Only report what the files actually say. If a file is missing or can't be
read, say so instead of guessing its contents. Don't start implementing
anything; wait for the maintainer to say what to work on.
