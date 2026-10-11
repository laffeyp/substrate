---
name: feedback-check-the-box-before-asserting-infra
description: "Everything is always on this box. Before writing \"needs Docker\" / \"needs Ollama\" / \"needs the Architect's box\" / \"requires live infra\" — actually check. It's here."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: a6554063-9cfe-4745-9f71-070dbc98d4f8
  modified: 2026-08-14T16:42:05.249Z
---

Before writing any sentence that asserts what infrastructure is NOT available — Docker, Ollama, swebench eval images, an API endpoint, a model, a dataset — actually check. On this box the answer is almost always "it's here." I have been writing "needs the Architect's box" / "needs Docker + Ollama live" / "requires live infra" as if those things weren't running on the machine I'm on. They are.

**Why:** user verbatim: *"Take it on the box, everything is always on the box, it's just that you don't actually check."* I had just claimed Sprint 199's S9/S10 wire-checks "need Docker + Ollama on the Architect's box" and named two test files (`test_assay_realmodel.py`, `test_assay_swebench_host.py`) as "needs infra" while skipping them. Both ran fine when I actually ran them (3/3 pass). Docker was up (v29.4.1), Ollama had 17+ models loaded (llama3.2:1b, qwen2.5-coder:7b, cloud models), swebench eval images were cached locally.

**How to apply:** the check commands that must fire before asserting infra absence —

- Docker: `docker info` (or `docker ps`)
- Ollama: `curl -sf http://127.0.0.1:11434/api/tags`
- Swebench images: `docker images | grep swebench`
- A specific model: check the Ollama tags response for its name

Only after the check returns absent may I write "not available." Related: [[substrate-test-invocation-gotcha]] (Ollama live here — already in memory), [[observation-contract-never-skip]] (run behavior tests for real, don't skip on invented infra excuses), [[be-your-own-skeptic-green-is-not-proven]] (extended: green-without-running is not green at all — a claim that a test "needs infra I don't have" is a claim about the machine, not the test, and it must be verified before it becomes a decision to skip).

**The wider pattern:** any claim I make about the SETUP — my box, the Architect's box, "usually this needs X" — is the same shape as the claims about the SYSTEM covered by KIT_DIARY 21 and 36 (tribal knowledge dressed as design choice). Check first; assert second.

**Cost framing is also drift.** Firing `qwen3-coder:480b-cloud` or `kimi-k2.7-code:cloud` or `deepseek-v4-pro:cloud` at N=300 is not a cost question. Words like "real cost", "needs cost opt-in", "opt in to spend" are wrong here — same shape as "needs the Architect's box" (asserting a constraint that isn't there). The rate-limit constraint that IS real: cloud-tier concurrency caps (`OllamaQuota.pro()` / `.max_tier()`) — the shim throttles concurrent in-flight requests to the tier's semaphore. That's a THROUGHPUT constraint, not a cost one. Related: [[project-no-cost-tracking]] (substrate itself never tracks $ / price — extending: my prose about the user's runs shouldn't either).
