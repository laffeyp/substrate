---
name: project-benchmarking-power-reality
description: "verified power numbers for the assay's paired-binary design — n=10 can't earn equivalence; the right test; trials are the wrong knob"
metadata: 
  node_type: memory
  type: project
  originSessionId: b961bf01-3a14-4cb4-a99f-1ee07812dc68
---

Monte-Carlo power analysis of the assay's paired-binary design (exact McNemar over per-problem resolved/not bits; pass^k = all-k-trials-pass collapse), adversarially re-derived and confirmed (2026-06-25):

- **A 10-problem bank cannot earn a powered equivalence claim at any defensible margin.** TOST power at n=10 (and n=6) is ~0 for δ=0.10/0.15/0.20; brute force shows equivalence within ±0.20 at n=10 is *literally impossible* (no outcome table passes; first feasible margin 0.25 via the degenerate zero-discordant table). Structural reason: exact two-sided McNemar needs ≥6 same-direction discordant pairs before p<0.05 (2·0.5⁶=0.031), so ≤10 problems exhaust the discordant budget before any inference. This is exactly why the framework honestly refused the 4/6-vs-4/6 call.
- **Required problems for ~80%-powered equivalence:** δ=±0.20 → ~90; δ=±0.15 → ~160; δ=±0.10 → ~360. Scales as ≈ p_disc/δ² (halve the margin ⇒ ~4× the bank). Detection (catching a real difference) is far cheaper than equivalence; the weak-vs-strong win was effectively a 6-0 discordant sweep.
- **Trials are the wrong knob for the comparison.** Growing k at fixed n narrows the CI only via a floor-effect artifact (pass^k deflates both arms toward all-fail), a hollow "equivalence at solving nothing k-in-a-row"; McNemar power at a fixed real gap flatlines/degrades with k. Only adding PROBLEMS narrows the between-problem CI legitimately (1/√n). Trials help within-problem variance second-order; keep k for a separately-labeled reliability estimand, never as a substitute for n.
- **CORRECTION to earlier advice:** bit-collapse → exact McNemar does NOT inflate type-I — it is CONSERVATIVE (A/A type-I ≈0.004 at n=10), because trial noise IS the discordant-pair mechanism McNemar conditions on. The two-level cluster bootstrap is the slightly LESS safe one at small n (≈0.068). So the A/A calibration check should show ~0 rejection, not >5%; a reading near/above 5% means something broke (e.g. a Wald approximation swapped in).
- **Right test for the equivalence claim:** score/RMLE TOST on the matched-pairs difference (Tango 1998 — McNemar is its δ=0 special case; Nam 1997), pre-register δ. NOT "p>α ⇒ equivalent" (absence of evidence) and NOT the Wald CI-inclusion TOST (anticonservative, worst-case type-I ~0.20 at n=10; falsely "equivalent" at zero discordant pairs). Tiny banks: unconditional exact paired equivalence test (Hsueh/Liu/Chen 2001). Frame via TOST (Lakens 2017 / Schuirmann 1987).
- **pass^k vs pass@k trap (the #1 thing to guard):** pass^k (reliability, harder with k) and pass@k (coverage, easier with k) move opposite. Best-of-N gains (Brown 2024, Snell 2024) are pass@k, gated on a verifier; if the small stack leans on best-of-N selected on VISIBLE tests rather than the firewalled held-out grader, it both flips the certified estimand and inflates coverage — the likeliest source of an impressive-but-hollow number.
- **Big-gap (480B) is a legitimate matched-COMPUTE comparison, not a different question** — provided the matched currency is fixed a priori (FLOPs/tokens/wall-clock, NOT parameter count). Many small calls vs one big pass at matched compute IS Snell's compute-optimal result. Relabel as capability/cost substitution and make the verifier explicit.

Links: [[project-substrate-benchmarking-phase]], [[project-no-cost-tracking]], [[be-your-own-skeptic-green-is-not-proven]].
