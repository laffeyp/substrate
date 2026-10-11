---
name: substrate-test-invocation-gotcha
description: "Run substrate tests with `uv run python -m pytest`, never `uv run pytest` (the latter hits the wrong interpreter)"
metadata: 
  node_type: memory
  type: reference
  originSessionId: ff12be5c-48fe-4cf1-a6d8-0b74675e20a1
  modified: 2026-08-01T00:02:39.308Z
---

In the `substrate` repo, the README documents `uv run pytest`, but that command resolves the Homebrew `/opt/homebrew/bin/pytest` (Python 3.11, no `msgspec`) and produces ~40 spurious collection ERRORS that look catastrophic and are not. The project's 3.12 `.venv` exposes pytest only as a module, so the correct invocation is **`uv run python -m pytest`** (294 passed, 1 skipped as of 2026-06-18). CI is unaffected (no shadowing binary there).

**mypy must be on PATH for the FULL suite (2026-07-31).** The coding-gate tests (`test_coding_problems`, `test_coding_flow`, `test_assay_coding`, `test_code_evolution`) run `run_gate`, which invokes `ruff`/`mypy --strict`/`pytest` as SUBPROCESSES calling the bare command. `mypy` lives at `.venv/bin/mypy` but is NOT on the shell PATH by default, so a plain `.venv/bin/python -m pytest` yields **77 failures all with `returncode=127, 'mypy: command not found'`** — an ENVIRONMENT artifact, not a regression. Run the full suite with the venv on PATH: `PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest` → 579 passed / 1 skipped / 0 failed. Lesson (substrate's own KIT_DIARY #27 discipline): a returncode-127 gate failure is "couldn't grade," not "code broke" — never attribute it to a code change. Always run the FULL suite (not just the touched test file) after any adapter/shared change, with mypy on PATH.

Other verified environment facts for this workspace (2026-06-18 full review):
- **Ollama is installed and live** at `localhost:11434`, with `llama3.2:1b` and `qwen2.5:7b-instruct` present — so the `@realmodel` tests and the real-model demo path run live here (they self-skip elsewhere). Conformance: `uv run substrate conformance` = 16 PASS / 0 FAIL / 1 DEFERRED, perf floor genuinely measured ~56k appends/sec > 40k.
- The 2026-06-18 review wrote a non-code artifact `REVIEW.md` at the workspace root (spans both repos; not inside either git repo). 78 verified findings. Top issues: read-path silent data-loss (`record.py:250`), `asyncio.to_thread` shutdown stall on the real-model path (`reference/_models.py:162`), console stored-XSS (`web/app.js`), hollow `substrate validate`. See [[be-your-own-skeptic-green-is-not-proven]].
