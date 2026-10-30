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
- #TBD - Task storage: tasks directory from `TSKMNGR_DIR` or the default, load
  all tasks with malformed files reported, atomic saves that refuse to
  overwrite a file changed on disk since it was loaded, and delete by moving the
  file to `.trash/` under a name with the delete time
- [7982e5c](https://github.com/Kevin-Brockers/tskmngr/commit/7982e5c9b62c955e9fe1f08a551be97f5dabf555) - Initial repository with `README.md` and MIT license

### Changed

- [#3](https://github.com/Kevin-Brockers/tskmngr/pull/3) - Approved dependency baseline: `ruamel.yaml` replaces `pyyaml` so
  saving a task keeps frontmatter comments and formatting, and `pytest-asyncio`
  is added for Textual's async UI tests
- [#3](https://github.com/Kevin-Brockers/tskmngr/pull/3) - Task storage format in `AGENTS.md`: the filename is the task's ID (no
  `id` key in the frontmatter), deleted tasks move to `.trash/`, and a value of
  the wrong type makes a file malformed
