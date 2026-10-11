---
name: project-swebench-solver-plan
description: "The SWE-bench solver = a SIMPLE vanilla non-agentic Substrate topology (mostly our own build), with an SDD-solver as a deliberate v2 — NOT a complex synthesis of every OSS approach"
metadata: 
  node_type: memory
  type: project
  originSessionId: 6213fff8-2552-4b26-8c40-aa765e0e8cc4
---

**Decision (2026-06-26):** Build the SWE-bench solver as a Substrate-native topology. Keep it SIMPLE and mostly OUR OWN; take only the few best, adoption-verified ideas from OSS; do NOT over-synthesize into something complex.

**The vanilla solver (now) — three plain phases, no tool use:**
1. **Localize** (TAKE from Agentless — the one piece we lack): issue + repo → suspect files → functions → edit locations, via cheap grep/embedding. The prompt-factory assumed you already knew the files (`declared_files`); SWE-bench doesn't give you that.
2. **Repair** (KEEP ours): best-of-N + Aider-style **SEARCH/REPLACE** edits (NOT unified diffs — LLMs miscount `@@` lines; the prompt-factory learned this the hard way), apply to a repo clone, `git diff` → `model_patch`.
3. **Select** (take the idea, keep our correction loop): the FIREWALL — the solver canNOT see the held-out `FAIL_TO_PASS` (that's the grade). Agentless's answer: GENERATE a reproduction test from the issue + run the repo's EXISTING tests; rerank the N candidates by which pass.

**Adoption-verified OSS landscape (skeptical, per the anti-hype rule):**
- **Agentless** = the genuinely-adopted non-agentic gold standard — OpenAI used it to showcase GPT-4o/o1. The right model to mine; it IS the "simple counter-example to complex agents." Source: arxiv 2407.01489, github.com/openautocoder/agentless.
- **OpenHands+CodeAct** tops the open-source leaderboard (~53% Verified) but is AGENTIC (tool-use) — contrast, not base.
- **Moatless** (MCTS) and **AutoCodeRover** (call-graph/program-analysis) are real but are the COMPLEXITY trap — skip for vanilla.
- **Aider** — deprioritize the repo-map; we already took its SEARCH/REPLACE format independently.

**SDD is NOT ceremony — it's error-correction that makes the model write better.** The dual-contract grade, the verify-against-real-API preflight (the prompt-factory's `drafter`/`preflight` — give the model the REAL signatures so it can't hallucinate APIs; Swift-bound there, rebuild on Python AST), the correction loop, the rubber-duck pass. This becomes a deliberate **v2 "SDD solver"** that wraps the vanilla one — corrects the earlier "drop the ceremony" framing in process/BLACKBOARD.md + docs/swebench-bridge-mapping.md.

**The prompt-factory (`_factory/prompt-factory/orchestrate/`, ~8.5k LOC, read in full) is REFERENCE ONLY — never reuse the code directly, ever.** It's one design input. Its `signal_emitter.py` is a hand-rolled event log = Substrate's Bus rebuilt by hand → the port deletes it and uses the record. See [[next-app-coding-flow-on-substrate]], [[project-containerization-requirement]], [[project-assay-roadmap]].

**STATUS (2026-06-27): BUILT end-to-end; first real-model solves done (exploratory).** All three phases wired in `substrate/src/substrate/topologies/swebench_solver/` (localize/repair/applier/select/select_exec/select_docker/select_regression/reproduction/assemble), branch `track-assay-benchmarking`, sprints 133–155. The SELECT firewall is real: regression reuses ONLY swebench's per-repo install + test_cmd (never eval_script's selection / never test_patch), test set from the checkout via a deterministic proximity picker (never PASS_TO_PASS), signal = passed-at-base/`regression_held` (scope-aware). Smoked on the LIVE flask-4045 container; two real-model runs: qwen2.5-coder:7b → honest negative, qwen3-coder:480b → honest PARTIAL fix (1/2 FAIL_TO_PASS, SELECT discriminated). The plumbing produces a real, applyable, regression-clean, near-correct patch — a full resolve is now a model+n question. Two open design Qs (BLACKBOARD `## Open questions` SWE-Q-1/2): the reproduction signal false-positives (model-generated repro is biased to what the model fixed — tiebreak not certifier); `exclude` uses test_patch paths (disclosed via `exclude_delta`). Reviewer-gated next: collection-survival discovery before multi-repo; power gates + pre-registration before ANY reported resolve-rate. The reproduction-false-positive reinforces [[be-your-own-skeptic-green-is-not-proven]] (the run_id cache-collision reused a stale grade — caught by reading the oracle log).
