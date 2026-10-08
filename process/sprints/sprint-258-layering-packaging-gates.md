# Sprint 258 — Kernel layering, packaging and gates

```yaml
---
id: 258
status: open
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

(filled at close)
