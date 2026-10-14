# Sprint 333 — Delegate as a session child

```yaml
---
id: 333
status: closed
closed_at: 2026-10-14
phase: 4
pass_kind: functional
depends_on: []
roadmap: process/planning/ROADMAP-2026-10-14-core-topologies-r3.md
---
```

## scope

r9 § 8.5: every delegate child is a registry session on the caller's model unless the call names another, in the caller's workspace, with its bundle, controls and tools, the caller as its parent; the bare tool-loop child and its 6-step cap go; nested children end and are deleted with their ancestors.

## observation contract

As kernel sprint 323's, which this card rebuilds.

## result

- **Re-applied** kernel sprint 323's delegate (it carried none of what round 9 removes): every child a registry session on the caller's model unless named, in the caller's workspace, with its bundle, length, tone and tools, `composite_of` the caller; the bare `tool_loop` child, its runner, `child_max_steps` and the per-call `baseline` gone; depth and tree budget from the registry; `SessionRegistry.descendants` for the app's nested end and delete cascades. The handoff line waits for K334. The app server builds delegate from the registry and the caller's id.
- **Tests.** `tests/test_delegate_session_child_333.py`, 9, and the moved delegate, schema, context, standing-session, background-task and real-model tests: 96 pass. The seven test files of the removed child are removed again. App: 27 server and composition tests pass.
