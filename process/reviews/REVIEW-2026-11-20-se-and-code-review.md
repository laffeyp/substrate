# REVIEW-2026-11-20 — software-engineering and code review of substrate

*Scope: `substrate/`, the Python runtime published as `substrate-kernel` 1.1.2. Reviewer read the full `sdd-kit-3/` kit, the R4 runbook (`RUNBOOK-2026-11-20-substrate-r4.md`), and `src/substrate/` (160 files, 13 subpackages, 40,264 lines) plus the parts of `scripts/` and `tests/` the findings touch. The gate stack passes on this machine (`ruff check`, `ruff format --check`, `mypy --strict`, `lint-imports`, `substrate conformance --no-perf`, `pytest`); every finding below is a fault those gates do not catch. A review is a record: nothing in the code was changed.*

---

## Orientation

Substrate is a mature SDD codebase, not a greenfield one. The vocabulary-as-contract discipline the kit demands is already visible in the source: roughly 35 `StrEnum` classes carry the closed sets (`RunStatus`, `RunFailureReason`, `InvalidReason`, `Verdict`, `SessionStatus`, `Reproduction`, `ProducerStatus`, and more), and several of them carry an inline "lens audit F0xx" note recording a prior pass that collapsed bare strings into one enum (`constants.py:45`, `:93`, `:105`). The dominant drift the review brief names — the same kind/status/verdict literal retyped at many call sites — is therefore mostly already paid down at the kernel core. What remains sits one layer out, in the assay and topology code, and in a different but adjacent form: typed `Struct`s that are flattened to untyped dicts on the bus and rebuilt by hand at every consumer. That is the largest finding.

The gate stack reproduced exactly: `ruff check` "All checks passed!", `mypy` "no issues found in 160 source files", `lint-imports` "2 kept, 0 broken", `substrate conformance --no-perf` "15 passed, 0 failed, 1 deferred, 1 skipped", `substrate --version` "1.1.2".

---

## Runbook findings

The R4 runbook is accurate on nearly every verifiable claim and candid about the staleness it does carry (it flags `CONTRIBUTING.md` naming `sdd-kit-2` and `0.2.json`, both correct flags). Two defects and one confirmation.

**R-1 (important). The Inventory row for the locked vocabulary is stale by one version.** Line 50 reads "Locked vocabulary | `process/signals/current.json` (the symlink/copy of `0.3.json`; `0.1`–`0.4` kept as audit trail)". The symlink actually targets `0.4.json` (`process/signals/current.json -> 0.4.json`), and the code agrees: `src/substrate/constants.py:38` sets `VOCAB_VERSION = "0.4"`. The same stale "0.3" appears in the session-startup block at line 227 by inheritance (it cites the archived sectioned decisions, which is correct, but the Inventory pointer above it is wrong). This is the one runbook cell that misstates the live contract version — the vocabulary is the contract, so the pointer to it should name the version the code emits into every record. Fix: a new round naming `0.4.json`, per the runbook's own "the fix for a wrong runbook is a new round, not an edit" (line 3).

**R-2 (minor). `substrate topology list` returns three names; the runbook's own day-to-day example runs a fourth.** Line 136 runs `substrate run --topology game_of_life_glider`, which works (verified: exit 0, record finalised). But `substrate topology list` returns only `session`, `swebench_repair`, `tool_loop` (verified), while `src/substrate/topologies/` holds ~24 topology packages, `game_of_life_glider` among them. The runbook glosses the command as "the bundled topology names" (line 146). The command under-reports; the gloss overstates what it returns. This is a CLI/documentation mismatch the runbook surfaces by contradicting itself. Fix direction belongs in the code (see C-7), not the runbook.

**R-3 (confirmation, not a defect).** Every gate exit code, the conformance tally "15 passed, 0 failed, 1 deferred, 1 skipped" with 17 checks, the `--version` 1.1.2, and `twine check` PASSED reproduced as written. The gate table (lines 83–90) is a faithful record.

---

## Code review — a taxonomy of error classes

### Class 1 — Primitive obsession: typed Structs flattened to `Any` dicts, rebuilt by hand (important)

This is the dominant structural fault and the real shape of the vocabulary-as-contract drift in this codebase. Producer inputs are typed `inp: Any` and read as dicts behind a `hasattr(inp, "get")` guard; the declared `Struct` is then reconstructed field by field, each field name a bare string literal that `mypy --strict` cannot see because `inp` is `Any`.

The idiom appears in **28 files** (every topology package plus the assay and reference pipelines) and the `hasattr(x, "get")` guard alone occurs **112 times**. The clearest site is the swebench solver:

- `topologies/swebench_solver/assemble.py:141` — `patches = list(inp.get("applied", [])) if hasattr(inp, "get") else []`
- `assemble.py:183-189` — rebuilds `AppliedPatch(round=int(a["round"]), slot=int(a["slot"]), model_patch=str(a["model_patch"]), creates_file=bool(a["creates_file"]))` from raw keys.
- `assemble.py:195-203` — rebuilds `TestResults(slot=int(r["slot"]), regression_passed=bool(r["regression_passed"]), reproduction=Reproduction(r["reproduction"]), summary=str(r["summary"]))` likewise.

