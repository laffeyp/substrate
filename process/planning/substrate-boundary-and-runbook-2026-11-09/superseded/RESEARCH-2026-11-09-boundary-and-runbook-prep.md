# The substrate/substrate-ui boundary, and what a substrate runbook needs

*2026-11-09. Research for writing a runbook for `substrate/`. Covers three things: how the two repos relate, whether the boundary is right under standard practice, and the state of substrate on its own terms — what exists, what the runbook has to account for.*

---

## How the two repos relate today

Substrate is a Python library and CLI, published to PyPI as `substrate-kernel` (version 1.1.2). It declares nine primitives (Producer, Event, Bus, View, Predicate, Trigger, Route, TerminationPolicy, Topology), runs them concurrently through one append-only log, and writes every run to a replayable record on disk. It has no UI. Its public surface is `substrate.api`, enforced by an import-linter contract in `pyproject.toml`. The code lives at `src/substrate/`, 145 Python files across 13 subpackages.

Substrate-ui is a desktop application (Electron + Python server) that hosts a specific set of substrate topologies — principally the session topology, which is an interactive model session with tools, compaction, roles, and language measurement. It imports substrate as an editable install (`../substrate`), calls its public API, and renders a window over the results. The server is `server.py`. The front end is `web/`. The Electron shell is `electron/`. The app is packaged with electron-builder into `Substrate.app`.

The dependency flows one direction: substrate-ui depends on substrate. Substrate has no knowledge of substrate-ui. Two coupling points exist:

1. The session topology lives in substrate (`src/substrate/topologies/session/`, 18 files, ~3,500 lines), not in substrate-ui. Substrate-ui renders it and drives it but does not define it.
2. Substrate-ui generates TypeScript files from substrate's vocabulary and controls. `web/vm/signals/versions/current.json` tracks the substrate-ui SDD vocabulary (v0.6 as of 2026-08-25). `web/vm/controls.gen.ts` reads the Length and Tone positions from substrate's `session/vocabulary.py`. The generation scripts (`scripts/gen_kinds.py`, `tools/sync-substrate-vocab.ts`) run at build time.

The working agreements name the boundary explicitly. Substrate's `process/WORKING_AGREEMENT.md` says "Out of scope for v1.0: a UI in-repo (substrate-ui is the separate companion)." Substrate-ui's `RUNBOOK-2026-10-29-project-r6.md` says "Depends on: `../substrate/` (no runbook of its own yet)."

---

## The boundary under Ousterhout

John Ousterhout's *A Philosophy of Software Design* (2018, 2nd ed. 2021) gives three principles that bear on this split.

**Deep modules.** The best decomposition produces modules with simple interfaces and large functionality behind them. A shallow module has a wide interface relative to the work it does. Substrate's public API (`substrate.api`) re-exports 73 names from 13 internal subpackages. A consumer — substrate-ui or anyone else — writes a topology function that calls `TopologyBuilder` methods, then calls `Runtime.run()`. The consumer sees nine concepts and one entry point. The kernel, the record format, the encoding pipeline, the writer loop, the trigger machinery, and the replay engine are all hidden. By the deep-module measure, this is a clean cut.

**Information hiding and leakage.** Ousterhout (following Parnas 1972) says that a module encapsulates a design decision, and leakage occurs when one decision is reflected in multiple modules. The substrate/substrate-ui split hides the kernel's design decisions (the six-step append cycle, the CRC framing, the RFC 8785 encoding, the trigger firing policies) entirely within substrate. Substrate-ui has no code that touches these internals. Two points where information leaks across the boundary:

- The session topology's event kinds. Substrate-ui's TypeScript code knows the names of session-topology events (`UserMessage`, `Returned`, `PromptComposed`, `SessionEnded`, etc.) because the front end renders them. This is structural — the UI must know what it displays. The leak is contained by code generation: substrate defines the kinds, and substrate-ui reads them through generated files rather than duplicating string literals.
- The record's on-disk format. Substrate-ui reads session records (`~/.substrate/sessions/<id>/record/events-*.jsonl`) to render transcripts. It reads them through substrate's API (`read_record`, `narrate`), not by parsing the JSONL directly. The file layout is hidden behind the API call.

Neither of these is the kind of leakage Ousterhout warns against, where two modules independently encode the same decision and can drift. The code generation keeps the vocabulary in one place (substrate), and the API keeps the record format in one place (substrate).

