# Phase 2 — Applications + visibility (summary)

*Two-minute overview of what's next. Detailed plan: `process/sprints/PHASE2_PLAN.md`. Sprint cards: `process/sprints/sprint-100..1xx-*.md`.*

---

## What this phase delivers

Phase 1 produced the runtime. Phase 2 produces the surface most users actually touch:

1. **A bundled topology catalogue** — six new application topologies that demonstrate what the substrate can do, beyond R-1/R-2/R-3.
2. **A terminal UI** (`rostrum tui`) — a live view of a running or recorded topology, with replay scrubbing, focused mode, and tree mode.
3. **A topology gallery** — `rostrum topology list`, `rostrum demo <name>`, `rostrum demo replay <name>`, with pip-installable community topologies.
4. **An interactive tutorial** — `rostrum tutorial step<N>` walks through writing a topology with live feedback.

The point: the runtime is invisible without applications and visibility. Phase 2 makes it visible.

---

## Why now

The runtime ships v1.0 with the conformance gate green. Without applications and a UI, the value proposition lands only with people who already understand event-sourced concurrent dataflow. Phase 2 makes the value visible to people who don't have to take it on faith — they can run a demo, watch the bus in the TUI, and see what happened.

Local small models change the constraint. Qwen 2.5 1B / Llama 3.2 1B / Phi-3 mini via Ollama or vLLM with batching can run 30–50+ concurrent Producer instances on a consumer laptop. The reference topologies' "walkthrough mode" stops being a pre-release smoke test and becomes the default user experience.

---

## The four waves

| Wave | Scope | Sprints |
|---|---|---|
| **10 — Survey + design** | Catalogue the candidates; design the TUI before any code | S-100 application survey · S-110 TUI design spec · S-10.bridge Textual SDK mapping · S-10.INT |
| **11 — Three priority topologies** | Build the user-named ones first | S-130 code review (5-LLM) · S-131 pair coding · S-132 recursive decomposition · S-11.INT |
| **12 — TUI build** | Textual app on public surfaces alone | S-120 app shell · S-121 topology graph overlay · S-122 replay scrubber + focused + tree modes · S-123 per-Producer latency · S-12.INT |
| **13 — Three more topologies** | Shock-and-awe set | S-140 population simulation · S-141 adversarial pair · S-142 research workflow · S-13.INT |
| **14 — Gallery + records + tutorial** | The discovery and on-ramp surface | S-150 bundled registry · S-151 demo records · S-152 narration overlays · S-153 interactive tutorial · S-14.INT |

Waves 11 and 12 run in parallel — the topologies don't need the TUI to build, and the TUI needs only the existing R-1/R-2/R-3 records plus the Wave-11 outputs to test against.

---

## The six new topologies

| Topology | Demonstrates |
|---|---|
| **`code_review`** (5-LLM ensemble) | Role-distinct system prompts, fan-in adjudication, cancel-all-others |
| **`pair_coding`** (driver + navigator) | Routes-into-future-instantiation pattern; chunked concurrent streaming |
| **`recursive_decomposition`** (planner + solvers) | Recursive Triggers at unbounded depth — the LangGraph-impossible demo |
| **`population_simulation`** (50+ agent producers + world-state) | Batched concurrent LLM execution on consumer hardware |
| **`adversarial_pair`** (writer + vulnerability-finder) | Two streams running concurrently from t=0 |
| **`research_workflow`** (retrievers + synthesizer + fact-checker + pause-for-review) | Multi-primitive composition — "you can wire all this?" |

Each ships with: Python module, CI-mode record (deterministic stand-ins; replays byte-identical), walkthrough-mode record (run against a real local LLM; committed), and a walkthrough doc.

---

## The TUI in one sentence

Textual app that attaches to a live or recorded substrate run via the public `attach()` API, renders the event stream with semantic coloring, overlays a topology graph generated from `RunStarted`, surfaces writer-stats via the sidecar, and supports replay scrubbing, focused-on-one-Producer mode, and ancestry-tree mode for recursive-decomposition demos. Built only on `substrate.api` and `textual` — verified by import-linter. It's the second public proof that F-API-6 (UI-buildability on public surfaces alone) holds.

---

## What's deferred (and why)

- Speculative execution with rollback — needs a fork tool that doesn't exist yet.
- Federation — needs transport + signing; out of v1.x scope.
- Self-modifying topologies — needs the topology-mutation primitive that v1.0 doesn't have.
- Cross-run delta predicates — needs the persistent-bus opt-in design pass.
- Steganographic capture — niche; needs a topology author with a real use case.
- Meta-orchestration / topology-as-output — needs sandboxed topology execution; design pass first.

None of these are closed. Each is parked with explicit reasons. Each becomes a Phase-N when the dependencies land.

---

## Open questions for Architect ratification

Q-2.1 Remote topology installation via `pip` from the gallery? · Q-2.2 Tutorial in v1.1 or v1.2? · Q-2.3 Default `population_simulation` agents — 25 or 50? · Q-2.4 TUI `replay --diff` in v1.1 or v1.2? · Q-2.5 Bundled-topology naming (`substrate.topologies.bundled.X` or `substrate.topologies.X`)?

See `process/sprints/PHASE2_PLAN.md` §"Open questions" for full text.

---

## After Phase 2

v1.1 ships: runtime + applications + TUI + gallery + tutorial. The substrate now has both the kernel-level rigor (Phase 1) and the application-level surface (Phase 2).

v1.2 candidates: the deferred list above, plus whatever 0.x external adopters surface. Decision deferred to a Phase 3 plan written after Phase 2 closes.

---

*Phase 2 plan ratified by Architect → BLACKBOARD `## Decisions` → sprint dispatches begin.*
