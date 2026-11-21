# RUNBOOK — substrate

*2026-11-20, round 3. Supersedes rounds 1–2 (in `process/planning/substrate-boundary-and-runbook-2026-11-09/superseded/`). Scope: `substrate/`, the Python runtime and CLI published to PyPI as `substrate-kernel`. The companion application is the sibling repository `../substrate-ui/`, which has its own runbook (`RUNBOOK-2026-11-12-project-r10.md`). This runbook does not override the working agreement or the method; where they differ, they win and this file is wrong. The fix for a wrong or stale runbook is a new round, not an edit.*

| Owner | Peter Laffey |
| --- | --- |
| Last updated | 2026-11-20 |
| Last run end to end | 2026-11-20: `ruff check`, `ruff format --check`, `mypy --strict`, `lint-imports` and `substrate conformance --no-perf` each exited 0 on this machine; the full `uv run pytest` was run the same day (result under "Known failures on the current tree"). The three-version isolated matrix `scripts/ci_local.sh` was not re-run this round. |
| Scope | `substrate/` only |
| Depends on | `../substrate-ui/` consumes this library (runbook `RUNBOOK-2026-11-12-project-r10.md`); the method is `../sdd-kit-3/` |
| Workspace | `../README.md` maps every item around this repository |
| Method | `CLAUDE.md` loads `../sdd-kit-3/AGENTS.md` |
| Package | `substrate-kernel` 1.1.2 on PyPI; import name `substrate` |

**What changed from the previous round.** Every `substrate` command was run on 2026-11-20 and the forms were corrected against the program, not a `grep` of `cli.py`. Round 2 wrote `substrate run <topology>`, `substrate inspect <record-root>` and `uv run twine check`; the real forms are `substrate run --topology <name>`, `substrate inspect ROOT --seq N` (a query flag is required), and `uv run --with twine twine check` (twine is not a dependency). Round 2 named only `run`, `demo`, `inspect` and `narrate`; this round carries the full twenty-command surface with each command's exit code, in Day-to-day development. `uv build` and `twine check` were run (exit 0), so Build and release now states a result, not an assumption. The BLACKBOARD read commands, Orientation and the gate stack are unchanged from round 2.

---

## Orientation

Read, in order, before doing anything. "Read" means the whole file unless a line says otherwise.

- **The method.** `CLAUDE.md` loads `../sdd-kit-3/AGENTS.md`, the working agreement. A first session reads the whole kit: `../sdd-kit-3/README.md`, `AGENTS.md`, `TECHNIQUES.md`, `ADDENDUMS.md`, `foundations/01`–`04`, `grammar/PRINCIPLES.md` and `BOOTSTRAP.md`, `templates/`, `lib/sdd.py`, `example/`.
- **The records.** `README.md` (the public face), `process/WORKING_AGREEMENT.md` (the standing rules), `process/BLACKBOARD.md` (the decision log and sprint-close record), `process/KIT_DIARY.md` (findings about the method), `process/RESEARCH.md` (the empirical log of what real models do on the topologies). The commands that read the log:
  ```
  tail -n 80 process/BLACKBOARD.md                              # the recent record, newest last
  grep -nE '^- \*\*[0-9-]{10} (user|agent-resolved)\*\*' process/BLACKBOARD.md   # decisions in the kind-prefixed form (2026-11-20 on)
  sed -n '/^## Decisions/,/^## Built/p' process/archive/BLACKBOARD-to-2026-11-20.md   # the grouped decisions of the prior sectioned shape
  tail -n 120 process/KIT_DIARY.md
  ```
  The BLACKBOARD is one newest-last append-only stream: a new entry goes at the end, `tail` shows the recent record, and a correction is a new entry naming the one it corrects. It was reordered from the sdd-kit-2 sectioned shape on 2026-11-20; the grouped decisions, deferred items, open questions and drift watchlist of that shape are in `process/archive/BLACKBOARD-to-2026-11-20.md`.
