# Sprint 293 — The console's compaction row; live test

```yaml
---
id: 293
status: closed
closed_at: 2026-10-11
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-11-compaction.md
asked: 2026-10-11 (Architect)
---
```

## scope

- substrate-ui: the compaction row names what was cleared or dropped, and a repeated cut does not appear. An opt-in live test reruns the codex case: a heavy second turn, then a question that needs it. Full kernel and UI suites once.

## checks

- The third turn's prompt holds the first two user messages and replies, and the model answers from them; suites pass.

## result

- **Console row** (`substrate-ui/web/vm/session_controller.ts`). It reads `cleared_through_seq` and an absent `dropped_seq_range`, and says what was cut: "— prompt history: older tool output cleared (results through seq 33)", or "earlier turns dropped (seq 17–27)". A cut equal to the last one shown adds no row, so the codex record's three "17–146" rows show once. Specs in `harness_tool_rows.spec.ts`: the dropped row, the cleared row, and the repeated cut.
- **Live test** (`test_compaction_live_293.py`, opt-in `SUBSTRATE_LIVE_DRIVER_TESTS=1`), run against real codex at a 30,000-token window: turn 0 gave the code word PELICAN-42; turn 1 ran `cat big.txt`, a 144,000-character harness result (seq 23); at turn 2 the cut was `tool_output_cleared` through seq 23, 36,141 → 153 estimated tokens, no turn dropped; the prompt held the code word and codex replied `PELICAN-42`. Under the old rule, 36,141 tokens against an 18,000-token budget would have dropped turns 0 and 1. 17.3 s.
- **Full suites, once.** Kernel: 1,496 passed, 9 skipped (opt-in tiers). UI unit specs: 32 passed. UI Python: 244 passed, 5 skipped.
- **Not in the installed app yet.** The app picks this up at the next build and install.

