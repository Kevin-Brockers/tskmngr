#!/usr/bin/env bash
# PreToolUse hook: before any `git commit`, show the staged diff and make
# Claude Code ask the maintainer for approval (see AGENTS.md).
set -euo pipefail

cmd=$(jq -r '.tool_input.command // ""')

# Only act on commands that run `git commit`.
if ! grep -Eq '(^|[;&|[:space:]])git([[:space:]]+-[^[:space:]]+)*[[:space:]]+commit([[:space:]]|$)' <<<"$cmd"; then
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
