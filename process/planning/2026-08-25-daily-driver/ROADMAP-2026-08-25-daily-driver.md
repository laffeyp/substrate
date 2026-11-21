# Roadmap — substrate daily driver (2026-08-25)

Derives from `current-design-direction/TECH-SPEC-2026-08-25-round6.md`. Names the pieces, the order, the dependencies, and the definition of done. Sprint cards live at `substrate/process/sprints/sprint-NNN-*.md` continuing the existing series (last sprint 200a). Piece G lands in `substrate-ui/sprints/` continuing that series (last sprint 032).

## What is done

Two things must be true before any daily-driver sprint dispatches. Piece 0 delivers both.

1. `substrate/process/signals/0.6.json` — locked vocabulary with strata, categories, invariants for every new kind. Architect ratifies in `substrate/process/BLACKBOARD.md ## Decisions`.
2. `substrate/process/signals/0.6-rationale.md` — the rationale doc BOOTSTRAP.md pairs with the JSON.

Piece A dispatches only after both land and the Architect ratifies. AGENTS.md hard rule 12.

## Pieces + order

| # | Piece | Land in | Sprints | Depends on |
|---|---|---|---|---|
| 0 | Sprint-0 Vocabulary Session | `substrate/process/signals/` + `substrate-ui/signals/versions/` | 202-204 | — |
| A | Session topology | `substrate/src/substrate/topologies/session/` | 205-210 | 0 |
| C | Named standing sessions + delegate per-call args | `substrate-ui/server.py`, `delegate.py`, `~/.substrate/sessions/` | 211-213 | A |
| B | Session-scoped daemon API | `substrate-ui/server.py` | 214-217 | A |
| D | CLI + REPL + slash commands | `substrate/src/substrate/cli.py` | 218-222 | A + B (stubs enough to start) |
| E | Application manifests + registry | `substrate/src/substrate/topologies/applications/` | 223-225 | — (parallel with A after 0) |
| F | Substrate toolkit tool wrappers | `substrate/src/substrate/topologies/tool_loop/substrate_tools.py` | 226-228 | A |
| H | Bundles + Mad Lib | `substrate/src/substrate/bundles.py`, templates | 229-232 | E |
| G | Substrate-ui two-view + rail | `substrate-ui-3pane/web/*.ts` | ui-033 onward | A-F land; CLI works end-to-end |

Total: 31 sprints in `substrate/process/sprints/` (202-232), plus a substrate-ui fast-follow starting at sprint 033 for Piece G.

## Dependency graph

```
piece 0 (vocab bootstrap)
   │
   ▼
piece A (session topology) ────────────────┐
   │                                        │
   ├──▶ piece C (named sessions, delegate) │
   │       │                                │
   │       ▼                                │
   │   piece E sprint 225 (pair_coding      │
   │       composite depends on C's         │
   │       standing-session dispatch)       │
   │                                        │
   ├──▶ piece B (daemon /api/session/*)    │
   │       │                                │
   │       ▼                                │
   │   piece D (CLI + REPL + slashes)      │
   │                                        │
   └──▶ piece F (substrate_tools.py)       │
                                            │
piece E sprints 223, 224 (app registry     │
  + three-app manifests) — parallel with A │
piece E sprint 225 (pair_coding composite) ◀── depends on C sprints 211-213
   │                                        │
   ▼                                        │
piece H (bundles + Mad Lib)                │
                                            │
piece G (ui two-view) ◀── A + B + C + D + F + H
```

## Cadence

- Pieces 0, A land plan-mode-per-sprint (Architect reviews each sprint card before dispatch). Establishing contracts.
- Pieces C, B, D, E, F, H run auto-band within phase after the piece's first sprint reviews clean. Filling logic against established contracts.
- Piece G plan-mode again — behavior-touching UI, cross-repo, own harness.

Halt-and-articulate on any sprint whose scope the Agent cannot restate as one bounded paragraph.

## Definition of done for the daily driver

A user opens a terminal, types `substrate`, and works. Every model call, every tool call, every file edit lands on one replayable record. `substrate resume` continues the session across daemon restarts. `substrate session end reviewer` cleans up a named standing sub-agent. `substrate run code_review --repo . --ref HEAD~1` fans reviewers over a real diff. `substrate bundle create team-review --wizard` scaffolds a bundle from questions. The UI's desktop view shows five session controls; the terminal view shows the transcript.

All 17 conformance checks pass (`substrate conformance`). Full-suite regression green: ruff + mypy strict clean; every new test named in the tech spec present and passing.

## What ships in v1 vs later

Ships v1: everything in pieces 0-H plus G.

Ships v1.5: transcript summary+tail strategy (product spec §4a); the `SessionWarning{bundle_changed}` handling on live-bundle-swap (product spec §7b PATCH).

Deferred (matches product-spec deferrals): `author_topology` (§5c), semantic compaction (§4a), retrieval plugin (§7b), MCP server + MCP client (§5f), real PTY, standalone-app wrapper, movable panes, thinking capture, graphite skin, terminal-V1 identity.

## Companion documents

- `TASK-BREAKDOWN-2026-08-25-daily-driver.md` — every sprint's scope, files, contract in one place.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` — the mechanical translation this roadmap dispatches.
- `current-design-direction/PRODUCT-SPEC-2026-08-17-round12.md` — the product this ships.
- `current-design-direction/DAILY-DRIVER-2026-08-17.md` — the vision this serves.

---

*Roadmap, 2026-08-25. Piece 0 is the first dispatch; 202 opens the chain. G lands in `substrate-ui/sprints/` after A-F close in this chain.*
