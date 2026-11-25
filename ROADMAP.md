# Roadmap

The development plan for `tskmngr`, broken down into small, traceable steps in
the order they should be built. It's filled from planning sessions with the
maintainer and kept up to date as work lands.

- **What's planned** and in which order: milestones, top to bottom.
- **What's done**: the finished steps, each linked to the PR that finished
  it, are in [`docs/finished_roadmap.md`](docs/finished_roadmap.md).
- **What's next**: the first unchecked step whose dependencies are done. A
  dependency that isn't listed here is done: its step is in
  `docs/finished_roadmap.md`.

## How to read and update this file

### Structure

- A **milestone** (`M1`, `M2`, …) is a meaningful, usable stage of the app,
  with a one-line goal.
- A **step** (`M1.1`, `M1.2`, …) is one unit of work, sized to fit roughly one
  pull request (see the PR policy in `AGENTS.md`).
- Step IDs are permanent. Never renumber or reuse them; if a step is dropped,
  mark it as dropped instead of deleting it.
- This file holds the open steps. A finished or dropped step moves to
  [`docs/finished_roadmap.md`](docs/finished_roadmap.md), with its line,
  sub-steps and notes, under its milestone's heading and goal; a milestone
  with open and finished steps has its heading and goal in both files, and
  one with only finished steps is only there. Both files list the milestones
  in the same order.

### Step format

```markdown
- [ ] **M1.2** Short description · `feature/<name>` · depends on M1.1
```

| Status | Meaning |
| ------ | ------- |
| `[ ]`  | To do |
| `[x]`  | Done, with a link to the PR that finished it |
| `[-]`  | Dropped, with a short reason |

A finished step keeps its line, gets the PR link appended, in the same
`[reference](link)` form as `CHANGELOG.md`, and moves to
`docs/finished_roadmap.md`:

```markdown
- [x] **M1.2** Short description · `feature/<name>` · [#7](https://github.com/Kevin-Brockers/tskmngr/pull/7)
```

### Rules

- Work top to bottom: take the first open step whose dependencies are done.
  Don't skip ahead without the maintainer's agreement.
- Update the step's status in the PR that implements it: mark it `[x]` with
  that PR's link (it becomes true when the PR is merged) and move it to
  `docs/finished_roadmap.md`. Before the PR exists, the link is `#TBD`.
- New milestones and steps come from planning sessions with the maintainer.
  Agents may suggest additions, reorderings or splits, but don't make them
  without approval.
- If a step turns out bigger than one PR, split it into sub-steps
  (`M1.2a`, `M1.2b`, …) after agreeing with the maintainer.

## Milestones
