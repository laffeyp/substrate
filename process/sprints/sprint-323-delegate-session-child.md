# Sprint 323 — Delegate as a session child

```yaml
---
id: 323
status: closed
closed_at: 2026-10-13
phase: 3
pass_kind: functional
depends_on: [315]
roadmap: process/planning/ROADMAP-2026-10-13-core-topologies-r2.md
---
```

## scope

Every delegate child is a registry session (r8 § 4.6): the default path stops building the bare tool-loop child and its 6-step cap; fan-out children stop defaulting to `deterministic`. A child runs on the caller's model unless the call names another, in the caller's workspace, and its answer folds back as the tool's result as today. A standing session named by the call still receives the message.

## observation contract

A delegate call with no model runs a session child on the caller's model, recorded in the registry with the caller as its parent; it takes more than six steps when its task needs them; its answer is the tool's result. Fan-out children with no driver run on the caller's model. Nothing in the kernel builds the tool-loop child any more.

## result

- **Built.** `tool_loop/delegate.py` rewritten: every child is a registry session (`_session_child`), with the caller as `composite_of`, on the model the call names or else the caller's, in the caller's workspace, with the caller's bundle, length, tone and tool allow-list (a read-only caller gives a read-only child), and no `driver_params` (a scripted caller's script would otherwise run again in its child). Its first turn runs to the session's own step limit; its reply is the tool's result (`answer`, `session_id`, `child_root`). Fan-out children default to the caller's model; the standing-session path is unchanged. Depth counts the caller's ancestors in the registry, and the tree budget counts the sessions under the topmost ancestor, since the app rebuilds every session's tools each turn and a counter in the tool would reset. Gone: the bare `tool_loop` child, its thread runner, `child_max_steps`, the child and model factories, and the per-call `baseline` (a call carrying it is refused). `SessionRegistry.descendants` lists a session's children at every depth, deepest first; the app's end and delete cascades use it. The app server builds delegate from the registry and the caller's id.
- **Tests.** `tests/test_delegate_session_child_323.py`, 9: a child is a session on the caller's model with its parent, workspace, bundle, length, tone and tools and its own `delegate` message; a child's turn makes 8 tool calls; a call names another model; a context slice reaches the child's message; fan-out children default to the caller's model; depth counts ancestors; the per-tool and tree caps refuse; interrupting the caller interrupts the child; descendants come deepest first. Moved to the new constructor: the standing-session, schema and context tests and both real-model delegate tests (run live: qwen2.5 parent, a session child, 8.5 s; a cloud-model standing reviewer, 5 s). Removed with the design they tested: `test_delegate.py`, `_backwards_compat`, `_cli_workspace_115`, `_per_call_baseline`, `_provenance`, `_per_call_model`, `_cancel_reaches_child_102`, and test 5 of `test_background_commands_103.py` (a child's tasks now belong to its session, which stays open; test 6 covers the session ending). Mutation: a `deterministic` default fails the first test.
