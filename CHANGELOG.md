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
- [7982e5c](https://github.com/Kevin-Brockers/tskmngr/commit/7982e5c9b62c955e9fe1f08a551be97f5dabf555) - Initial repository with `README.md` and MIT license