- **The current direction.** `process/planning/README.md` indexes every piece of work with its status; the live one is `process/planning/substrate-boundary-and-runbook-2026-11-09/`, the fourteen-stage boundary refactor whose sequence has not yet run. A folder the index marks closed, superseded or reverted is history, opened only when a current document points to it.
- **The code.** `src/substrate/cli.py` (the CLI entry; `substrate.cli:main`), `src/substrate/kernel/` (the append cycle, the writer loop, replay), `src/substrate/api.py` (the public surface, re-exporting the nine ideas), `src/substrate/topologies/session/` (the session topology substrate-ui drives), `src/substrate/record/` (the on-disk format), `tests/`.
- **The build system.** `pyproject.toml` (dependencies, the dev extra, the pytest and mypy and ruff configuration, the sdist include-list, the two import-linter contracts), `scripts/ci_local.sh` (the default gate), `scripts/ci_local_ubuntu.sh` (the Linux axis via Docker).
- **The sibling repository.** `../substrate-ui/` imports this library as an editable install and renders the session topology. Its records are at `../substrate-ui/process/`; its runbook is `../substrate-ui/RUNBOOK-2026-11-12-project-r10.md`.

## Inventory

| Surface | Path |
| --- | --- |
| Package source | `src/substrate/` (160 files mypy type-checks; 13 subpackages) |
| CLI entry | `src/substrate/cli.py` (`substrate = "substrate.cli:main"`) |
| Public API | `src/substrate/api.py` |
| Session topology | `src/substrate/topologies/session/` |
| Tests | `tests/` |
| Scripts | `scripts/` (CI, code generation, assay runners, benchmarks, the SWE-bench pipeline) |
| Specs | `docs/specs/` (kernel v15, product draft7, technical draft5, design draft1, with amendments) |
| Generated API reference | `docs/api.md` (never hand-edited; `scripts/gen_api_docs.py` writes it) |
| Walkthrough run records | `docs/walkthroughs/records/` (`scripts/gen_walkthrough_records.py` writes them) |
| Locked vocabulary | `process/signals/current.json` (the symlink/copy of `0.3.json`; `0.1`–`0.4` kept as audit trail) |
| Decision log | `process/BLACKBOARD.md` |
| Empirical log | `process/RESEARCH.md` |
| Published package | `substrate-kernel` on PyPI, version 1.1.2 |
| Installed CLI | `substrate` (linked into `~/.local/bin` by `substrate install`) |
| State directory | `~/.substrate/` (sessions, bundles, config, `daemon.sock`, `runs/`, `recent-workspaces.json`) |

## Prerequisites

- macOS or Linux on arm64 or x86-64. This machine is arm64 macOS.
- `uv` on `PATH`. This machine runs uv 0.11.8.
- Python 3.12, 3.13 and 3.14 for the full matrix; `pyproject.toml` requires 3.12+. This machine's default is Python 3.13.13; `scripts/ci_local.sh` fetches the three versions through uv.
- Ollama running locally for the real-model tests. This machine runs Ollama 0.40.13 with its API up at `127.0.0.1:11434`; when it is down the `realmodel` tests self-skip.
- Docker for `scripts/ci_local_ubuntu.sh` and for the SWE-bench harness test. This machine runs Docker 29.4.1.
- First-run install: `uv pip install -e ".[dev]"` (the editable install the src layout and the import-linter contract need). The SWE-bench scripts need `uv sync --extra swebench`, which installs `datasets` and `swebench`; the kernel imports neither.
- Secrets, for a PyPI release only: a PyPI API token for `substrate-kernel`, supplied to `twine` through `~/.pypirc` or the `TWINE_USERNAME`/`TWINE_PASSWORD` environment, never committed. The non-secret package name is `substrate-kernel`.

## Pick a chapter

