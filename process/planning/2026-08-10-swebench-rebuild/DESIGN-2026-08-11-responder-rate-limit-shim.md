# DESIGN — Provider-agnostic rate-limit shim for Responders (2026-08-11)

*The runner is under-defended against provider rate limits. The 2026-08-10 N=300
Lite v2 run fired 8 concurrent requests against a single Ollama Pro-tier model
and got 3337 of 4088 HTTP calls throttled to 429 (82%). Only the single-call
arm survived; every multi-call arm collapsed to zero passes. The topology
tolerated the failure by emitting no patch, so the row said "no model_patch" —
same wire as an honest failed try. No signal distinguished "throttled" from
"tried and failed."*

*Ollama Cloud's tiers cap concurrent MODELS (Free 1, Pro 3, Max 10), not
requests. OpenAI, Anthropic, xAI, Gemini each carry their own shape — RPM,
TPM, concurrent-request caps. Every one of them will kill a naive fire the
same way. The shim below is provider-agnostic on purpose: wrap the one
provider Substrate uses today (Ollama), keep the seam wide enough for the next
provider to plug in without a redesign.*

## The claim to measure

Under an assay whose arms fire the same model repeatedly, the effective
concurrency is not `SWEBENCH_CONCURRENCY` — it is `min(SWEBENCH_CONCURRENCY,
provider_cap_per_model)`. When the assay ignores that, the number reported for
the multi-call arm is dominated by throttling, not by the arm's mechanism.

## Two things the shim must do

1. **Cap concurrent in-flight calls per (provider, model) key** so a request
   never leaves the runner unless the provider will actually serve it. One
   semaphore per key, shared across every Responder that speaks to that key.

2. **Honour Retry-After and back off honestly on 429/503.** The pre-fix
   OllamaResponder retries 3 times with 1s/2s/4s backoff and gives up. Under
   sustained rate-limit that empties every retry budget in seconds and fails
   the request. A rate-limited call is not a failed call — it is a "try again
   at time T" call.

## The shim shape

**One new module: `src/substrate/adapters/rate_limit.py` (~120 lines).**

Three types:

- `ProviderQuota` — a data descriptor for one provider tier. Carries
  `max_concurrent_per_model: int`, `max_rpm: int | None`, `max_tpm: int | None`.
  Static; readers construct it once per tier + provider.

- `_semaphores: dict[str, asyncio.Semaphore]` — module-level, keyed by a
  string like `"ollama:qwen2.5-coder:7b"`. The semaphore's counter is the
  quota's `max_concurrent_per_model`. Shared across every wrapper for the same
  key so two `Responder`s pointing at the same model share one gate.

- `RateLimitedResponder(inner: Responder, key: str, quota: ProviderQuota,
  max_retries: int = 10)` — the wrapper. Implements the `Responder` protocol.
  `arespond` acquires the semaphore, calls `inner.arespond`, releases; on
  `httpx.HTTPStatusError` with 429 or 503, reads `Retry-After` off the
  response, sleeps that long (or falls back to exponential backoff capped at
  60s if the header is missing), retries up to `max_retries` before raising a
  typed `ProviderRateLimited` exception the runner catches by type.

**Per-provider quota helpers, one classmethod each.** `OllamaQuota.free()`,
`OllamaQuota.pro()`, `OllamaQuota.max_tier()`. Each returns a
`ProviderQuota` with the tier's public limits. When the next provider lands
(`AnthropicQuota.tier_1()`, `OpenAIQuota.tier_2()`), the shape is one
classmethod per tier per provider. No new interfaces.

## The runner change

`scripts/assay_swebench_confirmatory.py`:

1. Read `SWEBENCH_OLLAMA_TIER` env (`free` | `pro` | `max`, default `pro`).
2. Construct the matching `ProviderQuota` at startup, log it.
3. Every `OllamaResponder(model)` construction now goes through
   `RateLimitedResponder(OllamaResponder(model), key=f"ollama:{model}",
   quota=quota)`. Every arm that touches the same model shares the gate.
4. The pre-flight (`fold-2026-08-11` at
   `scripts/assay_swebench_confirmatory.py:524`) already pings every declared
   model; the same pass now also verifies the tier's concurrent-model cap is
   ≥ the number of unique models the run declares. If not, halt.

## Typed exception at the boundary

