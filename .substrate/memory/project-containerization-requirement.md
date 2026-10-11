---
name: project-containerization-requirement
description: "Containerization is REQUIRED for SWE-bench (and the adversary-proof firewall), NOT for current weak-local-model runs — queued behind finishing the current benchmarking work"
metadata: 
  node_type: memory
  type: project
  originSessionId: 6213fff8-2552-4b26-8c40-aa765e0e8cc4
---

**Decision (2026-06-26):** SWE-bench is a necessary destination for substrate benchmarking. Containerization is REQUIRED for it — record it now, add it WHEN we do SWE-bench, finish the current work first.

**Why it's needed (the real reasons, not hype):**
- **SWE-bench is table-stakes Docker.** The SWE-bench harness runs every instance in its OWN container by design — untrusted patches against a real repo, plus reproducibility. Our `assay/swebench.py` binding already lazy-imports swebench + runs Docker via TestSpec. So containerization isn't bolt-on; it's the substrate the recognized-benchmark path assumes from the start.
- **The adversary-proof firewall telos.** Today we run arbitrary LLM-generated Python on the BARE HOST with only a timer. Fine vs the current weak, non-adversarial local models. The exposure the moment the threat model gets serious: resource bombs (fork-bomb / memory — a timeout doesn't stop them), network (exfil / phone-home), filesystem (read host env/ssh keys/the whole problem bank; write anywhere). A container closes all of it at once via cgroup limits + `--network none` + FS isolation.

**The category clarification (the user's worry):** containerization wraps the GRADE (running candidate code: ruff/mypy/pytest), NEVER the models. Models run in Ollama (a separate `:11434` server), untouched — so "it slows down local models" is a category error. It adds only ~10-20% to the grade subprocess (already seconds), zero to inference; reuse a warm container / lightweight isolation (bubblewrap/nsjail) if even that matters.

**How to add it (when we do SWE-bench):**
- SWE-bench: use its native per-instance Docker harness (already wired in swebench.py).
- Our own bank: give `coding_flow.gate.run_gate` a sandboxed mode — run the gate command inside a container (or bwrap) with no network, FS limited to the sandbox dir, cgroup mem/cpu/pids limits.
- The SPECIFIC test-file-reading hole (a candidate reading test_grade.py for the answers) is fixed cheaper by an **input/output split** (feed inputs, capture outputs, compare to expected in the GRADER process where the candidate never sees them) — NOT by a container. Container is defense-in-depth for the broad untrusted-exec problem; the I/O split is the exact fix for the read.

See [[project-substrate-benchmarking-phase]], [[project-assay-roadmap]]. NOT needed for the current local-coder-ensemble experiment — do it at the SWE-bench step.