| Trigger | Chapter |
| --- | --- |
| First day on this repository | Orientation |
| "Does the current tree pass its gates?" | Build and test — local |
| "Run the full three-version matrix like CI" | Build and test — local (`scripts/ci_local.sh`) |
| "Release a new version to PyPI" | Build and release — PyPI |
| "Run a topology or a demo" | Day-to-day development |
| "Run only the automated checks" | Tests only |
| A gate fails, or a command errors | Troubleshooting |

## Build and test — local

The default gate is `scripts/ci_local.sh`. It runs the exact CI stack across Python 3.12, 3.13 and 3.14, each in an isolated env (`uv run --isolated --python <v> --extra dev`), then the `_deprecated/`-preservation guard. Hosted GitHub Actions has been unavailable since 2026-07-22 (minutes exhausted), so this script exiting 0, watched to conclusion, is the bar. The commands it runs, which are also the single-version gate:

| # | Command | Exit | Notes |
| --- | --- | --- | --- |
| 1 | `uv run ruff check .` | 0 | Lint. 2026-11-20: "All checks passed!" |
| 2 | `uv run ruff format --check .` | 0 | Format. 2026-11-20: "452 files already formatted". `ruff` is pinned at `0.15.17` because format output is version-sensitive. |
| 3 | `uv run mypy` | 0 | Strict type-check of `src/substrate`. 2026-11-20: "Success: no issues found in 160 source files". |
| 4 | `uv run pytest` | 0 | The test suite. Result in "Known failures on the current tree". |
| 5 | `uv run lint-imports` | 0 | The two import-linter contracts: the CLI imports only `substrate.api`/`substrate.app`, and each unit imports only units below it. 2026-11-20: "2 kept, 0 broken". |
| 6 | `uv run substrate conformance --no-perf` | 0 | The 17 conformance checks. 2026-11-20: "15 passed, 0 failed, 1 deferred, 1 skipped". Check 6 (replay round-trip) is DEFERRED by spec amendment A1.1 for Level 3(b); check 15 (performance floor) is SKIPPED under `--no-perf`. |

The whole matrix in one command:

```
scripts/ci_local.sh            # all three Python versions; or: scripts/ci_local.sh 3.13 for one
```

The performance floor (conformance check 15, N-PERF-1) is hardware-sensitive and runs separately:

```
SUBSTRATE_PERF_GATE=1 uv run pytest tests/test_perf.py    # or: uv run substrate conformance   (no --no-perf)
```

The floor is ≥40,000 reference-shape appends per second (amendment A2.1, recalibrated from 100,000) and ≤20% regression against the previous release tag.

**Verification.** `scripts/ci_local.sh` prints a per-version `PASS`/`FAIL` summary and exits non-zero on any failure. The conformance command prints one line per check and a final tally; "No check FAILED" with the deferred and skipped counts named is the expected result under `--no-perf`.

**Rollback.** These commands write nothing outside `dist/` and the caches; there is nothing to roll back. A bad change is reverted with `git`.

**Last end-to-end run.** 2026-11-20, on this machine (arm64 macOS, Python 3.13): gates 1, 2, 3, 5 and 6 each exited 0; gate 4 was run the same day.

## Build and release — PyPI

Substrate has no release script; a release is `uv build` then `twine`. The version lives in `pyproject.toml` (`version = "1.1.2"`); the last published version is 1.1.2 (`CHANGELOG.md`).

```
uv build                                  # builds the sdist and wheel into dist/
uv run --with twine twine check dist/*    # metadata check (twine is not a dependency; --with fetches it)
uv run --with twine twine upload dist/*   # publishes; needs the PyPI token; this is the outward-facing step
```

Before a release: bump `version` in `pyproject.toml`, add a `CHANGELOG.md` entry, and keep the gate stack green. The sdist include-list in `pyproject.toml` (`[tool.hatch.build.targets.sdist]`) carries only the package, `tests`, and the project files; without it hatch packed `process/runs/` and the sdist passed PyPI's 100 MB limit (18,336 assay records, 95 MB, since 1.0.1).

