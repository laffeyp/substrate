# Sprint 253 — Adapters

```yaml
---
id: 253
status: open
opened_at: 2026-10-08
pass_kind: remediation
roadmap: substrate-ui/process/planning/ROADMAP-2026-10-08-lens-audit-remediation.md
ledger_rows: 19
---
```

## why

OllamaResponder retries 4xx; two retry layers compound to 30 requests; the Responder protocol omits arespond; Ollama's address and the default model each have several sources (findings §4).

## sources

- RFC 9110 §15: 4xx is a client error; retry only transient classes (408, 429, 5xx, connection).

## scope (ledger rows)

Each row closes as named; a row the sprint cannot close halts the sprint.

| id | close | finding |
|---|---|---|
| F007 | fix | protocols.py:50-57 — Responder declares only `respond`; adapters expose `arespond` and call_responder prefers it — the async half of the seam is undeclared. Verify in adapters. |
| F064 | fix | models.py:115-118 — "Every Responder must expose both surfaces per the protocol (sprint 244)"; protocols.Responder declares only respond (see protocols.py:50-57). The async surface the session depends on is unchecked … |
| F065 | fix | models.py:270-286,306-320 — OllamaResponder retries on ANY httpx.HTTPError, including 4xx (a 400 "bad model tag" is re-sent 3 times with 1 s + 2 s sleeps). Retry guidance (RFC 9110 §9.2.2 idempotency; Google AIP-194) … |
| F066 | fix | rate_limit.py:172-202 + models.py — RateLimitedResponder's 10 retries wrap OllamaResponder's own 3 retries: up to 30 requests per call; and rate_limit.py:190-197 classifies by searching "429"/"503" in a RuntimeError m… |
| F067 | fix | rate_limit.py:104-114 — a module-global dict of asyncio.Semaphore shared across event loops; session turns each run on a fresh loop (session_registry _run_*_sync), and an asyncio primitive used under contention on a s… |
| F068 | fix | rate_limit.py:109-111 — docstring promises a warning when capacities disagree; none is logged. |
| F069 | fix | rate_limit.py:60-65 — Ollama Cloud tier limits cited from pooyagolchian.com and devtoolhub.com blog posts, not Ollama's own documentation. |
| F070 | fix | ensemble.py:90-95 — EnsembleResponder.arespond falls back to the SYNC respond on the event loop (call_responder offloads to a thread); ensemble metered stand-in reports model="ensemble-standin", losing which backend a… |
| F071 | fix | models.py:446-452 — CliResponder passes the whole prompt as one argv element; macOS ARG_MAX is 1 MiB (argv+env). A transcript past that fails with E2BIG; the prompt is also visible in `ps`. Measure the largest prompt … |
| F129 | fix | protocols.py:55 — `Responder` docstring: reference adapters "live in `substrate.reference`"; they live in `adapters/models.py:97,132`. |
| F147 | fix | adapters/models.py:170 — `OLLAMA_BASE_URL` read from the environment inside the adapter constructor, not passed from a composition root. |
| F273 | fix | reference/__init__.py:6, walkthrough.py:6-7,16 — "real local LLMs via the openai-compat adapter (Ollama at http://localhost:11434/v1) … Requires the `openai-compat` extra (httpx)". OllamaResponder now posts to the nat… |
| F274 | fix | reference/__init__.py:10-13 says import the Responder seam "from `substrate.reference`"; reference/_models.py:11 says "New code should import from `substrate.adapters`"; reference's own r1/r2/walkthrough import from `… |
| F275 | fix | r3_codesynth.py:176-177 — "walkthrough: a real model streams arbitrary chunks and tree-sitter replaces _complete_defs". No tree-sitter anywhere in src/ or pyproject; walkthrough.py:31,175 uses `_complete_defs`. |
| F276 | fix | r3_codesynth.py:127 — `block.split("def ", 1)[0].join(["def ", p]).strip()` evaluates to `block.strip()` ("" joined over ["def ", p]). |
| F277 | fix | r3_codesynth.py:120-127 — "complete declaration" = contains ":" and "\n " anywhere after a `def ` split; a def is "complete" at its first indented line, and any "def " substring (e.g. in a string or `undef `) starts a… |
| F278 | fix | r1_ensemble.py:81 — `chosen = next((c for c in cands if c["member"] in choice), cands[0])`: substring match ("m1" in "m10"); an adjudicator reply naming no member silently selects the first candidate, and the Verdict … |
| F279 | fix | walkthrough.py:33-34 — model names hardcoded (`llama3.2:1b`, `huihui_ai/qwen2.5-coder-abliterate:7b`); l.192 default record root `Path("walkthrough")/which` relative to cwd. |
| F281 | fix | — docstrings only; nothing found. |

## checks

- A 400 is sent once; a 503 is retried.
- One retry layer; rate-limit classification reads status codes, not message text.
- `Responder` declares `arespond`; mypy checks every adapter against it.
- One Ollama address and one default model, passed from a composition root.
- Rate-limit citations point at Ollama's own documentation or are removed.

## result

(filled at close)
