# Sprint 254 — Topologies tell the truth

```yaml
---
id: 254
status: open
opened_at: 2026-10-08
pass_kind: remediation
roadmap: substrate-ui/process/planning/ROADMAP-2026-10-08-lens-audit-remediation.md
ledger_rows: 82
---
```

## why

Four sites discard the model's reply; parsers read replies as their opposites (measured); the best_of_n loop exists four times; three error policies coexist (findings §1, §2).

## sources

- Roadmap decision: one failure policy (typed ProducerFailed; oracles map mechanism failure to NO_VERDICT).

## scope (ledger rows)

Each row closes as named; a row the sprint cannot close halts the sprint.

| id | close | finding |
|---|---|---|
| F112 | fix | applications/registry.py:214-224 — `_scan` with on_error="skip" drops a malformed manifest with no log line and no return of what was skipped; the module docstring (l.15-16) says "the daemon catches and logs", but the… |
| F113 | fix | registry.py:110,184 — `kind` and `runs` are validated through `SlotKind(kind)` / `ApplicationRuns(runs)`, then the raw str is stored (`SlotSpec.kind: str`, `ApplicationSpec.runs: str`). The enum is checked and discard… |
| F114 | fix | registry.py:192 — `on_error: str` takes "skip"/"raise"; any other string behaves as "skip". Stringly-typed flag. |
| F115 | fix | registry.py:75-92 — `SlotSpec` / `[slots]` parsed for every manifest; docstring says the binder was deleted in sprint 065 and the type "stays as a shape declaration until a real consumer surfaces". Parsed state with n… |
| F116 | fix | registry.py:129 — docstring line garbled mid-sentence ("in sprint 223; the spec always wanted"). |
| F117 | fix | applications/pair_coding_composite.py:11-17 — two different things named `pair_coding` (this application and `topologies/pair_coding`); the docstring documents the collision instead of resolving it; BUNDLED renames on… |
| F118 | fix | pair_coding_composite.py:91-111 — builder session is created, then reviewer; if the reviewer `create` raises (NameCollision, disk), the builder manifest stays registered with no reviewer. No rollback. |
| F119 | fix | pair_coding_composite.py:77-78 — `mkdir(parents=True)` on a caller-supplied workspace path at registration. |
| F120 | fix | applications/fanout_review.py:58-81 — `subprocess.run` for git with no timeout; one `git diff --no-index` process per untracked file, all gathered before the 24k-char truncation (l.85). A tree with 10k untracked files… |
| F121 | fix | fanout_review.py:70 — `ls-files` stdout `.split()` on whitespace; a file named "a b.py" becomes two paths, each diffed against /dev/null and missing. `-z` + split on NUL is git's documented form for arbitrary names. |
| F122 | fix | fanout_review.py:111 — repo I/O (git subprocesses) runs when the topology function is built, not inside a Producer; the diff is captured outside the record's causal chain except via the ReviewSubject replay of it. |
| F123 | fix | fanout_review.py:116 — quorum clamp skips when `roles` is empty (`else quorum`), leaving quorum 3 with zero reviewers: the silent-no-answer case F-7 names, for the empty input. |
| F124 | fix | truncation-with-marker implemented separately at fanout_review.py:85-89 (`_MAX_DIFF_CHARS` 24_000), research_sweep.py:69-70 (`_MAX_DOC_CHARS` 8_000), coding_flow/gate.py:121 (4000, head+tail), tool_loop/substrate_tool… |
| F125 | fix | applications/best_of_n_verified.py:37-48 — `_verdict_passed` takes the first PASS/FAIL token anywhere, case-insensitive. Measured: "This does not PASS." -> passed; "Cannot pass: FAIL" -> passed; "I would not say it fa… |
| F126 | fix | best_of_n_verified.py:110 — model-sourced Verdict sets `returncode=0 if passed else 1`; `returncode` means a process exit code in best_of_n, here it is invented. `source="model"` (C-5) marks it but the field still car… |
| F127 | fix | best_of_n_verified.py:64,104; research_sweep.py:101,123,146 — `except Exception` converts every error, including TypeError/AttributeError from a programming bug, into a recorded "(draft failed: TypeError)" candidate; … |
| F128 | fix | `hasattr(inp, "get")` defensive input parsing: 114 occurrences in 28 files. Producer input is untyped (`inp: Any`) and each topology re-parses it field by field with defaults (`index` defaults to 0 at research_sweep.p… |
| F130 | fix | research_sweep.py:71 — source label is `path.name`; two documents with the same basename in different directories get the same label in Findings and the synthesis prompt. |
| F131 | fix | research_sweep.py:153 — `_round_findings`: research_sweep has no rounds. |
| F132 | fix | research_sweep.py:209 — `KindBuffer("Finding")` is unbounded with O(history) `value()` (views.py:52-53 says so); `value()` is copied on every Finding for the predicate (l.228), O(n²) over the sweep. |
| F133 | fix | best_of_n/__init__.py:24-25 — docstring: coding_flow's migration onto this module is "a later refactor (#43)… at most two copies of the wiring". Two copies of the loop wiring by design statement; VERIFY when reading c… |
| F134 | fix | best_of_n/contracts.py:50 — `Verdict.source: str = "gate"` with three documented values "gate"/"check"/"model" in prose only; no enum. Same class as the status vocabularies sprint 107 typed. |
| F135 | fix | best_of_n/__init__.py:100,104 — `termination: Any \| None`, `draft_input_extra: Any \| None`; docstring says the latter "must be a callable (TriggerContext) -> dict". The type says nothing. |
| F136 | fix | best_of_n/__init__.py:86-87,199-204 — `_round_verdicts` scans the whole unbounded KindBuffer twice per Verdict (predicate + input builder): O(history) per event. |
| F137 | fix | code_review/__init__.py:49,84 — `VerdictRendered.decision: str # "approve" \| "request-changes" \| "block"`; `_DECISIONS` tuple is a second copy; no enum. |
| F138 | fix | code_review/__init__.py:87-91 — `_decision_in` substring match. Measured: "Disapprove" -> approve; "The unapproved import is a blocking issue: approve" -> approve (correct by luck of order); "blocker"/"blocking" count… |
| F139 | fix | code_review/__init__.py:54-56,116-118 — `_severity_of` = sum(bytes) % 5 + 1, a hash. When the model's reply names no verdict word, the decision falls back to this hash; the walkthrough verdict is still noise in that b… |
| F140 | fix | code_review/__init__.py:106 — `responder is not None` on a parameter typed `Responder` (non-Optional). |
| F141 | fix | code_review/__init__.py:189-191 — comment: liveness for a stuck reviewer "rests on the model adapter timeout (OllamaResponder 120s → raises)". adapters/models.py:162,189: `timeout: float \| None = None`, and the sprin… |
| F142 | fix | code_review/__init__.py:34 — comment cites `r1_ensemble` as the precedent; it lives in reference/r1_ensemble.py (exists). OK. |
| F143 | fix | code_review reviewers have no failure guard: a raising responder -> ProducerFailed; with fewer than `quorum` critiques the judge never fires and all_completed finalises with no VerdictRendered — the silent-no-answer c… |
| F144 | fix | code_review/__init__.py:79 `text[:200]`, conversation.py:165 `text[:700]` — two more inline truncations (no marker). Running count: seven truncation sites. |
| F145 | fix | code_review/__init__.py:199-201 — cancel predicate retypes "judge" and walks the payload with getattr/isinstance defensiveness. |
| F146 | fix | debate:44, prisoners_dilemma:63, intel_asymmetry:89, natural_conversation:83 — `model: str = "llama3.2:1b"` default in four signatures; four copies of the model name, no single default. |
| F148 | fix | conversation.py:32-34,136 — the engine imports `REPAIR_OK` from `instruments.repair` and branches on `rep.get("status")`; the `Instrument` docstring (l.80-81) says "the engine … knows nothing about common-ground / rep… |
| F149 | fix | conversation.py:154-161,182 — `converge_at` is a test hook in the production signature; the docstring says real-model convergence "is NOT wired". `Converged` and its threshold termination exist only for the hook. |
| F150 | fix | conversation.py:150 — speaker call has no failure guard; a raising speaker ends the conversation with ProducerFailed, then quiescence finalises the run. |
| F151 | fix | instruments/common_ground.py:39, repair.py:43, grader.py:45 — each instrument calls the responder with a fixed prompt that contains no transcript ("scan the latest turn for misalignment", "update common ground from N … |
| F152 | fix | natural_conversation/__init__.py:92 — `_emergence_instruments(deterministic=not walkthrough)` never passes `responder`, so l.43 always uses `DeterministicResponder(seed=999)`, walkthrough included. `deterministic` is … |
| F153 | fix | instruments/grader.py:31,49-51 — `Grade.observed_outcome` documented as 0/1/0.5; produced as a hash bit; `score_grades` (l.62-70) then computes Brier/log-loss over hash values. Any calibration score from this pipeline… |
| F154 | fix | instruments/grader.py:65-69 — `losses` keyed by claim id; a repeated claim overwrites the earlier loss. |
| F155 | fix | prisoners_dilemma/__init__.py:33-44 — TALK checked first, anywhere in the text. Measured: "I will not talk. STAY SILENT" -> talk; "My options are STAY SILENT or TALK.\nSTAY SILENT" -> talk (the prompt l.49 asks the mo… |
| F156 | fix | prisoners_dilemma:30 `choice: str` ("silent"/"talk"); intel_asymmetry:30 `assessment: str` (offensive/routine/uncertain); instruments/repair.py:24-26,33 `status: str` with module constants but no enum. Three more pros… |
| F157 | fix | intel_asymmetry/__init__.py:37,45 — fallback `_CONF` takes the last "N%" anywhere in the turn as the analyst's confidence; `_OFFENSIVE` matches "pre-position", which is in the shared question text (l.62) an analyst ma… |
| F158 | fix | conversation demos: `outcome_fn` runs for every speaker (conversation.py:170-173), so ALPHA emits a Decision too, though the docstring (prisoners_dilemma:65-66) has BRAVO decide. |
| F159 | fix | game_of_life/__init__.py:194-197 — the step predicate scans the whole unbounded CellNext buffer on every CellNext: O(cells × history); for G generations of R×C cells, O((R·C)²·G) predicate work. |
| F160 | fix | game_of_life:211 — `quiescence_with_watchdog(seconds=2)`, a literal unlike the other topologies' `watchdog_seconds` parameter. |
| F161 | fix | game_of_life:126-128 — `cell` reads `inp.get(...)` unguarded two lines after the guarded `hasattr(inp, "get")` form (l.124); the defensive idiom is applied inconsistently even within one function. |
| F162 | fix | pair_coding/__init__.py:63-68 — driver calls the responder (`_ = await call_responder(...)`), discards the reply, and yields the canned `chunks[index]` in every mode. Comment l.63-65: "In walkthrough mode the chunk te… |
| F163 | fix | recursive_decomposition/__init__.py:73-77 — decompose-vs-solve is decided by `depth < max_depth` in every mode; no model decides the tree shape. The "unbounded, data-dependent spawn tree" (l.12-14) is depth-rule-depen… |
| F164 | fix | recursive_decomposition/__init__.py:12-14 — "This is the demonstration LangGraph structurally cannot do: its graph is declared statically". LangGraph docs (Graph API overview, docs.langchain.com/oss/python/langgraph/g… |
| F165 | fix | topologies/__init__.py:5-6,12-13 — "built ONLY on the public `substrate.api` surface"; the topologies import `...adapters` (not api). "Sprint 140 formalizes a registry … until then, import topologies directly": bundle… |
| F166 | fix | adversarial_pair/__init__.py:81-82,92-95 — `walkthrough=True` builds real Ollama responders but `deterministic` defaults True independently, so `adversarial_pair_topology(walkthrough=True)` records real-model kinds as… |
| F167 | fix | adversarial_pair:93,95 — two more `"llama3.2:1b"` literals (six total). |
| F168 | fix | adversarial_pair:70 — Challenge.severity = byte-sum % 3 + 1 ("a deterministic projection of the real finding"); third hash-as-severity site (code_review, grader). |
| F169 | fix | adversarial_pair:55 `text[:200]`; pair_coding:82 `rationale[:120]`; adversarial_pair:69 `[:120]` — the revision prompt receives the prior artifact cut to 200 chars. Truncation sites now ten. |
| F170 | fix | pair_coding/__init__.py:48 — `ChunkBoundary.kind: str # "function" \| "class" \| "file"`, always "function" (l.69); a payload field named `kind` beside the envelope's `kind`. |
| F171 | fix | coding_flow/__init__.py:68-256 — a full second copy of the best_of_n loop: `_seeder_factory` (=best_of_n.seeder_factory), `_judge_factory` (=select_first_judge_factory, message text "gate exit" vs "validation failed (… |
| F172 | fix | code_evolution/__init__.py:195 — mutator has no failure guard. A raising model call leaves the generation one Fitness short; the breed predicate (l.356) never reaches n; the run ends on the watchdog with neither Evolv… |
| F173 | fix | best_of_n/contracts.py:61 `Exhausted(rounds)` and code_evolution/__init__.py:101 `Exhausted(gens, best_cost)` — two schemas under one kind name "Exhausted". Kind name = struct `__name__`; a reader keyed on kind cannot… |
| F174 | fix | code_evolution/__init__.py:139,229-239 — `_decide` returns a ("evolve"\|"exhaust"\|"spawn", payload) string-tagged tuple; dispatch by string compare. |
| F175 | fix | code_evolution/__init__.py:108-121 — `_ast_cost` is documented PLACEHOLDER; "the reward-hacking firewall is NOT built … the claim is hollow until all three exist". The topology's only user is assay/coding.py (VERIFY w… |
| F176 | fix | coding_flow/gate.py:168-180 — `subprocess.run(gate, shell=True, timeout=…)`. On timeout Python kills the shell only. Probe: gates "sleep 8; echo done" and "sleep 8 & wait", timeout 1 s -> both returned "timed out" at … |
| F177 | fix | coding_flow/gate.py:125-138 — the gate inherits the full `os.environ` (HOME, tokens, API keys) and runs model-written code with it and with network; gate.py:99-100 names "process isolation; tracked separately". Candid… |
| F178 | fix | coding_flow/gate.py:121 — head+tail truncation at 4000 (already counted). |
| F179 | fix | coding_flow/__init__.py:49 — comment "Re-exported here for backward compatibility" on Draft/Candidate/…; who imports them from coding_flow? (VERIFY; if none, the re-export is dead.) |
| F180 | fix | applications/*.manifest.toml — line-number citations are stale: best_of_n_verified "py:116" (def at 118), code_review "fanout_review.py:91" (93), research_sweep "py:155" (157), daily "session/__init__.py:286" (628). |
| F181 | fix | code_review.manifest.toml:9 — `default_bundle = "reviewer"`: `load_bundle("reviewer")` -> BundleNotFoundError (looked in ~/.substrate/bundles/reviewer); the shipped bundle is `code_review`. Nothing in src/ reads `defa… |
| F182 | fix | applications/code_review.bundle methodology: verdict words "accept, block, or ask"; code_review/__init__.py:49,84,111 uses "approve \| request-changes \| block". Three verdict vocabularies for one review. |
| F183 | fix | applications/*.bundle — the one-shot topologies' prompts are hardcoded in their modules (code_review l.75, research_sweep l.95/117/140, best_of_n_verified l.74); no one-shot topology loads a bundle. Whether the daemon… |
| F184 | fix | manifests: model defaults "kimi-k2.6:cloud" ×9 and "claude" ×6 across five manifests; topology signatures default "llama3.2:1b" ×6. Three default-model conventions, no single default source. |
| F185 | fix | research_sweep.manifest.toml:14-18 — documents as `{label, text}` objects; `gather()` (research_sweep.py:62) produces `(path.name, text)`; the conversion lives in the daemon (VERIFY in server.py). |
| F186 | fix | pair_coding.manifest.toml:13 — `workspace` default "."; pair_coding_composite.py:77 `Path(".").resolve()` = the server process's cwd, then `mkdir`. Same class as the `~/.substrate/sandbox` literal-workspace finding. |
| F187 | fix | fanout_review.py has no manifest; code_review.manifest.toml wraps fanout_review under the name "code_review", while topologies/code_review is a different module. Name ↔ module mapping crosses (as with pair_coding). |
| F188 | fix | best_of_n_verified.manifest.toml:15-18 — "`verify_model` may alternatively point at a deterministic Check function name … the daemon's resolver decides". VERIFY the daemon supports a Check name. |
| F189 | fix | Two opposite failure policies for a model call, each documented as the rule: |
| F282 | closes with the finding it resolves | l.219 code_evolution: no user outside tests/test_code_evolution.py (best_of_n mentions it in prose only); assay/coding.py builds coding_flow, not code_evolution. The EA topology, its PLACEHOLDER cost and the unbuilt r… |
| F283 | closes with the finding it resolves | l.223 coding_flow re-export: imported only by tests/test_best_of_n.py:18 and tests/test_swebench_repair.py:17. Back-compat kept for two tests. |
| F285 | closes with the finding it resolves | l.168 best_of_n two copies: confirmed (coding_flow section). |
| F288 | closes with the finding it resolves | one-shot application bundles: `_APP_BUILDERS` (l.383-447) never read `default_bundle` or `[slots]`; the three one-shot app bundles are inert text. Confirmed. |
| F289 | closes with the finding it resolves | best_of_n_verified "verify_model may name a Check function": l.403-405 "The verify=Check \| Responder union collapses to Responder here; a deterministic-check variant is a future card". The manifest claim is false. |
| F290 | closes with the finding it resolves | research_sweep {label,text}: converted at l.424-427. OK. |

## checks

- A test per measured misread ("This does not PASS.", "I will not talk. STAY SILENT", "Disapprove") passes.
- Instruments and the pair_coding driver change their output when the model's reply changes.
- One best_of_n loop; coding_flow and code_evolution compose it.
- One truncation helper with one marker format.
- No `except Exception` turns an error into a recorded candidate.
- Hash-derived severity and outcomes are gone or labelled CI-only and never scored.

## result

(filled at close)
