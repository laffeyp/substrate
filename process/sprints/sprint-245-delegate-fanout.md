# Sprint 245 — delegate fan-out

```yaml
---
id: 245
status: pending
phase: 5
pass_kind: functional
---
```

## scope

Grow the `delegate` tool to spawn N children in parallel from one
tool call. Every child is a session — no new topology. Three caps
inherited from the root down every descendant. Per
`substrate-ui-working/process/planning/delegation-research-r5.md`.

## files

- `substrate/src/substrate/topologies/tool_loop/delegate.py`

## call shape

```
delegate(
  task, [model], [child_session_name], [context], [baseline],
  [timeout_seconds],
  [children],            # list of session specs
  [max_depth],           # default 5
  [max_children],        # default 16, per parent
  [max_total_children],  # default 64, whole tree
)
```

When `children` is present, ignore the single-child fields and
spawn each entry as a session in parallel. Each entry:
`{task, [driver], [workspace], [tools], [isolate], [name]}`.

## result shape

```
{
  ok: true | false,
  answers: {<child_name>: "..."},
  child_roots: {<child_name>: "/path/to/record"},
  steps: {<child_name>: N},
  failed: {<child_name>: {error, failure_class}},
}
```

`answers` and `failed` are disjoint. `ok: false` only when every
child failed.

## invariants

- ONE `ToolCall(tool="delegate")` envelope on the parent record.
- ONE `ToolResult(tool="delegate")` envelope when all children
  Park or End.
- Every child spawns through `SessionRegistry.create` +
  `turn_sync`. No new seam.
- Three caps refuse with typed `ToolResult(ok=false)` naming
  which cap fired.
- Descendants cannot lift the caps they inherited.

## defaults bump

- `max_depth: int = 2` → **5**
- `max_children: int = 4` → **16**
- new: `max_total_children: int = 64`

## done criteria

- `delegate({children: [...]})` fires N sessions in parallel,
  folds one ToolResult when all Park or End.
- All existing single-child paths (session name / model / context
  / plain) still work; regression test suite green.
- Nested fan-out works up to the three caps.
