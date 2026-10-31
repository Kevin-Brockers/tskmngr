#!/usr/bin/env bash
# PreToolUse hook: before any `git commit`, show the staged diff and make
# Claude Code ask the maintainer for approval (see AGENTS.md).
set -euo pipefail

input=$(cat)

# A command without "commit" can't commit. Checked before anything that can
# fail, so other commands still run if, say, jq is missing.
[[ $input == *commit* ]] || exit 0

# From here on a failure blocks the command (exit 2) instead of letting the
# commit through unreviewed.
block() {
  echo "review-diff hook: $1, so the commit was blocked" >&2
  exit 2
}
trap 'block "unexpected error on line $LINENO"' ERR
command -v jq >/dev/null || block "jq is not installed"

cmd=$(jq -r '.tool_input.command // ""' <<<"$input")

# Whether `cmd` runs the git subcommand(s) matching the regex `$1`: a `git`
# word, maybe with a path, at the start, after an operator, `(` or a backtick,
# then global options (some take a value, maybe quoted), then the subcommand.
git_runs() {
  local start='(^|[;&|(`[:space:]])([^[:space:];&|()`]*/)?git'
  local value="(\"[^\"]*\"|'[^']*'|[^[:space:]]+)"
  local option="(-C|-c|--git-dir|--work-tree|--namespace|--config-env)[[:space:]]+$value|-[^[:space:]]+"
  grep -Eq "$start([[:space:]]+($option))*[[:space:]]+($1)([[:space:];&|)\`]|\$)" <<<"$cmd"
}

git_runs commit || exit 0

# The hook runs before the command, so it can't show what a `git add` in the
# same command will stage. Staging must be its own step.
if git_runs 'add|stage|rm|mv|restore|reset|apply'; then
  jq -n '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: "Stage the changes in a separate command first, then commit. This hook runs before the command, so it cannot show what this command would stage, and the review must show exactly what gets committed."
    }
  }'
  exit 0
fi

# `git commit -a` stages tracked changes itself, so include them in the preview.
if grep -Eq '[[:space:]]-[a-zA-Z]*a[a-zA-Z]*([[:space:]]|$)|--all' <<<"$cmd"; then
  diff=$(git diff HEAD --stat; echo; git diff HEAD)
else
  diff=$(git diff --staged --stat; echo; git diff --staged)
fi
status=$(git status --short)

max=20000
if (( ${#diff} > max )); then
  diff="${diff:0:max}
… (diff truncated; run \`git diff --staged\` for the rest)"
fi

reason="Review the changes before committing.

git status:
${status:-(clean)}

${diff:-(nothing staged)}

Approve to commit, or deny and say what to change."

jq -n --arg reason "$reason" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "ask",
    permissionDecisionReason: $reason
  }
}'