`uv build` and `uv run --with twine twine check dist/*` were run on 2026-11-20, each exit 0: the build produced `dist/substrate_kernel-1.1.2.tar.gz` and the matching wheel, and `twine check` reported PASSED for every artifact in `dist/`. `twine upload` publishes and is run only to release; it was not run.

**Verification.** `twine check` reports `PASSED` for both artifacts. After upload, `pip install substrate-kernel==<new>` in a clean env installs the published version.

**Rollback.** A PyPI release cannot be withdrawn. Yank the bad version on PyPI and publish a higher one. For a local install, `pip install substrate-kernel==<prior>`.

## Day-to-day development

```
uv venv --python 3.12                 # a project venv
uv pip install -e ".[dev]"            # editable install; the src layout and import-linter need it
uv run substrate run --topology game_of_life_glider --root ./runs/gol   # run a bundled topology (no model) to a record
uv run substrate narrate ./runs/gol   # read that record as prose
```

The twenty `substrate` commands, from `substrate --help`. Each was run on 2026-11-20, most against the `game_of_life_glider` record above; the exit column gives the result, and a command that was not run says why.

| Command | What it does | Ran, exit |
|---|---|---|
| `substrate --version` | prints the version (1.1.2) | 0 |
| `substrate run --topology <name> [--root R]` | run a bundled topology to a record; `--topology-module path:func` runs a module instead | 0 |
| `substrate topology list` | the bundled topology names | 0 |
| `substrate validate --topology-module path:func` | static topology lint; `--topology-module` is required and runs nothing | 64 on a bundled package module (relative import); for a standalone module file |
| `substrate inspect ROOT (--seq N / --why --producer / --ancestry --producer / --between A B)` | deterministic record queries; a query flag is required | 0 with `--seq`, `--ancestry --producer` |
| `substrate narrate ROOT` | the record as prose | 0 |
| `substrate tail ROOT` | stream events from a live or closed record | 0 |
| `substrate replay ROOT` | replay at an honesty tier | 0 |
| `substrate language ROOT` | language measures, one JSON line | 0 |
| `substrate handoff ROOT` | topology calls per turn | 0 |
| `substrate stats ROOT` | the off-bus writer_stats / diagnostics sidecar | 0 |
| `substrate score ROOT` | score Grade events | 64 when the record has no Grade events |
| `substrate conformance [--no-perf]` | the 17 conformance checks | 0 |
| `substrate demo replay <name>` | replay a committed demo record | 0 |
| `substrate demo run <name>` | run a bundled demo live (writes under `./runs/`) | 0 |
| `substrate bundle ls / show / create / edit` | bundle scaffolding | `ls` 0; `show` 64 without an existing bundle |
| `substrate session ls / end / rm / set-name` | session subverbs | `ls` 0; the mutating verbs need a session id |
| `substrate resume ROOT` | resume a paused persistent-bus run | not run — needs a paused run |
| `substrate chat` | open a REPL session against the daemon | not run — interactive and needs the daemon |
| `substrate daemon` | start the long-running daemon | not run — long-running |
| `substrate install` | put `substrate` on PATH and patch the shell startup | not run — modifies the environment |
| `substrate builder` | open the studio in a browser | not run — opens a browser |

The real-model demos and `substrate demo run` against a live model need Ollama up with the model the topology names. `substrate install` links the command into `~/.local/bin` and patches the shell startup file; the editable install above is enough for development without it.

## Tests only

```
uv run pytest                              # the whole suite
uv run pytest -m "not realmodel"           # skip the live-model tests
uv run pytest -m "not swebench_harness"    # skip the Docker gold-differential test
uv run pytest tests/test_perf.py           # the perf test (floor gated by SUBSTRATE_PERF_GATE=1)
uv run substrate conformance --no-perf     # the 17 conformance checks without the perf floor
```

