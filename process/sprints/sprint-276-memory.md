# Sprint 276 — Memory

```yaml
---
id: 276
status: closed
closed_at: 2026-10-10
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-10-default-guidance.md
asked: 2026-10-10 (Architect)
---
```

## why

Claude Code's memory is invisible to the record and specific to Claude; Substrate has none.

## scope

- `~/.substrate/memory/` and `<repo>/.substrate/memory/`: a `MEMORY.md` index and a topic file per entry.
- Indexes load at session open as `PromptFragment(memory)`, capped at 200 lines or 25 KB each.
- The memory rules (four kinds, one fact per file, why and how-to-apply) go in `standard`'s methodology.
- This repo's project entries move into `<repo>/.substrate/memory/`.

## checks

- An index loads.
- A save is a `ToolCall` into a memory directory on the record.

## result

- **Built.**
  - `PromptSource.MEMORY` at precedence 8, in the session-open set and in `CACHE_LAYOUT_SOURCES`, not in `SYSTEM_SOURCES`: Claude Code sends its memory index in the user block.
  - `memory_fragments(repo_root)` writes one fragment per existing index, operator first, then repo. Each is capped at 200 lines or 25 KB, Claude Code's limits, and its provenance is `{path, lines, truncated}`.
  - `session_topology(memory=)`. The daemon passes `memory=True` for every session, with the workspace as the repo root.
- **The memory rules.** A "# Memory" section was added to `standard`'s methodology. It is Claude Code's own memory instructions with the paths and tools mapped: the two directories, `write_file` and `edit_file`, and which kinds go where (`user`, `feedback` and `reference` to the operator's directory; `project` to the repo's).
- **This repo's project memory.** The 19 project and SDD entries were copied from the operator's Claude Code memory into `substrate/.substrate/memory/`, with an index. The operator's `~/.claude` is unchanged. Not committed: the entries include a personal detail (the operator's subscription price), so whether the directory belongs in a published repo is the Architect's call.
- **Test.** `test_memory_276.py`, 6 tests: both indexes load, operator first; the cap; no index, no fragment; memory is a source only when asked; it stays in the user turn unless the layout opts in; `standard` carries the rules.
- **Checks** (targeted): 24 passed, with the vocabulary and golden-head tests; the six goldens were regenerated, and the memory section appears in the five built on `standard`.
