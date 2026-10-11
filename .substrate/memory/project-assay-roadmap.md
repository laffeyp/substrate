---
name: project-assay-roadmap
description: "The shape of assaying ALL substrate topologies — two programs (answer-producers vs dynamics), per-topology oracle/ablation, effort tiers"
metadata: 
  node_type: memory
  type: project
  originSessionId: 6213fff8-2552-4b26-8c40-aa765e0e8cc4
---

The roadmap for getting every topology rigorously assayed (not just wiring-tested). The user wanted the SHAPE known, not built yet. Two kinds of topology need two kinds of assay — conflating them is the category error (don't measure debate by "does it beat one model on QA"). See [[project-substrate-benchmarking-phase]], [[project-benchmarking-power-reality]].

**SCOPE DECISION (2026-06-26):** Split into TWO passes. The active build = tractable ENGINEERING only. Everything hard-and-genuinely-novel routes into a separate, later **RESEARCH PASS** — batched, not done inline, so one research problem never gates broad coverage.
- **Build pass (now):** all answer-producers (pair_coding, code_review, adversarial_pair, tool_loop, recursive_decomposition) + the dynamics with concrete oracles (game_of_life = exact Conway; prisoners_dilemma = game theory; intel_asymmetry = intel-ablation). These reuse the proven machine / have a known oracle.
- **Research pass (later):** the emergence-vs-faking instrument — **debate** and **natural_conversation**. ROUTING RULE: if any build-pass topology turns out to need genuinely-novel emergence/faking instrumentation to measure honestly, it ALSO routes to the research pass rather than blocking the build. The research pass is where the novel stuff accumulates to be tackled together.

**Already true:** every topology has WIRING tests (SDD dual contract; dynamics ones share `test_conversation_topology`/`test_bundled_topologies`). The gap everywhere = the behavioral ASSAY (powered, honest measurement). Only coding_flow has it. `topologies/instruments/` (calibration scoring rules that pay-to-close-cheap-talk, repair detector, common-ground extractor, confidence grader) is the SEED of the dynamics-measurement layer.

**Program A — answer-producers** (emit a gradeable answer; reuse the proven coding_flow assay machine — oracle/suite/run/report/stats/firewall):
- coding_flow — DONE (firewalled bank, ablation, powered; verdict: free orchestration closes ~73% of gap to 480B, significantly worse + flakier, not equivalent).
- pair_coding (driver+navigator) — reuse coding bank; ablation vs single coder. CHEAP.
- code_review (write→review) — reuse coding bank; ablation write-only vs write+review. CHEAP.
- adversarial_pair (writer vs vuln-finder) — coding bank + a SECURITY held-out; ablation single-shot vs refined. MEDIUM.
- tool_loop (model→tool→model) — NEW tool-use bank; ablation vs no-tool single-shot. MEDIUM.
- recursive_decomposition (planner→solvers) — NEW decomposable-task bank; ablation flat vs decomposed. MEDIUM.

**Program B — dynamics topologies** (instrument a DYNAMIC + an emergence-vs-faking discriminator; oracle = log-projection on the dynamic, often vs a KNOWN theoretical baseline — NOT accuracy-vs-baseline):
- game_of_life (+_glider) — Conway CA, NO LLM; oracle = exact Conway rules (glider translates, blinker oscillates). CHEAP/deterministic.
- prisoners_dilemma (payoff asymmetry) — oracle = GAME THEORY (Nash, tit-for-tat); measure cooperation/defection, response-to-strategy. CHEAP–MEDIUM.
- intel_asymmetry (information asymmetry) — metric = does the joint call REQUIRE both private intel pieces? (ablate one agent's intel, watch the answer degrade). MEDIUM.
- natural_conversation vs _bare — the ABLATION pair IS the instrument; measure the claimed emergent property with _bare as null. MEDIUM–HARD.
- debate (positional asymmetry) — does debate move a judge TOWARD truth (emergence) vs capitulate (faking)? Needs known-truth claims + calibration scoring. HARD — the research frontier; where "reshape the topology to be measurable" applies.

**Cross-cutting rigor contract** (the coding_flow review's lessons, now a checklist every assay INHERITS via the shared layer, not re-derives): firewall where there's an answer; ONE currency no splice (label pass^k vs pass@1, surface flakiness); power/MDE sized BEFORE running (equivalence needs ~360 problems at δ=0.10 — most B-topologies report the dynamic, won't attempt equivalence); provenance (config fingerprint + run-id + self-describing JSONL) + real metering; corrected paired stats (margin-proper verdict, [0,0] degenerate→inconclusive guard, 90% CI for TOST).

**code_evolution (NEW build-pass answer-producer, 2026-06-26):** an evolutionary/FunSearch-style topology — generalizes coding_flow into a persistent population + continuous fitness (correctness + cost to minimize) + elitist selection + LLM mutation-on-elite + stagnation. Increment 1 BUILT + verified (topology, pure `_decide`, deterministic test; placeholder cost = AST-node count). Increment 2 = real fitness (executed-op count measured on HELD-OUT inputs, so the firewall catches cost-overfitting = EA's reward-hacking) + a continuous-fitness bank. Increment 3 = the EA-vs-best-of-N ablation — which NEEDS the continuous-score comparison (the Tango/Nam **score-TOST** the review flagged as owed; so this gives that stats upgrade a concrete home). The honest claim: EA only beats best-of-N when there's a cost GRADIENT; on binary pass/fail it collapses to coding_flow — the assay is built to report that null honestly.

**The surprising shape:** little of it is novel. The proven machine covers all answer-producers + the two exact-oracle dynamics (game_of_life, prisoners_dilemma). Only the debate/conversation emergence-vs-faking instrument is genuinely new ground.
