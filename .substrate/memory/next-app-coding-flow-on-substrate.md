---
name: next-app-coding-flow-on-substrate
description: Planned next Substrate application — rebuild the prompt-factory coding orchestration (best-of-N + build-validation + correction loop) as a Substrate topology
metadata: 
  node_type: memory
  type: project
  originSessionId: c5f5786b-ac39-4cfa-8bb3-319304032ea2
---

A planned **next application** on top of Substrate: the coding-orchestration flow the prompt-factory precursor implements by hand (`/Users/peterlaffey/Documents/conversation_soundfield_app/soundfield_build/_factory/prompt-factory/orchestrate/`). The user's point: that exact flow "could probably be built on top of the substrate" as one of the next applications.

**Why:** the precursor hand-rolls a dispatch loop that is *exactly* what Substrate's primitives express natively:
- **best-of-N** (`dispatch/best_of_n.py`): N candidate worker calls in parallel → score → pick winner → cancel the rest. That is an **ensemble topology** (parallel Producers + a Bus quorum + adjudicator + cancel-all-others) — the R-1 pattern, already built.
- **build-validation gate**: apply each candidate's artifacts, run a validation command, keep only build-passing winners. A deterministic Predicate / Trigger over the candidates' emitted artifacts.
- **correction loop** (`dispatch/correction.py`): on failure, re-dispatch with the error fed back. A cascade (failure event → retry Producer with enriched input) — the R-2 structured-error pattern.

So the coding flow ≈ ensemble (best-of-N) + a validation Predicate + an R-2-style correction cascade, composed. It is a strong showcase because it composes three primitives that already work, and it is genuinely useful (real coding workflow). The model seam is the rebuilt [[be-your-own-skeptic-green-is-not-proven]] `OllamaResponder` (now native /api/chat + think=False + num_ctx + retry).

**How to apply:** after the real-model path + existing-application demos are solid, propose this as the next application — a `coding_flow` topology with best-of-N coder Producers, a build-validation Predicate, and a correction cascade, demoed against real local models. Do NOT start it until the foundation work (adapter + per-application real-model demos) is finished and verified.
