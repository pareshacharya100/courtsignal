---
description: Create persistent task notes (plan, context, checklist) under dev/active/
argument-hint: Short task description, e.g. "live Voyage + Pinecone validation"
---

<!-- Adapted from diet103/claude-code-infrastructure-showcase (.claude/commands/dev-docs.md, commit 07f75ce).
     Copyright (c) 2025 Claude Code Infrastructure Contributors. MIT License; see .claude/UPSTREAM-LICENSE. -->

Create task notes for: $ARGUMENTS

1. Read `CLAUDE.md`, `docs/design.md`, and the modules/tests relevant to the task. Check `dev/active/` for an existing folder first; update it rather than duplicating.
2. Choose a short kebab-case task name and create `dev/active/<task>/` with three files, each starting with `Last Updated: YYYY-MM-DD`:
   - `<task>-plan.md`: goal, current state (with file references), the smallest sequence of steps, risks, cost/call bounds for any external service, and acceptance criteria tied to observable results.
   - `<task>-context.md`: key files, decisions and why, verified facts vs assumptions, provider docs consulted (with URLs and dates), and open questions for the user.
   - `<task>-tasks.md`: a checklist with acceptance criteria per item.
3. Keep it brief and concrete. Mark what is mocked, live-verified, or unverified. No secret values in these files.
