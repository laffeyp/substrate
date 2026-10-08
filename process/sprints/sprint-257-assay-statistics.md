# Sprint 257 — Assay statistics

```yaml
---
id: 257
status: open
opened_at: 2026-10-08
pass_kind: remediation
roadmap: substrate-ui/process/planning/ROADMAP-2026-10-08-lens-audit-remediation.md
ledger_rows: 28
---
```

## why

Score-TOST has no caller; two definitions of graded disagree (probe); pass^trials is labelled pass^k; salvage inflates per-call efficiency; the bank cannot earn equivalence (findings §1).

## sources

- Tango (1998) / Nam (1997) score-based equivalence; project memory: n ≥ 90/160/360 at δ = .20/.15/.10.
- Roadmap decision: bank ≥ 160.

## scope (ledger rows)

Each row closes as named; a row the sprint cannot close halts the sprint.

| id | close | finding |
|---|---|---|
| F215 | fix | stats.py:15-17 says the Tango/Nam score-TOST is "the upgrade owed before any equivalence claim actually runs"; stats.py:249 implements it; nothing calls `equivalence_verdict_score_tost` (grep src/, scripts/, substrate… |
| F216 | fix | report.py:496-499 vs 379-385 — two definitions of "graded" in one function. `_meets_floor` counts not-run cells as ungraded; `graded_rate` (reported, and the RunUnpublishable trigger l.594) counts only NO_VERDICT. Pro… |
| F217 | fix | report.py:193-205 + 79-81 — `pass_rate` comment "pass^k-COLLAPSED"; `_cell_passed` collapses to all-trials-pass, i.e. pass^(trials), not pass^k. With trials=5, pass_k=1 the McNemar/`delta_vs_control` currency is pass^… |
| F218 | fix | stats.py:88-94 — `_phk` uses `kk = min(k, n)`; a cell with fewer trials than k silently scores pass^n. suite.py:106-107 comment "k>1 needs trials >= k"; Suite.__post_init__ checks only `pass_k >= 1`; no check anywhere… |
| F219 | fix | run.py:321 + report.py:520,573 — SALVAGE cells carry `_ZERO_USAGE`; their passes count in `passes` but their model calls are 0, so `resolve_per_call = passes / model_calls` is inflated in proportion to the salvaged fr… |
| F220 | fix | preregistration.py:23-25 — "Timestamp verification … the confirmatory runner does that at its own boundary". scripts/assay_swebench_confirmatory.py has no git commit/rev-parse/log check (grep). Pre-registration-before… |
| F221 | fix | preregistration.py:118-121,145-154 — params missing from `params_by_arm` are "treated as absent"; a runner that passes no params hashes {name, role} only, so the 151-#1 reroll (same name, N=3 -> N=5) passes whenever b… |
| F222 | fix | cells.py:244-270 — "tamper-evident": `config_fp` is sha256 of meta's own fields, stored in the same editable file; the cells JSONL "append-only anchor" is an ordinary file. Detects an edit that forgets to rehash; not … |
| F223 | fix | cells.py:70-80 — every row reconstructed as `metric="resolved-held-out"`, `oracle_class=EXTERNAL_GRADER`, `replayable=False`, coding and swebench alike; `detail` = the row's `source`. coding_oracle's metric is "resolv… |
| F224 | fix | oracle.py:57-108 — `Result.score` and `Result.verdict` are independent fields (docstring: "the underlying fact lives in one field, verdict"); `Result(score=1.0)` with default `verdict=NO_VERDICT` reads `passed=False`.… |
| F225 | fix | oracle.py:160-188 — `ExternalGraderOracle` takes `(bool, str)` from its grader and can only emit PASS/FAIL; the H-1 NO_VERDICT state is unreachable through the generic external-grader class (coding_oracle's sandbox ti… |
| F226 | fix | conformance.py:23-25 exports `PASS="pass"`, `FAIL="fail"` and oracle.py has `Verdict.PASS="pass"`, `Verdict.FAIL="fail"`; assay/__init__ exports both families. Same words, different vocabularies (control-check state v… |
| F227 | fix | run.py:166-177 `run_suite` (sequential, no budget/salvage/classification) and run.py:248 `run_suite_with_salvage`: two suite orchestrators. |
| F228 | fix | run.py:340-343 — `asyncio.wait_for(run_arm_on_case(...), timeout)` cancels the coroutine; `oracle.grade` runs in `asyncio.to_thread` (l.152), which cancellation cannot stop — a timed-out cell's Docker grade keeps runn… |
| F229 | fix | report.py:34 — the generic report imports `REASON_HARNESS_ERROR` from assay/swebench (benchmark-specific module); report.py:245-252 `_extract_reason` keeps parsing ` reason=` out of detail after oracle.py:88-95 made r… |
| F230 | fix | report.py:595 — `n_missing = m.n_attempted - (m.n_attempted - m.n_no_verdict)`. |
| F231 | fix | coding.py:113-124 vs topologies/swebench_solver/select_exec.py:44-78 — two positive-evidence pytest-summary parsers (`_PASSED_RE`, `" failed"`/`" error"` substring vs `\d+\s+failed`/`\d+\s+error`). coding.py:121 subst… |
| F232 | fix | coding.py:102 — `expected = sum(t.count("def test_") …)`: textual count, includes `def test_` in comments/strings/helpers; a helper named test_* inflates `expected` and fails a correct candidate. |
| F235 | fix | stats.py:46-52 verdict words SUPERIOR/EQUIVALENT/INFERIOR/INCONCLUSIVE/UNDERPOWERED as bare str constants (fifth vocabulary convention). |
| F265 | fix | coding_problems.py — 71 problems. stats.equivalence_power_floor: 90 / 160 / 360 at margin 0.20 / 0.15 / 0.10; coding_suite default margin 0.1 (coding.py:145), cells.py default 0.1. `equivalence_verdict` can return EQU… |
| F266 | fix | coding_problems.py — the bank is textbook exercises (fizzbuzz, two_sum, roman, Kadane, LCS, …); 8 held-out/dev inputs are verbatim canonical public examples (e.g. 'loveleetcode', ['flower','flow','flight'], 'A man, a … |
| F267 | fix | coding_problems.py:19 — the held-out grading command is `ruff check . && mypy --strict . && pytest`: "resolved-held-out" fails a behaviourally correct candidate on a lint or type error. The metric name says tests; the… |
| F268 | fix | conformance.py:259-267 — check 5 "Quiescence" ("A logical-cooldown run finalises via quiescence-with-watchdog") runs `_basic_topo`, whose termination is `threshold_count(PRODUCER_COMPLETED, 1)` (l.128). The check pass… |
| F269 | fix | conformance.py:132-183 — check 1 "Retry enrichment … the failure reason STAGED FROM THE SAME EVENT": the retry trigger's input_builder reads `ctx.event.payload["error"]` directly; no Route, no staging. R-2 (r2_pipelin… |
| F270 | fix | conformance.py:224-230 — check 3 "Backpressure liveness" sends 3 events through admission=1; a burst of 3 does not exercise sustained backpressure. |
| F271 | fix | conformance.py:540 `floor = 40_000` literal; conformance_perf.py:22-24 repeats the figure in prose; "~56K measured" (l.534) is a remembered number, not recorded with machine/date. |
| F272 | fix | Three "PASS" vocabularies: conformance.Status.PASS="PASS" (enum), assay/conformance.PASS="pass" (str), oracle.Verdict.PASS="pass" (enum); `api` exports `Status` (conformance) by that bare name. |
| F280 | fix | conformance_perf.py:57-92 — the topology function is typed `b: object` and carries six `# type: ignore[attr-defined]`; `api.TopologyBuilder` is importable. |

## checks

- The equivalence verdict comes from score-TOST.
- The 2-of-4 probe reports graded_rate 0.5 and an unpublishable entry.
- pass_k > trials is rejected; the report labels its estimand.
- Salvaged cells carry usage from the record.
- The confirmatory runner refuses a pre-registration committed after the first cell.
- ≥ 160 problems, no verbatim canonical inputs; the held-out metric's name states what the gate checks.
- Conformance checks 1, 3, 5 exercise staging, sustained backpressure and quiescence.

## result

(filled at close)