Each test has a 30-second timeout (`pyproject.toml`), a safety net against a never-quiescent writer or a self-feeding trigger loop; every test finishes well under a second. The `realmodel` tests run a topology against a live Ollama model and self-skip when it is absent. The `swebench_harness` test runs the official SWE-bench harness in Docker against a real instance (gold patch resolves, empty patch does not) and skips when `swebench` is not importable, Docker is down, or the eval image is not pullable; an emulated x86 pull on arm64 can take 10+ minutes. Class-based collection is off (`python_classes = []`) so a domain record named `Test*` (the locked record `TestResults`) is not mistaken for a test class.

## Working with the owner

Requests are recorded before work starts: a direction becomes a dated `user` or `surfaced` entry at the end of `process/BLACKBOARD.md`, cited where the owner stated it. Live testing is paced piece by piece; one item finishes and is reported before the next starts. A change to a narrow request changes only what the request names. The writing standard for every document, commit message and CLI string is the project's plain register: each sentence a fact, particulars over abstractions, short words, no emoji. Standing preferences live in `../sdd-kit-3/AGENTS.md` and `process/WORKING_AGREEMENT.md`.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `ruff format --check` reports files would be reformatted | A `ruff` other than the pinned `0.15.17` reformatted the tree | Install the dev extra (`uv pip install -e ".[dev]"`), which pins `ruff==0.15.17`; run `uv run ruff format .` and commit |
| A test wedges or a run never ends | A never-quiescent writer or a self-feeding trigger | The 30-second per-test timeout fails it fast; read the trigger or termination policy it names |
| `realmodel` tests all skip | Ollama is not running | Start Ollama; `curl -s http://localhost:11434/api/tags` should answer |
| `swebench_harness` skips or is slow | `swebench` not installed, Docker down, or an emulated x86 image pull on arm64 | `uv sync --extra swebench`; start Docker; allow 10+ minutes for the pull |
| A domain record named `Test*` is collected as a test | pytest class collection | Already disabled with `python_classes = []`; do not re-enable it |
| `import datasets`/`import swebench` fails under mypy or at runtime | They are optional, env-gated, and unstubbed | `uv sync --extra swebench`; mypy already declares both modules untyped (`[[tool.mypy.overrides]]`) |

**Known failures on the current tree (checked 2026-11-20).** None among `ruff check`, `ruff format --check`, `mypy --strict`, `lint-imports` and `substrate conformance --no-perf`; each exited 0. Two conformance results are by design, not failures: check 6 (replay round-trip) is DEFERRED for Level 3(b) by spec amendment A1.1, and check 15 (performance floor) is SKIPPED under `--no-perf`. The full `uv run pytest` on 2026-11-20 with Ollama up: 1737 passed, 14 skipped, exit 0, in 7m28s. The 14 skips are opt-in tiers that name themselves — the SWE-bench Docker binding (`SWEBENCH_HARNESS_ENABLE=1`), the live-driver runs (`SUBSTRATE_LIVE_DRIVER_TESTS=1`), the perf floor (`SUBSTRATE_PERF_GATE=1`), and `swebench_repair`'s non-deterministic producers. Hosted GitHub Actions remains unavailable (Actions minutes exhausted, since 2026-07-22); the local matrix is the bar.

## Rollback across chapters

- A local change: `git` reverts it; the gate stack proves the revert.
- A PyPI release: cannot be withdrawn; yank the version and publish a higher one.
- A local install: `pip install substrate-kernel==<prior>`.
- The `~/.substrate/` state directory: a session or bundle is data, not built output; it is not rolled back by a code change.

## Escalation

The questions only the owner can answer are the closed list in `../sdd-kit-3/AGENTS.md` "Questions only the user can answer": product intent the artifacts do not contain; money, accounts, credentials; outward-facing or irreversible acts (a PyPI upload is one); risk only the owner can accept; physical-world observation; contradictions in the owner's own instructions. Substrate adds two project-specific halts (`process/WORKING_AGREEMENT.md`): `spec_ambiguity`, where a sprint needs a semantic the canonical specs underspecify (surface the exact spec section and the ambiguity; the owner rules or cuts an additive spec revision), and `conformance_unmapped`, where an artifact is needed by a conformance check that no sprint chain yet covers end to end (surface for wave re-planning). A newly found defect is recorded the same day on `process/BLACKBOARD.md`. On an incident in a running session, the session's record under `~/.substrate/sessions/<id>/` is the first thing to read; the daemon socket is `~/.substrate/daemon.sock`.

