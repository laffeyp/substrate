# Sprint 256 — SWE-bench solver and oracles

```yaml
---
id: 256
status: open
opened_at: 2026-10-08
pass_kind: remediation
roadmap: substrate-ui/process/planning/ROADMAP-2026-10-08-lens-audit-remediation.md
ledger_rows: 54
---
```

## why

Mechanism failures grade FAIL; a missing report grades FAIL; typed errors are never raised; the gate's timed-out grandchildren live on (probe); the error band cites the wrong authors and split (findings §1, §6, §10).

## sources

- Wang, Pradel and Liu, arXiv 2503.15223: 7.8% on SWE-bench Verified.
- OpenAI, "Introducing SWE-bench Verified": curated by OpenAI with the SWE-bench authors.

## scope (ledger rows)

Each row closes as named; a row the sprint cannot close halts the sprint.

| id | close | finding |
|---|---|---|
| F190 | fix | localize_elements.py:106-109 — docstring: "Death-resilience … the LLM call is wrapped; if it dies, emit an empty SuspectFiles…". Code l.131: "no exception swallow". Docstring describes the removed behaviour. |
| F191 | fix | localize_elements.py:112-128 — EditLocations over BLOB_THRESHOLD (16 KiB) reaches the view as `{"$blob": …, "bytes": N}`; the drafter input builder (assemble.py ~557-573) read `["targets"]` -> KeyError -> every drafte… |
| F192 | fix | records.py:7-9 and swebench_solver/__init__.py:7 — "REUSED from coding_flow"; they are imported from best_of_n.contracts (records.py:22). |
| F193 | fix | records.py:161-176 — `GradeResult.verdict: str` with three wire strings, `reason: str` closed set; grader.py:86-90 maps `assay.oracle.Verdict` -> string via a dict. Enum exists, record field is str (same class as regi… |
| F194 | fix | applier.py:285 — `git add -A` with check=False and output discarded; if it fails, `git diff --cached` is empty and l.294-295 reports "no-op: candidate produced an empty diff" — an infrastructure failure graded as a mo… |
| F195 | fix | applier.py:252-261,275-281 — every touched file is decoded `errors="replace"` and re-encoded UTF-8 whole. A non-UTF-8 (latin-1) source file: every undecodable byte becomes U+FFFD (EF BF BD) on write, so the diff touch… |
| F196 | fix | applier.py:256,258 — CRLF detected from the first 4096 bytes only; a file with mixed endings is normalised to all-CRLF or all-LF on write, again diffing unedited lines. |
| F197 | fix | applier.py:10-11,140-146 — "leading-whitespace-flexible" tier 2 compares `.strip()` (leading AND trailing). |
| F198 | fix | repair.py:98-103 — `git clone --local` per candidate, `subprocess.run` with no timeout; apply_candidate's two git calls also lack timeouts. |
| F201 | fix | grader.py:3-17 — module docstring narrates sprint plans ("Sprint 196 lands the live consumer"); VERIFY whether 196 landed (assemble.py). |
| F202 | delete | The retired heavy topology `swebench_solver_topology_with_test_selection` (assemble.py:506-786) and its six satellite modules (select, select_exec, select_docker, select_regression, reproduction, repro_base_validate: … |
| F203 | delete | _deprecated/README.md:29-32 — "`_build_solver_arm_from_payload(..., include_test_selection=True)` also keeps the escape hatch open"; assemble.py:549 and swebench_matrix.py:258 say sprint 199b retired that opt-in. READ… |
| F204 | delete | reproduction.py:54-89 — `combine_repro_scripts` runs each script through `exec(compile(...), {})`; with an empty globals dict `__name__` resolves to builtins' "builtins", so a script with `if __name__ == "__main__":` … |
| F205 | delete | reproduction.py:81,87-88 — `indented` computed then `del indented`, comment "keep `indented` referenced so future indentation-style variant doesn't dead-code it". Dead code kept to satisfy a linter. |
| F206 | delete | reproduction.py:8-9,103-106 ("If ALL K model calls fail, emits an EMPTY ReproductionTest … Partial failures drop the raising samples") vs l.111,116: halt-on-error, `asyncio.gather` without return_exceptions propagates… |
| F207 | delete | select_docker.py:204-232 — on `subprocess.TimeoutExpired` the code kills the `docker` client process; nothing stops the container (no `--name`, no `docker kill`/`rm -f`). `--rm` removes it only when it exits. The 900 … |
| F208 | fix | select_docker.py:138-152, assay/swebench.py:454, assay/swebench_suite.py:112 — three copies of a stderr-JSON event emitter ({t, kind, boundary, payload}); "Kind names match vocab v0.3 § G.2". Typed lifecycle events wr… |
| F209 | delete | select_docker.py:73-75 — `cmd_takes_paths` "Legacy alias — kept for the one caller that still checks the boolean": the only callers are its own two tests (tests/test_swebench_select_docker.py:43,103). |
| F210 | delete | "python /sol/repro.py" retyped at select_exec.py:154 and repro_base_validate.py:88; "/sol" mount at select_docker.py:213. |
| F211 | fix | _build_edit_context (assemble.py:86-117) — per-file 15_000 / total 60_000 caps: truncation site eleven. |
| F212 | fix | assemble.py:348 — passes `termination=quiescence_with_watchdog(watchdog_seconds * 10)` to best_of_n_correction as a "placeholder termination that never fires"; kernel/topology.py:368 `self._reg.termination = policy` —… |
| F213 | fix | assemble.py:272,425 — `firewall_instance: Any`; assemble.py:417 `report_dir: Any`. |
| F214 | fix | oracle.py:72-76, swebench.py:46-47 `_LITE_GRADER_ERROR_BAND = 0.078` — cites "Xia & Chen (2025) … arxiv 2503.15223 … ~0.078 on SWE-bench Lite" and "SWE-bench Verified is ~0.02". arXiv 2503.15223 (fetched): authors You… |
| F236 | fix | swebench.py:883,915-920 — `SwebenchLogProjectionOracle._ESSENTIAL_PRODUCER_KINDS = {"solve", "grader"}`. "solve" exists only in swebench_matrix's backend topologies (l.85,133). The oracle is also the paired oracle for… |
| F237 | fix | swebench.py:1221-1228 — `batch_grade_from_records` maps a missing report.json to `resolved=False` (FAIL). oracle.py:47-50: "Silence at any grader layer becomes a typed NO_VERDICT … The old shape rolled harness silence… |
| F238 | fix | swebench.py:1081-1096 — SwebenchExtractOnlyOracle's deferred placeholder carries `reason=REASON_HARNESS_ERROR` ("names the deferred state honestly"). A deferred cell and a harness exception share one reason; if the ba… |
| F239 | fix | swebench.py:92-118 — `classify_reason_string` substring rules: "ValueError: invalid digit" -> git_error; "legitimate request rejected" -> git_error; "ConnectionError: generate unlimited" -> rate_limited. Docstring ack… |
| F240 | fix | swebench.py:146-151 — `timeout_for_instance` takes `rest.split("-")[0]`: scikit-learn__scikit-learn-25570 -> key "scikit-learn/scikit" -> miss -> default. Returns 3600 only because the default equals the table's 3600 … |
| F241 | fix | swebench.py:390,1199 — `contextlib.chdir(rdir)` in library code (run_swebench, batch_grade_from_records) mutates process-global cwd; `read_resolved` (l.304-309) and `run_swebench` (l.412) also search `Path.cwd()`. Und… |
| F242 | delete | swebench.py:645-663 `swebench_oracle`: zero callers. swebench_suite.py:387-427 `_repair_and_grade_topology_from_payload`: zero callers, and passes `instance_id=run_id` (l.417) — a run_id ("{arm}-{case}") where the har… |
| F243 | fix | Four SWE-bench oracle variants: swebench_oracle (dead), SwebenchRecordOracle (+ legacy factory swebench_record_oracle), SwebenchLogProjectionOracle, SwebenchExtractOnlyOracle — the Record and ExtractOnly variants dupl… |
| F244 | fix | Verdict wire mapping written three times: grader.py:86-90 (enum->str), swebench.py:958 (str->enum), cells.py:56-60 (`Verdict(str)`); plus `"pass" if resolved else "fail"` literals at swebench.py:514,633. |
| F245 | fix | swebench_suite.py:244-273 — `prepare_swebench_case` (default `skip_base_pytest=False`) runs the base pytest in Docker (docstring: 15-40 min per instance on astropy/django/sympy) and fills `regression_files`, `exclude`… |
| F246 | fix | swebench_suite.py:210-214 — every prepared case `mkdtemp(prefix="assay-swe-")` (a full checkout); nothing removes it (grep: no rmtree for base_checkout in assay/ or the confirmatory runner). None present at audit time… |
| F247 | fix | swebench_suite.py:99 — `_MOTHER_CACHE_ROOT = Path.home() / ".cache" / "substrate" / "swe-mothers"` computed at import, outside `substrate_home()`; tests and SUBSTRATE_HOME runs share the real cache (1.7 GB on this mac… |
| F248 | fix | swebench_suite.py:138-147 — the unlocked `mother.exists()` fast path returns the mother while a peer holds the lock mid-`git clone --bare` (git creates the target dir at start); a second worker can clone --local from … |
| F249 | fix | swebench_suite.py:165-175,211-212 — `git clone` (network, ~700 MB astropy) and `git checkout` with no timeout. |
| F250 | fix | swebench_matrix.py:39-55 — `SWEBENCH_OLLAMA_TIER` read from env inside each Arm.build; an unknown value raises `SystemExit` from library code. |
| F251 | fix | swebench_suite.py:240-241 — "which Princeton/OpenAI/Anthropic curated OUT of SWE-bench Verified". SWE-bench Verified was released by OpenAI with the SWE-bench authors; Anthropic is not a curator (VERIFY with source if… |
| F252 | fix | swebench_matrix.py:279, swebench_suite.py:303 — `_ = repro_k` "source-compat": parameters accepted and ignored in two places. |
| F253 | fix | swebench_matrix.py:12-14 — backend arms emit no ModelUsage: tokens and model_calls are 0 for those arms in every report; `resolve_per_call` is None; compute comparisons across a matrix mixing these arms with metered a… |
| F254 | fix | (re swebench_suite.py:240-241) SWE-bench Verified: OpenAI with the SWE-bench authors; 93 Python developers reviewed 1,699 samples -> 500, screening for underspecified issues and unfair/incorrect tests (OpenAI "Introdu… |
| F255 | fix | swebench_errors.py — DockerDaemonError, ContainerCrashed, GitOperationFailed, HarnessTimeout, HarnessError, SwebenchRunnerError: zero `raise` sites in src/ or scripts/ (grep). scripts/assay_swebench_confirmatory.py:13… |
| F256 | fix | swebench_agent.py:79-87 `_apply_edit`: exact `search in content`, `content.replace(search, replace, 1)` (first occurrence, no uniqueness check, no whitespace tier, no CRLF handling). topologies/swebench_solver/applier… |
| F257 | fix | swebench_container.py:118-133 — `write_file` runs `docker cp` with `check=False` and ignores the result; `_apply_edit` returns "applied" either way. swebench_container.py:115-116 `read_file` returns `exec()` output, w… |
| F258 | fix | swebench_agent.py:111 — the agent's file list is `git ls-files \| head -400`; astropy/django/sympy have thousands of files, so most files are invisible to the agent's localization (no marker that the list was cut). |
| F259 | fix | swebench_container.py:115,124 — `cat {relpath}`, `mkdir -p $(dirname {relpath})` interpolate a model-supplied path into a shell (within a `--network none` container whose agent already has a bash action — no added cap… |
| F260 | fix | Three clone functions: swebench_suite._clone_at (via mother cache), swebench_workspace.host_clone (direct from GitHub each time), repair.py's `git clone --local`. solve_on_host clones a full repo from GitHub per call … |
| F261 | fix | swebench_host.py:21-22, swebench_agent.py:35-36 — two local `_Responder` Protocols duplicating `substrate.protocols.Responder`. |
| F262 | fix | swebench_host.py:65-68 — the whole file is read into the prompt with no cap (assemble.py:68-81 records the 1.4 MB prompt -> 400 failure this caused elsewhere); `apply_candidate` result ignored (l.69-71), so an apply e… |
| F263 | fix | firewall failures raise `ValueError` in swebench_host.py:59, swebench_agent.py:104 and `FirewallViolation` elsewhere (swebench_matrix.py:271, assemble.py:303). |
| F264 | fix | swebench_agent.py:137 — "unparseable (no ACTON:)" typo in a string written to the agent's prompt log. |
| F286 | closes with the finding it resolves | l.251 grader.py sprint 196: landed (assemble.swebench_solve_and_grade_topology, swebench_suite.swebench_solve_and_grade_arm); the grader.py docstring still narrates it as future. |
| F287 | closes with the finding it resolves | l.310 Verified curators: resolved above (OpenAI + SWE-bench authors). |

## checks

- A failed localizer or drafter grades NO_VERDICT; a missing report grades NO_VERDICT.
- Typed swebench errors are raised at their sources; classify_reason_string is gone or a last resort with tests.
- The gate kills its process group on timeout (probe becomes a test); the docker container is stopped on timeout.
- Citations match the paper; the Lite band has a source or is removed.
- The heavy topology, its satellites and the two scripts are deleted; nothing imports them.
- applier keeps undecodable bytes and mixed line endings intact.

## result

(filled at close)
