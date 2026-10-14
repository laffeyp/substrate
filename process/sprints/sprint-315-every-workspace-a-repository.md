# Sprint 315 — Every workspace a repository; worktrees from the kernel

```yaml
---
id: 315
status: open
phase: 1
pass_kind: functional
depends_on: [314]
roadmap: process/planning/ROADMAP-2026-10-13-core-topologies.md
---
```

## scope

Opening a session on a workspace that is not a git repository runs `git init` and a first commit of what it holds (r8 § 3.7; the Architect, 2026-10-13). The session registry makes a worktree and branch for a session or run that asks for one; `_session_worktree` moves from `substrate-ui/server.py` into the kernel with its tests.

## observation contract

A session opened on a plain folder finds a repository with one commit; on an existing repository nothing is committed; a run given `workspace_shape = worktree` gets its own worktree on its own branch, and its changes show in the diff read.
