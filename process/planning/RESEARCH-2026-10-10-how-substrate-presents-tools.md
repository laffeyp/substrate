# RESEARCH: how Substrate presents tools to each driver

*2026-10-10. Status: research. No Substrate code changed. Inputs: a review written by the `claude -p` driver inside session `s_6aa52a8f0e3b436c8092fd21` ("How Substrate presents tools to its drivers", 2026-10-10), checked claim by claim; the code at `3c0542ac` / `75b3293`; live probes on this machine (Ollama 0.34.1, `claude` 2.1.296, `codex` 0.157.0, `cursor-agent` 2026.09.23); vendor documentation; six papers.*

## 1. The question, and what is already true

The question: how should Substrate present its tools to each driver it supports, which parts of that are one correct practice for every driver, and which are particular to a driver?

Two facts frame the answer.

- **The current setup works.** Sessions on Ollama cloud models and on `claude -p` call tools, get results and answer. The review's session made three tool calls in twenty turns and its driver wrote a twenty-kilobyte report. Nothing below starts from "it is broken".
- **Little of the advice on offer is theory.** Section 3 sorts what Substrate can rely on (engineering theory with a long record), what is measured but narrow (a handful of studies and benchmarks), and what is vendor guidance or folklore. The program in section 7 exists because the second and third kinds have to be checked on Substrate's own drivers before they change code.

So the work splits in two. **Defects** are things the code does wrong today, found by probing, fixed on evidence alone (section 5). **Practices** are changes that published guidance favours; each is a hypothesis to measure before it is adopted (sections 4 and 7).

## 2. The drivers Substrate supports

Substrate reaches a model through one of two responder classes. The session's model step chooses how to present tools by one test (`session/__init__.py:369–370`): does the responder class have an `achat_tools` method? `OllamaResponder` does, so every Ollama tag runs in **native** mode (schemas in Ollama's `tools` field). `CliResponder` does not, so every CLI runs in **text** mode (a prose tool list and a "reply with one JSON object" directive).

What each driver is, probed 2026-10-10:

| Driver | How Substrate calls it | Brings its own agent harness? | Ollama `capabilities` | Context | Mode today |
|---|---|---|---|---|---|
| `kimi-k2.7-code:cloud`, `kimi-k2.6:cloud`, `kimi-k3:cloud` | Ollama `/api/chat` | no | vision, thinking, completion, tools | 262k / 262k / 1M | native |
| `glm-5.2:cloud`, `glm-5.1:cloud` | Ollama | no | thinking, completion, tools | 1M / 203k | native |
| `deepseek-v4-pro:cloud` | Ollama | no | completion, tools, thinking | 1M | native |
| `nemotron-3-super:cloud` | Ollama | no | completion, thinking, tools | 262k | native |
| `qwen2.5:7b-instruct`, `qwen2.5-coder:7b`, `llama3.2:1b` | Ollama (local) | no | completion, tools | 33k / 33k / 131k | native |
| `deepseek-r1:8b` | Ollama (local) | no | tools, thinking, completion | 131k | native |
| `llama3:8b`, `llama3:latest` | Ollama (local) | no | **completion only** | 8k | native (**fails**, §5 D1) |
| `deepseek-v4-flash:cloud`, `qwen3-coder:480b-cloud` | Ollama | — | **retired** (§5 D2) | — | offered in the picker |
| `claude` | `claude -p <prompt>` | **yes** (Bash, Read, Edit, Write, Grep, MCP) | — | — | text |
| `codex` | `codex exec <prompt>` | **yes** (shell, file edits, MCP) | — | — | text |
| `cursor-agent` | `cursor-agent -p <prompt>` | **yes** ("has access to all tools, including write and shell") | — | — | text |
| `deterministic` | in-process | no | — | — | text (test double) |

`gemini` 0.59.0 is installed but has no entry in `KNOWN_CLI_ADAPTERS`, so Substrate does not offer it.

