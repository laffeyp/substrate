# Sprint 349 — A session's workspace can stay a plain folder

```yaml
---
id: 349
status: closed
closed_at: 2026-11-12
phase: continuing a session (substrate-ui roadmap 2026-11-12-continue-a-session r2, E7)
pass_kind: functional
depends_on: []
plan: ../substrate-ui/process/planning/2026-11-12-continue-a-session/ROADMAP-2026-11-12-continue-a-session-r2.md
---
```

## scope

`SessionRegistry.create` makes every workspace not inside a repository into one (K315, `ensure_repository`: `git init`, `git add -A`, a commit). A folder that holds repositories but is not one (the Architect, 2026-11-12: "It's not a Git repository and we're not going to treat it like one") must stay as it is. `create` takes `make_repository: bool = True`; `False` skips `ensure_repository`, and with `branch` raises ValueError, since a worktree needs a repository. The default is unchanged. One verifiable property: a folder created with `make_repository=False` has no `.git` afterwards.

## context_files

- `src/substrate/topologies/session_registry.py` (`create`)
- `src/substrate/topologies/workspace.py` (`ensure_repository`, `make_worktree`)

## signal contract

### Emits

No kind. The record of a session in a plain folder is as any session's.

### Invariants

- A create without the argument does what it did: a plain folder becomes a repository.

## artifact contract

### Files modified

- `src/substrate/topologies/session_registry.py`

### Files created

- `tests/test_plain_folder_349.py`

### Command exit codes

- `uv run pytest tests/test_plain_folder_349.py` returns 0.

## observation contract

The folder on disk after create: no `.git`, the same entries.

## done criteria

A session can work in a folder of repositories without making it one.

## notes

Consumer: substrate-ui sprint 497 (`../substrate-ui/process/sprints/sprint-497-plain-folder-workspace.md`), the server option that passes it.

## self-review checklist

- [x] Scope is concrete and bounded.
- [x] One source file.
- [x] No kind.
- [x] Consumer named, its card on disk.
- [x] Observation contract present.

## close

- `tests/test_plain_folder_349.py`: 3 passed (a folder holding a repository stays without `.git` and with its entries; the default still makes one; a branch with `make_repository=False` raises and leaves the folder). With K347's tests: 6 passed. Registry and workspace tests: 39 passed. ruff clean; `mypy --strict` clean.
- Mutant (`create` always making a repository): 2 of 3 fail.

Rubber Duck Pass: no events change. No observations.
