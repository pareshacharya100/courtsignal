---
description: Update dev/active task notes before a context reset or end of session
argument-hint: Optional focus
---

<!-- Adapted from diet103/claude-code-infrastructure-showcase (.claude/commands/dev-docs-update.md, commit 07f75ce).
     Copyright (c) 2025 Claude Code Infrastructure Contributors. MIT License; see .claude/UPSTREAM-LICENSE. -->

Update the notes in `dev/active/` so work can resume cleanly in a new session. Focus: $ARGUMENTS

For each active task:
- `<task>-context.md`: current state, decisions made this session and why, files changed, bugs found (with the test that covers them), blockers, exact next commands, and `Last Updated`.
- `<task>-tasks.md`: mark done items ✅ with the evidence (command + result), add newly discovered items, reorder.
- Record actual results from live runs (counts, ranks, model name, date) and anything that failed. Never record secret values.
- Note uncommitted changes (`git status --short`) and how to verify them (`python -m pytest -q`).

Prioritize facts that are hard to rediscover from the code. Move a task folder to `dev/completed/` only when the user agrees it is done.