`AppliedPatch`, `TestResults`, and `SelectedPatch` are declared as frozen `Struct`s in `topologies/swebench_solver/records.py`; here their field vocabulary (`round`, `slot`, `model_patch`, `creates_file`, `regression_passed`, `reproduction`, `summary`, `repro_code`) is retyped as string keys at each consumer. A rename of one field in the `Struct` would not break any of these reads; it would silently read `None`/`[]`. That is exactly the failure class the kit's "vocabulary is the contract" rule exists to prevent, moved from the tag layer to the payload-field layer.

Two secondary smells ride on the same idiom:
- The `hasattr(inp, "get")` guard with an `else []` / `else 0` fallback (`assemble.py:141`, `:142`, `:209`, `:234`) encodes an impossible branch: the kernel always resolves a Producer input to a mapping, so the `else` arm can only mask a real wiring bug as an empty result. A `KeyError`/typed decode would be louder and truer.
- The per-field coercions (`int(...)`, `str(...)`, `bool(...)`) re-assert at runtime a type the `Struct` already guarantees, because the `Struct` was discarded on the way to the bus.

Fix direction: decode the resolved input once into its declared `Struct` at the Producer boundary (`msgspec.convert(inp, type=SolverInput)` or a small typed `@classmethod from_input`), then read attributes. The field names live in one place — the `Struct` — and `mypy` guards every read. `records.py` already proves the types exist; the work is to stop round-tripping through `dict[str, Any]`.

### Class 2 — Retyped verdict and metric literals in the assay layer (important)

The one place the classic "same literal, many homes" drift survives.

- `assay/conformance.py:23-24` defines module-level `PASS = "pass"` and `FAIL = "fail"`. Those exact wire strings are already the values of `Verdict.PASS` / `Verdict.FAIL` in `assay/oracle.py:52-53`. Two independent definitions of the same closed vocabulary, one file apart.
- `assay/swebench.py:409` writes `"verdict": "fail"` as a bare literal; `swebench.py:529` writes `"verdict": "pass" if resolved else "fail"`. Neither routes through `Verdict`.
- `assay/swebench_grade_producer.py:87-88` maps `_V.PASS: "pass"`, `_V.FAIL: "fail"` — re-stringifying the enum it is holding, which is `Verdict.PASS.value` spelled by hand.
- The metric name `"resolved"` appears as a bare literal **22 times** across `assay/` and `topologies/swebench_solver/` with no named constant: `assay/cells.py:207` (default), `swebench_matrix.py:355`, `swebench_suite.py:357` and `:500` (defaults), and `swebench.py:559, 698, 722, 746, 827, 842`. `oracle.py:63-64` documents `metric` as a closed-ish set ("resolved", "exact_match", …) in prose, with no type behind it.

Why it is a fault: `Verdict` exists precisely so "pass"/"fail"/"no_verdict" have one home (the oracle.py docstring makes the case — the 2026-08-10 postmortem of 517 silent fails). Writing the string again defeats that; a typo (`"faill"`) would pass every gate and corrupt the grade silently. The `"resolved"` metric is the same latent bug with no enum at all.

Fix direction: use `Verdict.PASS.value` / `.FAIL.value` at the four bare-literal sites and delete the `conformance.py` duplicate constants in favour of importing `Verdict`; introduce a `Metric` `StrEnum` (or at minimum `METRIC_RESOLVED`) and reference it at the 22 sites.

### Class 3 — Stringly-typed message role (minor)

Chat message `role` is a bare string. `adapters/models.py:231-232` builds `{"role": "system", ...}` and `{"role": "user", ...}`; `adapters/harness_streams.py:137-141` branches on `kind == "assistant"` and `kind in ("assistant", "user")`. The set {`system`, `user`, `assistant`, `tool`} is closed (it is the model-message vocabulary), but no `Role`/`MessageRole` enum names it. It is a boundary with an external wire format, which lowers the severity, but the branch in `harness_streams.py` is substrate's own logic keying on the literal, not a pass-through.

Fix direction: a small `MessageRole(StrEnum)` used at the construction and comparison sites; the `.value` is what crosses the wire, so the external contract is unchanged.

### Class 4 — One god-function and three god-modules (important for the function, minor for the files)

`session_topology` spans **775 lines** (`topologies/session/__init__.py:1042-1817`) and nests `topo` (527 lines) and `_model_factory` (293) inside it. It is not pure declarative wiring: the 775-line span holds 66 `def`/`if`/`for`/`elif`/`while` keywords, so conditional logic and closure definitions are interleaved in one scope. The kit's hard rule 6 (one concept, small scope) and Ousterhout's deep-module guidance both argue against it; the practical cost is that no reader holds the whole function, and a change to one producer-factory sits inside 700 lines of unrelated wiring.

