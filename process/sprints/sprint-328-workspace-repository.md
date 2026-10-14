# Sprint 328 — Every workspace a repository; worktrees

```yaml
---
id: 328
status: closed
closed_at: 2026-10-14
phase: 4
pass_kind: functional
depends_on: []
roadmap: process/planning/ROADMAP-2026-10-14-core-topologies-r3.md
---
```

## scope

r9 § 5: a session opened on a folder that is not a git repository gets `git init` and a first commit; a run gets a worktree of the caller's repository on its own branch, or detached at a target. Worktree creation moves from the server into the kernel.

## observation contract

A plain folder becomes a repository with one commit; a folder inside a repository is left alone; a run's worktree is on its branch; the app's worktree sessions still work.

## result

- **Re-applied** kernel sprint 315's code unchanged (it carried none of what round 9 removes): `topologies/workspace.py` (`ensure_repository`, `make_worktree`, `worktree_diff`), `SessionRegistry.create(branch=...)`, `substrate.app.workspace`; and in the app server, worktree creation and diffing from the kernel.
- **Tests.** `tests/test_workspace_315.py`, 6 pass; the app's `test_server.py` and `test_server_security_boundary_110.py`, 28 pass.
