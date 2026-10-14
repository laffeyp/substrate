# Sprint 315 — Every workspace a repository; worktrees from the kernel

```yaml
---
id: 315
status: closed
closed_at: 2026-10-13
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

## result

- **Built.** `topologies/workspace.py`: `ensure_repository` (a folder not inside a repository gets `git init` and one commit of what it holds, under the user's git identity or `Substrate <substrate@localhost>` when none is set; a folder inside a repository is left alone, so no repository nests in another; without git installed it does nothing and the session opens on a plain folder), `make_worktree` and `worktree_diff` (moved from `substrate-ui/server.py`). `SessionRegistry.create` makes every workspace a repository and, given `branch`, opens the session in its own worktree under `<base>/wt/<session_id>` with shape `worktree`. Sessions that do not ask for a branch keep working in their workspace as before. `substrate.app` exports the module; the app's server calls it, keeping its rule that only session worktrees are served.
- **Found.** The app's `/api/agent` concurrency test failed: two sessions opening on one folder at once both ran `git init`, and the second commit hit the first's `index.lock`. A lock per workspace path fixes it; the check is repeated under the lock.
- **Tests.** `tests/test_workspace_315.py`, 6, red first (the module did not exist; the race test failed 3 of 3 before the lock): a plain folder gets one commit of its files; an empty folder an empty first commit; a repository and a folder inside one are left alone; a worktree on its own branch, reused, with a read-only diff; the registry's repository and branch; eight concurrent opens make one repository. Kernel suite 1,686 passed (the known model-path test deselected); the app's Python suite passed but for the race, which now passes 3 of 3.