The three largest modules — `cli.py` (1914), `topologies/session/__init__.py` (1892), `topologies/session_registry.py` (1891) — are large but cohesive (a CLI command surface, a topology assembly, a registry); size alone is not the fault. `coding_problem_bank` (673 lines, `assay/coding_problems.py:37`) is a data bank, which is acceptable as a single literal. Flag `session_topology` specifically: extract the model/harness/prompt factories into named module-level functions so the topology body reads as assembly, not implementation.

### Class 5 — Magic sentinels and scattered truncation constants (minor)

- The `"?"` unknown-value sentinel is a default in **26** `.get(..., "?")` sites (`cli.py:1044`, `cli.py:155`, `projections/narrate.py:120`, `adapters/harness_streams.py:149`, `topologies/session/transcript.py:252` and others). It is a display fallback for a missing `kind`/`tool`/`instance_id`; a named `UNKNOWN = "?"` constant would make the intent one thing instead of 26 identical guesses.
- String-truncation caps are magic numbers chosen per site: `[:160]`, `[:300]`, `[:400]`, `[:4096]`, `[:120]`, `[:40]` (e.g. `assemble.py` summary at `[:160]`, `adapters/models.py` at `[:300]`/`[:400]`). Each is roughly unique, so this is not a retyped-constant drift, but the numbers carry no name for what they bound (a log line, a prompt echo, an error summary). Minor; name them where two sites share a purpose.

### Class 6 — Misleading docstring: `constants.py` names the wrong vocabulary file (minor)

`constants.py:7-8`, the module docstring, says the locked vocabulary is `process/signals/0.3.json` ("…the locked vocabulary process/signals/0.3.json (additive successor to 0.2 and 0.1…)"). The same file sets `VOCAB_VERSION = "0.4"` at line 38 and the comment at line 33 says `0.4.json`. `current.json` targets `0.4.json`. The docstring is stale by one version, in the file that defines the version — the same slip as runbook finding R-1, in code. Fix: name `0.4.json` in the docstring, or state the version by reference to `VOCAB_VERSION` so the two cannot diverge again.

### Class 7 — Boolean parameters, mostly acknowledged (minor)

25 functions take a `: bool` parameter. The majority are `click` command handlers (`cli.py:478 narrate(... lifecycle, summary)`, `cli.py:689 conformance(no_perf)`, `cli.py:1453 daemon(foreground)`, `cli.py:1556 session_rm(... force)`), which `click` always passes by keyword, so they are not call-site traps. The genuine positional traps are internal and few: `topologies/session/mcp_channel.py:103 deliver(session_id, call_id, ok: bool, output)` invites `deliver(sid, cid, True, out)`, and `topologies/recursive_decomposition/__init__.py:68 _solver_factory(max_depth, fanout, responder, runaway: bool)`. Low volume; make the two internal ones keyword-only.

### What the gates already hold (not findings, stated so the review is honest about scope)

Broad exception handling is disciplined: 62 `except Exception` sites, 53 carry an explicit `# noqa: BLE001` at a read-a-possibly-torn-record boundary, and the three un-annotated ones (`kernel/runtime.py:575`, `:1066`, `cli.py:126`) each immediately re-raise a typed `RegistrationError`/`ClickException` with `describe_error(exc)` and `from exc`. No bare `except:` exists. `type: ignore` appears 18 times, modest for 40k lines. The reserved-namespace guard, the frozen-Struct input immutability, and the `Verdict`/`RunStatus` enums are the kit's discipline applied correctly.

---

## Highest-leverage fixes

1. **Decode Producer inputs into their declared `Struct` at the boundary** (Class 1). This is the one change that moves the payload-field vocabulary back under `mypy`'s eye across 28 files; it removes the 112 `hasattr(... "get")` guards, the silent `else []`/`else 0` fallbacks, and the hand coercions in one motion. Start with `swebench_solver/assemble.py`, where the rebuilt types (`AppliedPatch`, `TestResults`) already exist in `records.py`.
2. **Collapse the verdict and metric literals onto `Verdict` and a new `Metric` enum** (Class 2): delete `conformance.py:23-24`, route `swebench.py:409/529` through `Verdict`, and name the 22 `"resolved"` sites. Small, self-contained, closes a silent-typo class on the grade path.
3. **Correct the one stale vocabulary pointer in two places** (R-1 + Class 6): a new runbook round naming `0.4.json`, and the `constants.py` docstring. The contract version should read the same in the runbook, the docstring, and `VOCAB_VERSION`.
4. **Extract `session_topology`'s nested factories to module scope** (Class 4) so the 775-line body reads as assembly.

---

*REVIEW-2026-11-20-se-and-code-review. Seven error classes, two important (Class 1 primitive-obsession across 28 files; Class 2 retyped verdict/metric literals), the rest minor. Two runbook defects (R-1 stale vocabulary version, important; R-2 `topology list` under-reports, minor). The gate stack and the kernel-core vocabulary discipline are sound; the drift lives in the assay and topology layers, in the payload-field dict-rebuild pattern.*
