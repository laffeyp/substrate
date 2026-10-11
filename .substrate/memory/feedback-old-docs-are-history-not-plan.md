---
name: feedback-old-docs-are-history-not-plan
description: "Old planning/direction docs in this project are historical. The reveal-shell atom migration (Phase 8) is what \"cockpit\" became. Don't propose past epics as future work."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 21f7b8e2-3b74-423c-b088-70467776e917
  modified: 2026-09-24T23:16:00.846Z
---

Old planning docs (COCKPIT-DIRECTION-round2, prior vision notes, pre-Phase-8 plans) describe past direction, not queued work. What "cockpit" was IS the reveal shell now: substrate-ui at `web/reveal.html` + the React atom transcript from Phase 8. That epic is done.

**Why:** The user shipped it. The current substrate-ui running at `127.0.0.1:8765` (multi-pane, movable-cell grid, per-pane controllers, real transcript, real reveal-view, tool cards under `<details>`) IS the cockpit those old docs pointed at. Treating those docs as forward-looking wastes a turn re-proposing what's already merged, and reads as failing to recognize the current state.

**How to apply:** When surveying "what's next," read the current code and the current `BLACKBOARD.md` / `KIT_DIARY.md` first; treat anything under `process/planning/*` that names a phase before the last one closed as history. Prior memory that describes a past epic as "the north star" is stale — verify against the actual codebase before repeating it. If a memory conflicts with what the code shows, trust the code and mark or remove the memory.

Corollary: don't invoke old-cockpit direction, old-round-N-redesign, or prior product-vision docs when proposing next work. The queue lives in current sprint cards, `BACKLOG.md`, and things the user says out loud in-session.