**General-purpose modules are deeper.** Chapter 6 argues that general-purpose interfaces, designed to serve many situations, tend to be simpler than special-purpose ones tuned to one caller. Substrate was built as a general-purpose runtime — it ships 15 topologies besides the session (game of life, prisoners' dilemma, code review, pair coding, debate, research sweep, SWE-bench solver, etc.). The session topology is one consumer among many. The nine-primitive vocabulary was locked before the UI existed. This is the right order: the general-purpose layer came first, and the special-purpose application (substrate-ui) composed on top of it.

**Verdict.** The boundary is correct. Substrate is the deep, general-purpose module. Substrate-ui is the special-purpose application that calls its interface. The dependency flows one way. Information leakage is handled by code generation and API calls. Ousterhout's Chapter 9 section "Separate general-purpose and special-purpose code" prescribes exactly this shape: push the general-purpose code down, push the special-purpose code up, do not mix them.

---

## The state of substrate on its own terms

### What exists

The repository holds 145 source files under `src/substrate/`, organized into 13 subpackages with a layered import contract enforced by import-linter. The layer order, top to bottom: `cli` → `app` → `assay | conformance` → `topologies | reference` → `_daemon | adapters` → `api` → `bundles | projections | testing` → `kernel | naming | home` → `record` → `encoding | protocols | errors` → `constants | types | language`.

Tests: 186 test files under `tests/`. The default gate is `scripts/ci_local.sh`, which runs ruff, mypy strict, pytest, import-linter, and the 17 conformance checks across Python 3.12, 3.13, and 3.14 in isolated environments. `scripts/ci_local_ubuntu.sh` covers Linux via Docker. GitHub Actions is unavailable (minutes exhausted); the local matrix is the bar.

Docs: `docs/` has a structured reading order — tutorial, demo, adding-a-topology for learners; api.md, replay.md, schema-evolution.md for reference; four canonical specs (kernel v15, product draft 7, technical draft 5, design draft 1) plus three amendments. Walkthroughs with committed run records sit at `docs/walkthroughs/`.

Process: `process/BLACKBOARD.md` (the decision log, 1,344+ entries), `process/WORKING_AGREEMENT.md`, `process/KIT_DIARY.md`, sprint cards at `process/sprints/` (340+ cards, latest is sprint-340), planning documents at `process/planning/` (70+ research, roadmap, design, postmortem, and review files), reviews at `process/reviews/` (20+ review files).

Release: version 1.1.2 on PyPI. The `substrate` CLI installs via `python3 -m substrate install`. The install links the command into `~/.local/bin` and patches the shell startup file if needed.

State directory: `~/.substrate/` holds sessions, bundles, config, the daemon socket and pidfile.

Scripts: 45 files under `scripts/`, covering CI, code generation, assay runners, benchmarking, language analysis, and the SWE-bench evaluation pipeline.

### What substrate-ui's runbook covers that substrate's does not

Substrate-ui has a 318-line runbook at its repo root (`RUNBOOK-2026-10-29-project-r6.md`). It has been run end to end (2026-10-27, 21:16–21:24), the known failures are dated (checked 2026-10-29), and every path in it has been verified against the tree. Substrate has no equivalent.

For a substrate runbook, the sections the runbook guide (`docs/runbook-guide-2026-10-30/GUIDE-2026-11-04-runbook-r2.md`) prescribes are:

1. **Orientation.** The method (`CLAUDE.md` → `../sdd-kit-3/AGENTS.md`), the records (`process/BLACKBOARD.md`, `process/WORKING_AGREEMENT.md`, `process/KIT_DIARY.md`), the current direction (`process/planning/` and its open items), the code entry points (`src/substrate/cli.py`, `src/substrate/kernel/runtime.py`, `src/substrate/api.py`), the build system (`pyproject.toml`, `scripts/ci_local.sh`), the sibling repo (`../substrate-ui/`, which has a runbook).

2. **Inventory.** The surfaces the commands touch: the source tree at `src/substrate/`, tests at `tests/`, scripts at `scripts/`, the installed package (`substrate-kernel` on PyPI), the CLI command (`substrate`), the state directory (`~/.substrate/`), docs at `docs/`, process records at `process/`, the locked vocabulary at `process/signals/current.json`.

3. **Prerequisites.** Python 3.12+ (CI tests 3.12, 3.13, 3.14). `uv` on PATH. Ollama running locally for real-model tests. Docker for `ci_local_ubuntu.sh` and SWE-bench evaluation. Optional: `swebench` and `datasets` extras for the SWE-bench pipeline.

4. **Pick a chapter.** Routes from "does the code pass its gates" to "run the conformance suite" to "release to PyPI" to "run a topology" to "run the SWE-bench evaluation."

5. **Build and test — local.** The gate commands in order: `uv run ruff check`, `uv run ruff format --check`, `uv run mypy --strict`, `uv run pytest`, `uv run lint-imports`, `uv run substrate conformance --no-perf`. Or all at once: `scripts/ci_local.sh`. Each command's expected exit code. The perf floor gate separately: `SUBSTRATE_PERF_GATE=1 uv run pytest tests/test_perf.py`.

6. **Build and release — PyPI.** `uv build`, `twine check`, `twine upload`. Version bump in `pyproject.toml`. Tag and push. The sdist include-list in `pyproject.toml` that keeps `process/runs/` out of the 100 MB limit.

7. **Day-to-day development.** `uv venv --python 3.12`, `uv pip install -e ".[dev]"`. Running a topology: `uv run substrate run <path_to_topology>`. Running a demo: `uv run substrate demo replay code_review`. The real-model tests need Ollama with specific models.

8. **Tests only.** The six commands from CONTRIBUTING.md. The `--no-perf` flag. The `-m realmodel` and `-m swebench_harness` markers. The 30-second per-test timeout.

9. **Troubleshooting.** The known failures and their dates. The GitHub Actions minutes-exhausted state. The ruff pin (`0.15.17`) and why it exists (format drift). The `python_classes = []` setting and why (domain records named `Test*` confused pytest). The mypy strict gate and the `swebench.*` ignore override.

10. **Rollback.** For a PyPI release: yank the version and ship a higher one. For a local install: `pip install substrate-kernel==<prior>`.

11. **Escalation.** The closed list from `AGENTS.md` "Questions only the user can answer." The `spec_ambiguity` and `conformance_unmapped` project-specific halts from `WORKING_AGREEMENT.md`.

12. **Conventions.** The eight-word vocabulary. The tone canon (structured output, sequence numbers, no anthropomorphic synonyms, no emoji). Append-only logs. No in-place edits to planning files. No deletions.

13. **References.** The four specs, the four amendments, `CONTRIBUTING.md`, `scripts/ci_local.sh`, `pyproject.toml`.

14. **Session startup.** The reading list from `AGENTS.md` "What you read at session start," adapted for substrate's paths: `CLAUDE.md` → `../sdd-kit-3/AGENTS.md` (the whole kit on first session), `process/WORKING_AGREEMENT.md`, `process/BLACKBOARD.md` (grep decisions + tail), `process/KIT_DIARY.md` (tail), the current sprint card.

### What needs to happen before the runbook can be written

The runbook guide's first rule is "every command has been run." The commands for substrate have been run many times (344 sprints, CI runs across three Python versions, 1.1.2 released to PyPI), but no single document gathers them with their expected exit codes and last-run dates. The runbook is the document that does that.

The runbook guide's third rule is "dates on everything that ages." The known failures need a dated check. The last end-to-end CI run needs a date and a log path.

Substrate's `process/planning/` folder has 70+ files but no planning index (`README.md` with status per piece of work). Substrate-ui has one at `process/planning/README.md`. The runbook's Orientation section needs to point at this index, so one must exist before the runbook can name it. The alternative is to note the absence and let the runbook's Orientation section describe what's open by reading the BLACKBOARD.

Substrate's `CONTRIBUTING.md` covers the gates but predates the daily-driver arc (it still says the SDD kit is `../sdd-kit-2/`, not `sdd-kit-3`). The runbook will capture the current state regardless, but `CONTRIBUTING.md` is stale.

---

## Sources

- Ousterhout, John. *A Philosophy of Software Design.* Yaknyam Press, 2018; 2nd ed. 2021. Chapters 4 (deep modules), 5 (information hiding), 6 (general-purpose modules), 9 (separate general-purpose and special-purpose). Verified against secondary sources; the book text was not consulted directly.
  - [Book summary, freshman.tech](https://freshman.tech/philosophy-of-software-design-summary)
  - [Review, Pragmatic Engineer](https://blog.pragmaticengineer.com/a-philosophy-of-software-design-review/)
  - [Summary, DEV Community (Carsten Behrens)](https://dev.to/carstenbehrens/summary-of-a-philosophy-of-software-design-by-john-ousterhout-c52)
  - [Reading notes, depthofcode](https://depthofcode.pages.dev/posts/book-philosophy-software-design)
- Parnas, David L. "On the criteria to be used in decomposing systems into modules." *Communications of the ACM* 15(12), 1972. Ousterhout cites this as the origin of information hiding.
- The runbook guide: `docs/runbook-guide-2026-10-30/GUIDE-2026-11-04-runbook-r2.md`.
- The file organization guide: `docs/document-organization-guide-2026-10-30/GUIDE-2026-10-30-reorganizing-files-and-folders-r3.md`.
- Substrate-ui's runbook: `substrate-ui/RUNBOOK-2026-10-29-project-r6.md`.
- The SDD kit: `sdd-kit-3/AGENTS.md` and `sdd-kit-3/README.md`.
