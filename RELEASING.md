# Releasing

How a version of `tskmngr` is released, e.g. `0.1.0`. `main` holds the
released code and `dev` the work towards the next release; both change only
through pull requests (see `AGENTS.md`). Only the maintainer opens the
`dev` → `main` pull request and pushes release tags.

1. **Prepare the release in a pull request into `dev`.** On a branch like
   `chore/release_0_1_0` from the latest `dev`:
   - set the version in `pyproject.toml` and `uv.lock` (`0.1.0`);
   - in `CHANGELOG.md`, rename `## [Unreleased]` to the version and the
     planned release date, e.g. `## [0.1.0] - 2026-11-25`, and start a new
     empty `## [Unreleased]` above it.

   The rename and the version get no changelog entry of their own. Run lint,
   format and tests, then open the pull request against `dev`.
2. **Freeze `dev`.** From the merge of that pull request until the tag is
   pushed, no other pull request merges into `dev`. If the planned date
   slips, a pull request into `dev` corrects the date in `CHANGELOG.md`
   first.
3. **Open the `dev` → `main` pull request** (the maintainer). It carries the
   release to `main` unchanged; CI runs on it.
4. **Merge it** once CI is green.
5. **Tag the merge on `main`** with `v` followed by the version:

   ```bash
   git checkout main
   git pull --ff-only origin main
   git tag v0.1.0
   ```
6. **Push the tag:** `git push origin v0.1.0`. This starts `release.yml`. It
   stops, creating nothing, unless the tagged commit is on `main`, the tag
   matches the version in `pyproject.toml`, `CHANGELOG.md` has a section with
   entries for that version, ruff and pytest pass, and the wheel, the sdist
   and a `git archive` of the tag leave out the working files. Then it
   creates the GitHub Release with the wheel and sdist attached and the
   changelog section as its notes.
7. **Set the next development version in a pull request into `dev`**, e.g.
   `0.2.0.dev0` in `pyproject.toml` and `uv.lock`, also without a changelog
   entry. Its merge ends the freeze.