`assay/swebench_errors.py` gains one class: `ProviderRateLimited` extending
`SwebenchRunnerError` with `reason = REASON_HARNESS_ERROR` (or a new
`REASON_RATE_LIMITED` if the shared closed set grows — see below). The
runner's `_classify_cell_error` catches it typed; the row's `reason` field
carries the closed-set string.

## Closed-set additions

Add `REASON_RATE_LIMITED` to `_HARNESS_REASONS` at `assay/swebench.py`. This
is a vocabulary_change_required halt under AGENTS.md hard rule 2 — file the
proposal, wait for ratification, land the reason string, land the wrapper's
raise-site. Every writer + reader migrates in one commit. The vocab word
already existed as an unnamed failure mode; naming it closes a gap the
holistic review (F4) called for.

## Testing shape

Three pure unit tests, no live network:

1. **`test_rate_limited_responder_shares_semaphore_across_wrappers`.** Two
   wrappers with the same key have the same underlying semaphore; a `respond`
   on one blocks a `respond` on the other when the counter is exhausted.

2. **`test_rate_limited_responder_honours_retry_after_header`.** A mock inner
   Responder raises `httpx.HTTPStatusError(429)` with `Retry-After: 5`; the
   wrapper sleeps 5 seconds (verified by a monkey-patched `asyncio.sleep`
   collecting the sleeps).

3. **`test_rate_limited_responder_raises_typed_on_exhaustion`.** After
   `max_retries` attempts, the wrapper raises `ProviderRateLimited`, not
   `RuntimeError`. Runner catches by type; row lands with typed reason.

One end-to-end test env-gated behind an actual Ollama endpoint verifies the
gate-share is real, not a fiction of the mocks.

## What this is NOT

- **Not a general rate-limiter service.** No token buckets, no shared
  server-side state, no fairness across process boundaries. One Python
  process, one set of semaphores, one Retry-After honour policy.
- **Not a queue.** Requests wait on the semaphore or 429-retry, they do not
  enter a durable queue. If a topology's watchdog fires while a request is
  waiting, the request cancels with the topology.
- **Not per-request cost accounting.** `ModelUsage` already tracks tokens and
  wall-clock per call. The shim adds throughput protection, not economics.
- **Not a provider-selection layer.** A caller still constructs the Responder
  for the model it wants. The shim adds capacity awareness to that
  constructor; it does not route away from a rate-limited model to a healthy
  one. That belongs to a separate concern (which the ensemble arm partially
  addresses today).

## The seven landing steps

1. **File the vocab halt** on `REASON_RATE_LIMITED` to
   `process/BLACKBOARD.md`. Await Architect sign-off.

2. **Land the shim module** at `src/substrate/adapters/rate_limit.py` with
   the three types + three quota helpers. Three unit tests. Public exports via
   `substrate.adapters.__init__`.

3. **Add `ProviderRateLimited`** to `assay/swebench_errors.py`. Add
   `REASON_RATE_LIMITED` to `_HARNESS_REASONS`. Both writers migrate in the
   same commit as the vocab-halt ratification.

4. **Wire `SWEBENCH_OLLAMA_TIER`** into the runner's model construction path.
   Pre-flight verifies the tier can hold every unique model declared.

5. **Update the confirmatory runner's `_classify_cell_error`** to catch
   `ProviderRateLimited` before the string-repr fallback. One row per
   rate-limited cell, typed reason.

6. **Fire a small Lite check** at N=10 against Ollama Pro to prove the
   shim + Retry-After honour actually work under real 429 pressure.

7. **Land the next provider quota** when the next provider does. The shape
   is one classmethod per tier per provider; nothing else changes.

## The one-paragraph summary

Substrate today defends against provider rate limits by hoping a small
exponential backoff will pass under the wire. It does not, and the 2026-08-10
Ollama Pro run's 82% throttle rate proves it. The shim below caps concurrent
calls per (provider, model) key at the provider's declared tier limit and
retries 429s honestly by reading Retry-After. The wrapper implements the
Responder protocol so a topology never knows it exists; the runner constructs
it once per model at startup. The shape is provider-agnostic — one
classmethod per tier per provider — so the next provider adds no new
interfaces. The rate-limit failure becomes a typed row with a closed-set
reason string, not a silent zero-patch cell.
