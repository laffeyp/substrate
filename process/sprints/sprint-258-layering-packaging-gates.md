# Sprint 258 — Kernel layering, packaging and gates

```yaml
---
id: 258
status: closed
closed_at: 2026-10-08
opened_at: 2026-10-08
pass_kind: remediation
roadmap: substrate-ui/process/planning/ROADMAP-2026-10-08-lens-audit-remediation.md
ledger_rows: 16
---
```

## why

The sdist ships 95 MB of run data; the import contract is a denylist cli.py evades; ruff runs none of the rules its 92 noqa comments name; the status gate misses single quotes and .ts (findings §2, §5, §9).

## sources

- *Twelve-Factor App*, V: "The build stage is a transform which converts a code repo into an executable bundle."
- import-linter docs: layers contracts.

## scope (ledger rows)

Each row closes as named; a row the sprint cannot close halts the sprint.

| id | close | finding |
|---|---|---|
| F001 | fix | substrate pyproject.toml — no [tool.hatch.build.targets.sdist]; sdist ships process/runs (18,336 files, 95 MB gz) since 1.0.1; 1.0.0 was 1.3 MB; PyPI default limit 100 MB. |
| F003 | fix | constants.py:7-8,33-37 — docstring/comment name process/signals/0.2.json and "v0.2 ratified"; VOCAB_VERSION = "0.3" (l.38). Comment and value disagree. |
| F004 | fix | __init__.py:13 — "locked vocabulary at process/signals/0.1.json"; current is 0.3. |
| F005 | fix | encoding.py:108,174,180,189 — SafeCanonical.reason values "unknown_kind" / "non_canonical_value" are bare strings (a closed set); check consumers. |
| F006 | fix | encoding.py:133,173,186 — `except Exception` with no noqa/rationale; elsewhere the project requires a BLE001 rationale. Check whether ruff selects BLE at all (if not, the BLE001 gate only polices comments). |
| F008 | fix | pyproject [tool.ruff] and substrate-ui/ruff.toml select no rules → ruff defaults (E4,E7,E9,F). BLE (blind except) and S (bandit) never run, yet kernel+UI carry 82 '# noqa: BLE001' and 10 '# noqa: S…' comments; the pre… |
| F042 | fix | api.py:116-131,260-278 — the kernel's public facade (F-API-1) now re-exports application objects: SessionRegistry and its errors (sprint 099), the daemon HTTP client and session/tool-loop kind names (sprint 107). The … |
| F061 | fix | pyproject import-linter contract (forbidden_modules) is a DENYLIST of kernel subpackages; cli.py imports substrate._daemon (8 function-level imports) and reaches substrate.topologies.*/templates via importlib.import_m… |
| F199 | fix | topologies -> assay (swebench_solver/assemble.py, grader.py) and assay -> topologies (assay/__init__.py, coding.py, swebench_container.py, swebench_host.py, swebench_matrix.py, swebench_suite.py): a package-level cycl… |
| F200 | fix | pyproject.toml:152-155 — the cli forbidden list omits substrate.adapters, topologies, assay, session_registry, bundles, _daemon, reference; the comment (l.145-150) calls the list "every internal surface EXCEPT substra… |
| F233 | fix | assay/__init__.py:11-12 — "imports … substrate.api and the model seam (substrate.reference), never kernel internals — like topologies/": the model seam is substrate.adapters; assay imports topologies (cycle noted above). |
| F234 | fix | Enum styles: `enum.Enum` (oracle.Verdict, records.Reproduction, RepairOutcome), `str, enum.Enum` (run.CellSource), `StrEnum` (constants.RunStatus, registry.SlotKind…), module-level str constants (conformance, suite ro… |
| F292 | fix | substrate/.githooks/pre-commit:50 — STATUS_RE matches double-quoted literals only. Missed: server.py:4235-4237 `m.status == 'parked' / 'interrupted' / 'ended'`; tests/test_session_registry_boot_scan_preserves_ended.py… |
| F293 | fix | substrate/.githooks/pre-commit:37 — mypy output to the fixed path `/tmp/substrate-mypy.log` (shared real /tmp; sprint 107: "gates write only to their own temp dirs"). |
| F428 | fix | Six UI test files import no UI code at all and test kernel modules only (substrate.session_registry, tool_loop.delegate): test_boot_scan_lazy_turn_index_094, test_delegate_session_ended_mid_delegate, test_delegate_via… |
| F429 | fix | clarification: substrate/tests references SessionRegistry in 10+ files (test_active_runtimes, test_turn_failure_state_101, …); the boot-scan, by-name and name-collision behaviors are tested only in the UI repo. |

## checks

- `uv build` sdist under 5 MB; `twine check` passes.
- An import-linter layers contract passes: kernel/record/projections import nothing above them.
- ruff selects BLE and S; `ruff check` passes; every noqa names an enabled rule.
- The status gate flags `'parked'` in a planted .py and .ts line, in both repos' hooks.
- The kernel-only UI tests run in substrate/tests.

## result

**Packaging (F001).** `[tool.hatch.build.targets.sdist]` lists the package, tests and project files. The 1.1.2 sdist is now 889 KB; it was 95 MB compressed, because process/runs (18,336 files) shipped inside it.

**Layering (F042, F051, F061, F199, F200, F233).** One import-linter "layers" contract now covers the whole package: cli > app > assay | conformance > topologies | reference > _daemon | adapters > api > bundles | projections | testing > kernel | naming | home > record > encoding | protocols | errors > constants | types. It passes. A planted `topologies → assay` import breaks it and names the line. To get there:
- **topologies ↔ assay.** The firewall moved to `topologies/swebench_solver/firewall.py`; it is a rule on the solver's inputs. The grade producer and the solve-and-grade composition moved into assay (`assay/swebench_grade_producer.py`, `assay/swebench_solve_and_grade.py`).
- **The registry.** `session_registry` moved from the package root to `topologies/session_registry.py` (64 importers updated).
- **`substrate.app`** is new: the application facade, holding the session registry names, the daemon client, the session and tool-loop kind names, the bundled-topology registry, the calibration scorers and the conformance suite. `api` is the kernel's facade again; it no longer depends on the applications above it.
- **api ↔ bundles.** `substrate_home` moved to the leaf module `home.py`, which api re-exports.
- **kernel ↔ projections (F025).** `LiveRecord` moved into `record/live.py` and now imports record.py's segment helpers instead of copying them (F030).
- **The CLI contract** is an allowlist of `{api, app}` over every top-level unit, where it was a denylist that missed seven. The CLI's AST test now counts `importlib.import_module("substrate…")` as an import. The CLI's reaches through importlib and the private `_daemon` are gone; `connect` and `tcp_host_port` are public on the daemon client.
- The kernel pre-commit hook runs `lint-imports`.

**Rules that run (F008, F006).**
- ruff selects BLE and S in both repos. S603/S607 are ignored with the reason stated: argv-list subprocess calls only.
- Each of the 28 blind excepts in kernel src, and the 3 in the UI server, either names the boundary it guards or became typed `except` clauses. The UI's create, turn and end handlers used `isinstance` dispatch inside `except Exception`; they now catch by type.
- Production asserts became explicit raises: 5 in the kernel, 6 in server.py. Among them is F014's runtime assert, fixed under `asyncio.timeout(...).expired()`, with a test that hangs or mislabels on the old code.
- `sha1` naming hashes say `usedforsecurity=False`; web_fetch refuses non-http(s) schemes.
- The coding gate runs in its own process group and kills the whole group on timeout (F176, with a test). Its one `shell=True` call says why.
- encoding.py's catches are narrowed or justified.

**Vocabulary (F003, F004, F005, F234).**
- The constants and package docstrings name vocabulary 0.3.
- `InvalidReason` (StrEnum) is the one set of invalid-emission reasons, used by encoding, the sequencer and conformance.
- Every enum in src is a StrEnum: Verdict, Decision, Status, RunPhase, CellSource, Reproduction and RepairOutcome were converted.

**Gates (F292, F293).**
- `scripts/check_status_literals.sh` is the one status-literal gate. It catches both quote styles in .py, .ts and .tsx; planted lines in each were caught.
- Both repos' hooks run it.
- The server's three single-quoted comparisons now use SessionStatus.
- reveal_component.ts is excluded by name until U112 replaces it.
- mypy logs to a `mktemp` file.

**Tests in the right repo (F428, F429).** The six kernel-only UI test files now live in substrate/tests (24 tests).

**Gates run.**

| Gate | Result |
|---|---|
| kernel ruff, format, mypy --strict (138 files), lint-imports (2 contracts) | clean / kept |
| UI suite | 214 (238 − 24 moved) |
| vm_smoke | 12/12 |
| electron_smoke | 0 defects |
| kernel suite | see BLACKBOARD |
