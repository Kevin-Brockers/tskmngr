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

### M1 and later

To be planned in the next planning session.
