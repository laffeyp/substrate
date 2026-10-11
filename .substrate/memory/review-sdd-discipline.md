---
name: review-sdd-discipline
description: "As reviewer, hold substrate's work to the SDD (sdd-kit-2) methodology bar, not just code/prose correctness"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 842e2bb4-a7fc-477f-ae47-13df46ecbd68
---

When reviewing substrate, add the Signal-Driven Development lens (sdd-kit-2, read in full 2026-06-13) as a standing review dimension alongside code-correctness, the engineering canon [[review-engineering-canon]], and prose [[review-writing-white-orwell]]. The user's directive: "with SDD, keep us on track."

**Why:** substrate adopted sdd-kit-2 as read-only canon (`../sdd-kit-2/AGENTS.md` first, then `WORKING_AGREEMENT.md`). Reviews must check the work honors the methodology, not just that the code runs.

**The load-bearing checks (verify, don't trust):**
- **Vocabulary is the contract** (PRINCIPLES commitment 1-3): reserved `substrate.*` kinds live in the locked vocab (`signals/0.2.json`); Producer-declared/application kinds are per-topology, strict-validated at the bus boundary, NOT vocab additions (the R-1/R-2/R-3 precedent). No unilateral tag invention — needs a typed proposal via the 8 evolution kinds + Architect ratification + version bump.
- **The 12 hard rules** (AGENTS.md), esp.: #6 ≤2 files/one concept (else decompose, technique 17); #9 observation contract for behavior-touching/UI sprints (the soundfield round-23 trap; `observation_contract_missing` is a halt); #10 hand-author needs authorization; #11 originals over summaries; #12 no deletions (additive/round-N only).
- **Dual + observation contract** both pass to close. Content assertions do NOT cover product behavior — UI/replay/behavior sprints need driving steps + expected signals/visible state.
- **Halt-and-articulate** (#4): deviations from a sprint card and spec/vocab gaps must be SURFACED to BLACKBOARD `## Surfaced for review` (never silently decided; never fabricated to avoid halting). `## Decisions` is Architect-only.
- **Rubber Duck Pass** at close is defensible only because it grounds on external check surfaces (locked vocab, dual contract, tone canon) — not intrinsic self-critique.
- **Signal ≠ log**: typed, stable, schema-enforced-at-emit; honesty events (don't fake-emit; a `supports*=false` / explicit deferral beats a silent no-op).

**How to apply:** name the rule/commitment when citing an SDD finding (as with GoF/White-Orwell). Compose with runbook §5 impact-weighting — silent no-ops and honesty-of-status (a plan/card claiming a discipline it violates, e.g. the false "≤2 files honored" claim) rank high. Already applied in reviews #14 (hard rules 6/9/12, A1.1 deferral, vocab discipline) and #15 (vocab precedent, deviation-surfacing, observation contract).