The column that matters most is the fourth. The `achat_tools` test asks *can Substrate pass schemas through an API*. What decides what the prompt must say is *does the driver already run its own tool loop*. For a bare model Substrate is the whole harness: the tool list, the call format and the loop rules are its entire operating manual. A CLI agent arrives with its own tools and loop; Substrate's prompt lands on top of them.

## 3. What theory there is

### 3.1 Theory Substrate can rely on (engineering, long record)

These govern Substrate's side of the boundary: what is recorded, who owns state, how components agree. They are not claims about model cognition, and none of them is in doubt here.

- **Event sourcing and an append-only log** (Fowler, 2005; the kernel's record). The record is the system of truth; every state is a fold over it. This is why a tool call that does not reach the record does not exist for Substrate, whatever it did on disk.
- **Single source of truth** for a definition. A tool's name, arguments and description should live in one place and every presentation should be generated from it. Today the prose (`describe`) and the schema (`_TOOL_SCHEMAS`) are kept by hand in two places (`tool_loop/tools.py:683`, `:692`).
- **Design by contract** (Meyer, 1988) and SDD's vocabulary-as-contract. The ToolCall / ToolResult / ModelReply / Returned shapes are the contract between the model step, the tools and every reader. A driver-specific presentation may change the bytes the model reads; it may not change the events.
- **Errors as values.** A failing tool returns `ToolResult(ok=false, error=…)`; the loop continues. This is standard practice in agent loops and in Substrate's tool seam.
- **Separation of concerns and least privilege.** A driver should get the tools the session grants and nothing else. The probes in §5 show the CLI drivers getting much more.

### 3.2 Measured, but narrow

- **ReAct** (Yao et al., arXiv:2210.03629, ICLR 2023): interleaving free-text reasoning with actions beats acting alone on the tasks tested. It is the empirical root of "let the model say why before it calls". It is a finding about prompts on 2022 models, not a theory.
- **Format restrictions cost reasoning** (Tam et al., arXiv:2408.02442, EMNLP 2024 Industry). The largest losses came from constrained decoding (JSON mode); format-restricting instructions cost less; classification tasks sometimes gained. Substrate's text mode is a format instruction, not constrained decoding.
- **Natural-language tool selection** (Johnson, Pain and West, arXiv:2510.14453; replication by Somma, Plante and Premji, arXiv:2607.03953). Replacing JSON calls with natural-language tool selection raised accuracy by 18.4 and 14.9 points. Both test *which tool to pick* in customer-service and mental-health dialogues; neither tests argument-heavy tools like `bash` or `edit_file`. Both come from small companies. The replication found the advantage "smaller or reversed" for heavily tuned frontier models.
- **Programmatic tool calling** (Patel et al., arXiv:2608.06370): typed Python stubs matched or beat JSON calls for 11 of 14 models on a 309-entry BFCL v4 subset. This favours code, not natural language.
- **Position in long context** ("Lost in the Middle", Liu et al., arXiv:2307.03172, TACL 2024): models use information at the start and end of a long context better than in the middle. Relevant to where the tool list and the current message sit in a 50 KB prompt.

The one argument with a mechanism behind it is **distribution match**: a post-trained model has seen its vendor's tool format millions of times in training, so that format is the one it executes best. It explains why native schemas help tuned frontier models and why small or untuned models gain from looser formats. It predicts, and does not prove, that each driver's best presentation is close to its own training format.

### 3.3 Vendor guidance

Authoritative on mechanism, silent on comparison, and written about the vendor's own product.

- Anthropic, "Define tools": detailed descriptions are "by far the most important factor in tool performance"; "aim for at least 3–4 sentences for each tool description"; return "only high-signal information"; Claude often writes text before a `tool_use` block, and that text is part of the assistant message.
- Anthropic, "Writing effective tools for agents" (Aizawa, 11 Sep 2025): "Tool implementations should take care to return only high signal information"; "For Claude Code, we restrict tool responses to 25,000 tokens by default."
- Ollama, "Tool calling": the assistant message, with its `tool_calls`, `content` and `thinking`, goes back into the message list; each result goes back as `{"role": "tool", "tool_name": …, "content": …}`; one reply may hold several calls.

### 3.4 What the driver's own review contributed

The review in session `s_6aa52a8f…` was written by Claude about the harness running it. Its facts mostly checked out (§6). Its causal story did not: it blamed the operator's style rules for its own untested claims, and it called the tool list injected text when the list is the user's own prompt. A driver's account of itself is evidence to check, like any other source.

## 4. The core: what every driver gets

Each item names its basis (§3) and how it bends to Substrate. "Measure" marks a practice to test in the §7 program before it changes the default.

| # | Practice | Basis | Substrate constraint | Status |
|---|---|---|---|---|
| C1 | One definition per tool (name, typed arguments, a 3–4 sentence description); the schema, the prose list and any other rendering are generated from it | single source of truth; Anthropic docs | the definition is code, versioned with the tool | build |
| C2 | The tool list appears once per prompt, under a heading, and never as the prompt's first line | measured on the record (§5 D5, D6) | `PromptComposed.text` stays the exact input | build |
| C3 | Only Substrate's tools are live; a driver's own tools are removed or fenced | least privilege; the record is the truth | a call that bypasses ToolCall breaks every reader | build where the CLI allows (§5 D3) |
| C4 | The driver is isolated from the operator's personal agent setup (memory files, hooks, permission modes, MCP servers) | least privilege; reproducibility | a session's behaviour must not depend on who is logged in | build (§5 D3) |
| C5 | Capability decides mode, per model, from the provider's own report | the provider's report is the ground truth | the mode is recorded in SessionStarted so a reader knows it | build (§5 D1) |
| C6 | A call is recognised only where the call format says it sits (the start of the reply, or the native channel), never anywhere in the text | parser correctness | a quoted example must not run a tool | build (§5 D4) |
| C7 | The model's own words beside a call return to it in later steps | ReAct; Anthropic and Ollama message shapes | the record already keeps them (`ModelReply.text`, K262 § M.2) | measure |
| C8 | Old tool results are shortened in the rendered history; the record keeps them whole | Anthropic "high-signal"; context budget | rendering is a projection of the record, never a change to it | measure |
| C9 | The model may write reasoning before its call | ReAct; Tam et al. | the reply text is recorded as ModelReply.text | measure |
| C10 | Usage is the provider's count wherever the provider reports one | K262; measurement | `ModelReply.usage.estimated` says which | build (§5 D7) |

What stays as it is, for every bare model: Substrate's loop rules in `methodology.md`, the wrap-up directive, the three-failure cap, errors as observations, and Substrate's ownership of history. History stays with Substrate because the record is the one artifact every driver and every reader shares; `plan_window` trims it per driver and records `TranscriptCompacted`, and `delegate` passes children seq-range slices of it. A driver that keeps a private history (`claude --resume`, `codex resume`, `cursor-agent --continue`) would break both.

## 5. Defects found by probing (2026-10-10)

Each was observed on this machine. None depends on a theory.

**D1. Ollama models without tool support fail every call.** `llama3:8b` reports only `completion`. Substrate sends it a `tools` array; Ollama answers `{"error":"… llama3:8b does not support tools"}`, so every model step of a session with tools fails. The daemon already probes `/api/show` capabilities to decide `think` per model (UI sprint 085, `server.py`); it does not probe `tools`. Fix: choose text or native mode from the probed capability, and record the mode.

**D2. The picker offers retired models.** `deepseek-v4-flash:cloud` ("retired at 2026-09-25") and `qwen3-coder:480b-cloud` ("retired at 2026-07-15") are still installed tags; `/api/show` returns the retirement error. `_agent_models` lists every tag from `/api/tags` without checking. Fix: drop tags whose `/api/show` returns an error, or mark them.

**D3. `claude -p` runs with the operator's whole agent setup.** Substrate runs `["claude", "-p", <model flag>, <prompt>]` (`server.py:712`, `_cli_command`) with no isolation flags. Measured with a two-line test prompt:

| Flags | Input tokens | Output tokens | What the model reported |
|---|---|---|---|
| `--tools ""` | 78,380 | 5,997 | 189 callable tools from five MCP servers |
| `--tools "" --strict-mcp-config` | 6,709 | 108 | no tools; the operator's CLAUDE.md rule present |
| `--tools "" --strict-mcp-config --setting-sources ""` | 2,849 | — | no CLAUDE.md rule, no style hook |

Without flags the driver also has its built-in Bash, Read, Edit and Write, and `~/.claude/settings.json` sets `"defaultMode": "auto"`, so they run without asking: the review's 20,791-byte draft was written by the built-in Write and appears nowhere on the record. `codex exec` has no flag that removes its tools; it has `--sandbox read-only`, `--ignore-user-config`, `--ignore-rules` and `--ephemeral`. `cursor-agent -p` has no tool-removal flag; `--mode ask` is read-only. Untested: whether `--setting-sources ""` keeps the subscription login (the probe above ran on it and succeeded), and whether removing the driver's tools changes how well it follows Substrate's text convention.

**D4. A quoted example can run a tool.** `parse_tool_call` falls back to `_loads_obj(content)`, which takes the first balanced JSON object anywhere in the reply (`tool_loop/tools.py:802`). A final answer that quotes `{"name": "bash", "arguments": {…}}` while explaining the format is executed. The same rule is what lets a reply that opens with a sentence and then gives the JSON still work.

**D5. The tool list is sent twice.** In the seq-324 prompt of `s_6aa52a8f…` (49,748 bytes) the 2,991-byte tool list appears once from the `tools_suite` fragment and once under "Tools you MAY use:". The committed `daily` CI record shows the same with two tools. Pre-K261 code did the same by design (`tools_suite_producer.py` docstring: "The two coexist by design"); K261 kept the wording.

**D6. A session with no seed opens on a bare tool list.** That prompt's first line is `add(a, b) -> a+b`: the `tools_suite` fragment has precedence 20, before the methodology (50), and has no heading.

**D7. The CLI drivers throw away real usage.** `claude -p --output-format json` returns `usage` (input, cache, output and thinking tokens), `modelUsage` keyed by the real model ID (`claude-opus-5-5`), `duration_ms` and `stop_reason`. `CliResponder` reads plain stdout and records word-count estimates. `codex exec --json` and `cursor-agent --output-format json` offer the same kind of output (fields not yet checked).

**D8. Ollama's thinking is dropped.** Thinking-capable models run with `think=True` by default (UI sprint 085). Ollama returns the reasoning in `message.thinking`; `OllamaResponder` reads only `content`, so the reasoning is neither recorded nor sent back, though Ollama's documentation shows it returned with the assistant message.

**D9. Two test tools ship in every session.** `full_suite` includes `**CALCULATOR`, so `add` and `mul` sit at the top of every live tool list.

## 6. The driver's review, checked

| Claim | Verdict | Evidence |
|---|---|---|
| Mode chosen by `achat_tools` (F1) | true | `session/__init__.py:369–370` |
| Two tool systems, only Substrate's recorded (F2) | true; cause broader (D3) | workspace file with no ToolCall; `defaultMode: auto` |
| Tool list reads as injected text (F3) | false | the list is the `-p` prompt, the user's own turn |
| Layer conflicts are unresolvable (F4) | overstated | the parser accepts prose then JSON (D4); the commit trailer never arose |
| Reasons beside a call dropped (F5) | true, by design in K262 | `transcript.py:224`; vocabulary § M.2 |
| Old results resent in full (F6) | true | `transcript.py:231–235` renders `output` whole |
| Environment facts go stale (F7) | mostly a one-off | the session spans about six hours and at least three app builds |
| One-line descriptions (F8) | true | `ollama_tools` uses `describe` |
| `add` and `mul` ship (F9) | true | D9 |
| "Nothing checks the arguments" (§6) | false | unknown argument names return an error (UI sprint 097); types are not checked |
| Turn 0's `claude-opus-4-8` is unexplained | likely explained | `claude-opus-4-8` is a curated pin, `server.py:727` |
| R11, serve tools to Claude Code over MCP | rejected | Claude Code would run its own multi-call loop inside one Substrate step; the calls would bypass the record |

## 7. The research program

One protocol, run per driver, on a schedule.

**When it runs.** On adding a driver; on a CLI version change (`claude`, `codex`, `cursor-agent`); on an Ollama model entering or leaving the roster; before any change to a C-item marked "measure".

**Step 1, inventory (no model calls).** Version; `--help` flags for tool removal, settings isolation, output format, system-prompt injection and session persistence; `/api/show` capabilities and context; retirement status. Output: one row of the §2 table, dated.

**Step 2, presentation probe (one call each).** With the planned flags: what tools the driver says it can call; whether the operator's memory file and hooks reach it; input-token overhead of an empty prompt; whether usage comes back structured. Output: one row of the D3 table.

**Step 3, task set.** A fixed suite in the assay harness, run on the deterministic tools workspace:
1. one call with a required argument (`read_file`);
2. paging (`read_file` past the 12 KB cap, then the next offset);
3. an exact-match edit (`edit_file`, where a non-unique match must fail as an observation);
4. a shell command with output (`bash`);
5. a three-step task that needs the result of step 1 in step 3;
6. a turn where the right answer is no tool;
7. a reply that must quote a tool-call example without running it (D4).

**Metrics** (tokens and time only; no money): parseable call rate; correct-tool rate; argument-error rate (unknown names, missing required); unrecorded side effects (files changed in the workspace with no ToolCall); steps to answer; input and output tokens per step; wall time.

**Comparisons.** Each "measure" item is an A/B on the same driver: current presentation against the candidate, the same seeds where the driver accepts one. The benchmarking-power memo applies: ten trials cannot show equivalence; a decision needs the trial count the effect size demands, or the change is called unproven.

**Output.** One dated profile per driver under `process/planning/` (`PROFILE-<date>-<driver>.md`): inventory, probe, task results, and which presentation it gets. The profiles are what the per-driver code reads from, as a table in the responder or a manifest, not as prose.

## 8. Per-driver profiles: idiosyncrasies and special abilities

**Bare Ollama models with tools** (kimi, glm, deepseek-v4-pro, nemotron, qwen2.5, llama3.2, deepseek-r1).
- *Idiosyncrasies.* `qwen2.5-coder` puts a call as JSON in `content` rather than `tool_calls` (handled by `parse_tool_call`). `llama3.2:1b` drops required arguments when the prose list carries a framed header (`tools_suite_producer.py` docstring, pre-K263). Thinking models spend their output budget on `thinking` unless `think` is set (UI sprint 085).
- *Special abilities.* Several calls in one reply; a `thinking` field that can be recorded and returned (D8); role-tagged messages (`assistant` with `tool_calls`, then `tool` results) instead of one flat user string.
- *Open.* Whether role-tagged history beats the flat transcript on the §7 task set. Ollama's own loop example uses it; nothing has measured it on Substrate's tools.

**Ollama models without tools** (`llama3:8b`).
- Text mode, the same convention `CliResponder` uses today. Fix D1 first.

**Claude Code (`claude -p`).**
- *Idiosyncrasies.* Runs a full agent per call, with its own system prompt (about 2.8k input tokens at minimum, measured), tools and permission modes; loads the operator's CLAUDE.md, hooks and MCP servers unless told not to; the prompt is one argv string.
- *Special abilities.* `--tools ""`, `--strict-mcp-config`, `--setting-sources ""` (isolation, D3); `--append-system-prompt` puts Substrate's framing at system level, where it carries more weight than text inside the user turn; `--output-format json` returns real usage and the real model ID (D7); `--model` pins the version.
- *Candidate presentation.* Isolation flags on; a system-level note that the tools listed are Substrate's and are called by replying with the JSON object; text mode otherwise unchanged. To measure: whether the note changes the parseable-call rate.

**Codex (`codex exec`).**
- *Idiosyncrasies.* No flag removes its tools; shell commands run under a sandbox policy.
- *Special abilities.* `--sandbox read-only` (fences its own tools so they cannot change files); `--ignore-user-config` and `--ignore-rules` (isolation); `--ephemeral` (no session files); `--json`; `--output-schema <FILE>`, which may constrain the final message to a JSON schema and so enforce the call shape. Untested.

**Cursor agent (`cursor-agent -p`).**
- *Idiosyncrasies.* `-p` "has access to all tools, including write and shell"; no tool-removal flag.
- *Special abilities.* `--mode ask` (read-only); `--output-format json`; `--model` with bracketed parameters; `--workspace`.

**Gemini CLI.** Installed (0.59.0), not in the catalog. Inventory before adding.

**Deterministic.** The test double; text mode. Its behaviour is the CI baseline, not a driver to tune.

## 9. Order of work this suggests

Defects first, since each is a fix on evidence: D1 (capability decides mode), D2 (retired tags), D3 (isolation flags for `claude`, the nearest equivalents for `codex` and `cursor-agent`), D4 (call position), D5 and D6 (one labelled tool list), D9 (test tools out of the live suite), D7 (structured CLI usage), D8 (record thinking). Then C1 (one definition per tool), which every later change builds on. The "measure" items (C7, C8, C9, role-tagged Ollama history, natural-language or code call formats) wait for the §7 task set to exist in the assay harness.

## 10. Open questions

- Does `--setting-sources ""` keep subscription login in every case, and does it also drop project-level settings Substrate might want?
- Does removing a CLI agent's own tools make it better or worse at Substrate's text convention?
- Does recording Ollama `thinking` change replay determinism or record size enough to matter?
- Should a session's presentation (mode, flags, notes) be part of `SessionStarted`, so a reader knows what the model was shown without re-deriving it?

## Sources

- Substrate at `3c0542ac` (kernel) and `75b3293` (console): `topologies/session/__init__.py`, `session/transcript.py`, `adapters/models.py`, `tool_loop/tools.py`, `substrate-ui/server.py`.
- Session record `~/.substrate/sessions/s_6aa52a8f0e3b436c8092fd21/record`, PromptComposed seq 324.
- Probes on this machine, 2026-10-10: `ollama` 0.34.1 `/api/show` and `/api/chat`; `claude` 2.1.296 (`--help`, three `-p --output-format json` calls); `codex exec --help` 0.157.0; `cursor-agent --help` 2026.09.23.
- Anthropic, "Define tools", https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools
- Aizawa, K., "Writing effective tools for agents — with agents", Anthropic, 11 Sep 2025, https://www.anthropic.com/engineering/writing-tools-for-agents
- Ollama, "Tool calling", https://docs.ollama.com/capabilities/tool-calling
- Yao, S. et al., "ReAct: Synergizing Reasoning and Acting in Language Models", arXiv:2210.03629, ICLR 2023.
- Liu, N. F. et al., "Lost in the Middle: How Language Models Use Long Contexts", arXiv:2307.03172, TACL 2024.
- Tam, Z. R. et al., "Let Me Speak Freely?", arXiv:2408.02442, EMNLP 2024 Industry.
- Johnson, R. T., Pain, M. D., West, J. D., "Natural Language Tools", arXiv:2510.14453, 2025.
- Somma, A., Plante, I., Premji, F., NLT replication across 14 models, arXiv:2607.03953, 2026.
- Patel, I., Sen, S., Lumer, E., Subbiah, V. K., "The Bitter Lesson of Tool Calling", arXiv:2608.06370, 2026.
- Fowler, M., "Event Sourcing", 2005; Meyer, B., *Object-Oriented Software Construction*, 1988 (design by contract).
