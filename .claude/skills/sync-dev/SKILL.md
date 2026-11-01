---
name: sync-dev
description: Update the local dev branch from origin and delete local branches that are fully merged into dev, keeping only main and dev. Branches on GitHub are never touched. Use after a pull request has been merged, or when asked to pull dev, sync with dev or clean up merged branches.
---

# sync-dev

Bring `dev` up to date and remove local branches whose work is already in
it. Only `main` and `dev` are always kept. Branches on GitHub are never
deleted or changed: nothing is pushed. Nothing is force-deleted or reset
either; anything that doesn't fit the steps below is reported to the
maintainer instead of being fixed by guessing.

1. **Check the working tree.** Run `git status --porcelain`. If it lists
   anything, stop and tell the maintainer which files are uncommitted;
   switching branches could carry them along or fail. Don't stash, commit or
   discard them yourself.
2. **Fetch.** Run `git fetch --prune origin`. `--prune` only removes the
   local `origin/…` references of branches already deleted on GitHub; it
   doesn't change GitHub. On a network error, retry up to 4 times, waiting
   2, 4, 8 and 16 seconds.
3. **Update `dev`.** Run `git checkout dev`, then `git pull --ff-only origin
   dev`. If the pull isn't a fast-forward (local `dev` has commits that aren't
   on `origin/dev`), stop and report those commits
   (`git log --oneline origin/dev..dev`). Never reset `dev`.
4. **Delete merged local branches.** List them with `git branch --merged dev`
   and leave out `main`, `dev` and the current branch. Delete each with
   `git branch -d <name>` (never `-D`); `-d` refuses anything not merged, so
   no commits are lost. A branch with no commits of its own, like one created
   but not worked on yet, also counts as merged; name these in the summary.
5. **Report unmerged local branches.** List what's left with `git branch`. For
   each branch besides `main` and `dev`, say how many commits it has that
   `dev` doesn't (`git rev-list --count dev..<name>`) and whether its upstream
   is gone (`git branch -vv` shows `[origin/…: gone]`). A gone upstream with
   commits not in `dev` can mean a squash or rebase merge: don't delete it,
   ask the maintainer.
6. **Summarize** for the maintainer: the commit `dev` is now at
   (`git log --oneline -1`), the local branches deleted, and any local
   branches kept and why.

Only report what the commands actually printed. If a step fails, say which
command failed and include its output.
