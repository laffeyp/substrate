# process/runs — index

*Current as of 2026-11-20. Generated run data, grouped by run. The scripts under `scripts/` write here by default; nothing in `src/` reads it as source, except three language tests that read the small `assays/length_drift_2026-10-12*` directories. The verdicts a run supports are recorded in `process/BLACKBOARD.md`, not in the logs. Four families:*

| Family | What it holds | Written by | Tracked in git |
|---|---|---|---|
| `assays/` | assay and SWE-bench evaluation runs, one directory per run | `scripts/assay_*.py`, `scripts/agency_assay.py` | mixed — see `assays/README.md` |
| `benches/` | benchmark runs: `agency/`, `coding/` | `scripts/agency_assay.py`, `scripts/bench_coding.py` | `coding/` is gitignored; `agency/` tracked |
| `smokes/` | smoke runs: `flask/`, `solves/`, `swebench/` | `scripts/flask_solve.py`, `scripts/solve_instance.py`, the SWE-bench smoke | all gitignored |
| `fixtures/` | a committed input fixture (`swebench-lite-full-qwen3coder480b-20260627.jsonl`) | authored, not generated | tracked |

The gitignore patterns that keep the generated output out of the tree are in `.gitignore` under the 2026-08-31 run-directory note. A run directory that is tracked is kept as evidence; a gitignored one lives on disk only.
