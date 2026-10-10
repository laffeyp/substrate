# Compaction

A session's history grows with every turn. When it no longer fits in the model's context window, the session leaves the oldest turns out of the prompt. That is compaction. Nothing is deleted: the record keeps every event, and the model can read any of it back.

## What Substrate does today: rolling window

Each model call's prompt holds the seed, the session's prompt pieces (role, bundle, tool list, parent context, per-turn text), and as many of the most recent turns as fit. The current turn always stays.

- **Budget.** The history gets 60% of the driver's context window, less the seed and prompt pieces; the other 40% is left for the reply.
- **Sizing.** Each turn's size is estimated from its rendered text (characters ÷ 4). The window keeps the newest turns whose estimate fits, oldest dropped first. (Before sprint K261 the window assumed every turn cost 800 tokens whatever its size, and dropped history a short conversation never needed to drop.)
- **On the record.** Every drop writes a `TranscriptCompacted` event: the seq range dropped, the first seq kept, and the estimated prompt size before and after. Every prompt the model was sent is on the record as `PromptComposed`, so what the model saw at any call can be read back.
- **Getting history back.** A session's model has the `inspect_record` tool. When it needs something older than the window, it reads its own record — the actual events, not a summary.

This is the "reactive" choice (product spec §4a): the model fetches old history when it needs it, at the cost of a tool call, and reads it at full fidelity.

### Measured on a real model (2026-10-09)

`tests/test_realmodel_session_compaction.py` runs `llama3.2:1b` on a local Ollama at `num_ctx=2048` (Ollama's default window) and keeps the conversation going until it overflows:

| | |
|---|---|
| Model calls | 8 |
| Compactions recorded | 3 (estimated prompt cut 1,273 → 1,126, 1,409 → 1,089, 1,556 → 833 tokens) |
| Largest prompt Ollama read | 1,011 tokens of 2,048 (`prompt_eval_count`); no prompt was cut by Ollama |
| Our estimate against Ollama's count | Ollama counted 0.88–1.02 × our estimate from the second call on; the first, tiny prompt counted 1.93 × (Ollama's chat template adds about 26 tokens) |
| Replies after the first compaction | every turn answered |

## Drivers that compact on their own

A CLI driver (`claude`, `codex`) runs its own harness, which compacts before the underlying model sees the prompt. Substrate sends the CLI the prompt it would send any driver and budgets against the CLI's declared input ceiling (`[driver.<name>].context_tokens` in `~/.substrate/config.toml`, default 100,000).

## Planned, not built

From product spec §4a:

- **Summary plus tail (v1.5).** When the prompt would overflow, replace the oldest turns with one summary event, also written to the record, and keep the last turns verbatim. "Proactive": the model reads a synthesis it did not ask for.
- **Semantic compaction (later).** Choose earlier turns by relevance to the current task instead of by recency, with a small side model or a similarity index.

Either would write its own `TranscriptCompacted` (or summary) event, so the record still shows what the model was and was not given.