## Conventions

The standing rules a reader keeps while following this runbook:

- **The eight-word vocabulary.** Producer, Bus, View, Predicate, Trigger, Route, TerminationPolicy, Topology (the README frames Event as a ninth idea). No anthropomorphic synonyms ("agent", "actor", "speaker") and no reframes of substrate's own concepts (a topology as a "workflow", a firing as a "step", a run as a "task"). This binds docs, CLI output, log fields and code identifiers. The English word "task" for the problem a model solves is the input domain and is allowed.
- **Structured output, with sequence numbers.** The runtime returns typed values, never prose; identification names a sequence number ("at seq 1247"), never "around the third trigger". No emoji.
- **Append-only logs.** `process/BLACKBOARD.md`, `process/RESEARCH.md` and `process/KIT_DIARY.md` grow at the end; a correction is a new entry naming the one it corrects.
- **No in-place edits to planning documents.** A new round is a new file whose first lines name what it supersedes; the old round moves to its piece's `superseded/`.
- **No deletions.** Retired code and records go to `_deprecated/`, `process/archive/` or a piece's `superseded/`; the audit trail is the work (hard rule 12). The `_deprecated/`-preservation guard in `scripts/ci_local.sh` checks this.
- **SPDX headers.** Every source file carries the PolyForm-Noncommercial-1.0.0 identifier and the copyright line.

## References

Inside the repository: the four canonical specs and their amendments (`docs/specs/kernel_spec/v15.md` with `v16_reconciliation_note.md`, `docs/specs/product_spec/draft7.md` with amendments A1–A3, `docs/specs/technical_spec/draft5.md` with amendment A1, `docs/specs/design_spec/draft1.md`); `CONTRIBUTING.md` (the gate list and the spec corpus — stale on two points as of 2026-11-20: it names the method as `../sdd-kit-2/` where it is now `../sdd-kit-3/`, and the vocabulary as `0.2.json` where `current.json` tracks `0.3.json`); `scripts/ci_local.sh`; `pyproject.toml`. Outside: the runbook guide this file follows, `../docs/runbook-guide-2026-10-30/GUIDE-2026-11-04-runbook-r2.md`, and the file-organization guide behind the repository layout, `../docs/document-organization-guide-2026-10-30/GUIDE-2026-10-30-reorganizing-files-and-folders-r3.md`.

## Session startup

Paste at the start of a session. The method's own session-start list comes first: `CLAUDE.md` has loaded `../sdd-kit-3/AGENTS.md`.

```
# 1. the method (first session: the whole kit)
cat CLAUDE.md                                        # loads ../sdd-kit-3/AGENTS.md
# 2. the records
cat process/WORKING_AGREEMENT.md
tail -n 80 process/BLACKBOARD.md
grep -nE '^- \*\*[0-9-]{10} (user|agent-resolved)\*\*' process/BLACKBOARD.md
sed -n '/^## Decisions/,/^## Built/p' process/archive/BLACKBOARD-to-2026-11-20.md
tail -n 120 process/KIT_DIARY.md
# 3. the current direction
cat process/planning/README.md
ls process/planning/substrate-boundary-and-runbook-2026-11-09/
# 4. the locked vocabulary and the current sprint card
cat process/signals/current.json
ls process/sprints/ | tail -5
```

First session also reads the whole kit: `../sdd-kit-3/README.md`, `AGENTS.md`, `TECHNIQUES.md`, `ADDENDUMS.md`, `foundations/01`–`04`, `grammar/PRINCIPLES.md` and `BOOTSTRAP.md`, `templates/`, `lib/sdd.py`, `example/`.
