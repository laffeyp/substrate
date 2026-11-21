# RESEARCH: guidance, length and tone changed mid-session

*2026-10-12. Asked by the Architect: show a session's guidance, length and tone in its pane and let them change mid-session; and, before building, "how do we change it in the middle of a session? … does that actually swap out the past conversation too? Or does it only come in as new guidance … what effect would that have on the model? … it looks like you're continually feeding new things to a model, but you're not. You're just feeding the same thing back in again and again."*

## What happens today

Read from the code on 2026-10-12.

- **A change is a record event.** `SessionChanged {field: length | tone}` starts the session-prompt producer again for the `control` source only (`_REWRITTEN_ON_CHANGE`, `topologies/session/__init__.py`). It writes a new `control` fragment carrying the change's seq; the prompt keeps each source's newest fragment (the cohort rule, § P.4). Guidance (`harness_level`) has no such rewrite: it is set at open.
- **The control text rides the system channel.** `control` is in `SYSTEM_SOURCES` with `bundle_style` and `baseline` (`session/vocabulary.py`).
- **The past is not rewritten.** Every earlier user message and reply stays as written; the record never changes, and the prompt is a pure function of it.
- **Every turn sends everything again.** No driver keeps the conversation between turns: `claude` runs as `claude -p` with no `--resume`, and Ollama's `/api/chat` is stateless. Each turn composes the whole prompt from the record (system text, then the history) and sends it. The Architect's reading is right: nothing new is fed in except the new message; the rest is the same text sent again.

So after a tone change the model reads: the new tone sentence at the top, then every earlier reply, written in the old tone, then the new message.

## What that does to a model

- **Instructions fade over a conversation.** Li et al., "Measuring and Controlling Instruction (In)Stability in Language Model Dialogs" (arXiv 2402.10962, 2024): on LLaMA2-chat-70B and GPT-3.5, a system prompt's hold drops significantly within eight rounds; the authors tie it to attention decaying over long exchanges and offer split-softmax as a fix (a model change, out of Substrate's reach).
- **A model copies its own earlier replies.** Wan et al., "Mitigating Conversational Inertia in Multi-Turn Agents" (arXiv 2602.03664, ICML 2026 poster): models "mimic their own previous responses as few-shot examples"; attention to earlier assistant turns grows with context length while attention to the system prompt falls. Huang et al., "Do LLMs Benefit From Their Own Words?" (arXiv 2602.24287, ICLR 2026): removing earlier assistant replies left quality unchanged on a large share of turns, and models "over-condition on their previous responses", carrying "stylistic artifacts" forward.
- **Read together:** a tone or length sentence changed only at the top competes with every reply already written the old way, and the replies sit closer to the model's next token. Neither paper tests a mid-session change of a style instruction; that is an inference from both, not a result. The two 2026 papers are single studies, not replications.

## What it costs to change the top of the prompt

- **Anthropic's API** caches a prompt as a prefix in the order tools, system, messages; "changes at each level invalidate that level and all subsequent levels" (platform.claude.com, prompt caching). A changed system text means the whole conversation after it is processed again.
- **Ollama on this machine**, measured 2026-10-12 with `llama3.2:1b`, a 515-token prompt, the system line changed between calls: prompt evaluation took 48.0 ms the first time, 4.2 ms for the same prompt again, 30.0 ms after the tone line changed, then 3.9 ms. `prompt_eval_count` reads 515 every time; the time shows the reuse. Ollama's own documentation does not describe this cache; the claim rests on the measurement and on third-party write-ups of llama.cpp's slot cache.
- **The claude CLI:** whether `claude -p` caches across separate runs was not checked.
- A change at the top costs one full reprocessing on the next turn, then the new prefix is reused. Measured in time and tokens; Substrate tracks no prices.

## Ways a change can enter the prompt

1. **System text only** (today). The newest `control` fragment replaces the old one at the top. Clean, one place, but the instruction sits far from the model's next words and competes with the old-style replies.
2. **System text plus a marker where the change happened.** The record already holds the `SessionChanged` event at its seq; the composer can render it in the history at that point ("from here on: terse"). The newest instruction then also sits next to the turns it governs. The record is unchanged; only how the prompt is drawn from it changes.
3. **Rewriting past replies.** Not possible within Substrate's rule: the record never changes, and the model's replies cannot be regenerated without running the model again.
4. **Leaving out earlier replies** (Huang et al.'s context filtering). It removes the pull of the old style and loses what the replies said; a large change to what every driver reads.

## Showing them in the pane

- The Architect named two shapes: the values at the end of the session bar's line ("turn 3 · 12s · 2 tools · returned · low · normal · neutral"), or one chip per control in the top bar.
- The app already shows the picks in the model chip's card (U139).
- Anthropic's chat app had a styles menu (Concise, Explanatory, Formal) and is retiring it: custom styles become skills invoked with a slash command (support.claude.com, "Styles are moving to skills"). Substrate already has slash commands.

## Open, for the Architect

- Placement: the bar line or chips.
- How a change enters the prompt: way 1 or way 2.
- Whether guidance (`harness_level`) also changes mid-session; today only length and tone have a rewrite.
- A measurement before choosing between ways 1 and 2: the K296 live test already counts reply words (terse 115, full 288 on kimi); the same test can change length mid-session under each way and count the next three replies.
