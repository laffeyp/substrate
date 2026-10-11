# RESEARCH (round 2): how Substrate presents tools, and what it tells each driver

*2026-10-10, round 2. Round 1 (`RESEARCH-2026-10-10-how-substrate-presents-tools.md`) stays as written; this round adds §9, the instruction set Substrate gives its drivers, distilled from this machine's Claude setup, and renumbers the sections after it. Status: research. No Substrate code changed. Inputs: a review written by the `claude -p` driver inside session `s_6aa52a8f0e3b436c8092fd21` ("How Substrate presents tools to its drivers", 2026-10-10), checked claim by claim; the code at `3c0542ac` / `75b3293`; live probes on this machine (Ollama 0.34.1, `claude` 2.1.296, `codex` 0.157.0, `cursor-agent` 2026.09.23); vendor documentation; six papers.*

## 1. The question, and what is already true

The question: how should Substrate present its tools to each driver it supports, which parts of that are one correct practice for every driver, and which are particular to a driver?

Two facts frame the answer.

- **The current setup works.** Sessions on Ollama cloud models and on `claude -p` call tools, get results and answer. The review's session made three tool calls in twenty turns and its driver wrote a twenty-kilobyte report. Nothing below starts from "it is broken".
- **Little of the advice on offer is theory.** Section 3 sorts what Substrate can rely on (engineering theory with a long record), what is measured but narrow (a handful of studies and benchmarks), and what is vendor guidance or folklore. The program in section 7 exists because the second and third kinds have to be checked on Substrate's own drivers before they change code.

A second question came with round 2. This machine carries a worked-out setup for working with Claude: a global CLAUDE.md, an output style, a hook that runs before every message, a writing skill, a reviewer, and a memory of corrections. A session's driver should get none of the operator's local setup and all of a distilled, versioned Substrate version of it, adapted to each model. §9 takes that setup apart.

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

## 9. The instruction set Substrate gives its drivers

### 9.1 The rule

A session's driver reads Substrate's instructions and nothing from the operator's machine. For a CLI agent that means two steps on every call: zero out what the CLI would load by itself (§5 D3), then inject Substrate's set. For an Ollama model there is nothing to zero out; the set goes in as the system message (`OllamaResponder` already sends one when `system` is set, `adapters/models.py:221–223`) or as session-open fragments.

Measured 2026-10-10 on `claude -p`: with `--tools "" --strict-mcp-config --setting-sources ""` the driver reported neither the operator's CLAUDE.md rule nor the style hook, and the call took 2,849 input tokens. Without `--setting-sources ""` it quoted the CLAUDE.md rule back by path.

The operator's setup on this machine stays as it is. It is the working environment of the person; the Substrate set is the working environment of a session.

### 9.2 What is on this machine

| Source | Size | What it does | Mechanism in Claude Code |
|---|---|---|---|
| `~/.claude/CLAUDE.md` | 8,194 B | acknowledge before acting; research, don't fabricate; adversarial information space; no Claude attribution in git; every output is writing; unaddressed prose; read files whole; reverse explainer | loaded into every session's context |
| `~/.claude/output-styles/plain.md` | 2,655 B | the writing standard: each sentence a fact, particulars over abstractions, short words, varied rhythm, prose before lists, stop when done, hard thing first | replaces the default output style section of the system prompt |
| `UserPromptSubmit` hook | 1 line | "Write like E. B. White and George Orwell. Plain register only. Every sentence carries a fact…" | printed into the context before every user message |
| `skills/dellm/SKILL.md` | 6,429 B | strip the measured machine register (Kobak 2025, Liang 2023, Wikipedia's catalog), then write by craft (Orwell, Strunk & White); four passes | loaded on demand by name |
| `skills/reviewer/SKILL.md`, `agents/reviewer.md` | 7,335 + 7,486 B | a persistent reviewer that checks SDD discipline per turn and per epic | a subagent with its own context |
| `skills/design-theory-pass/SKILL.md` | 6,461 B | refine an approved UI by named perception principles, rendered and measured | loaded on demand |
| project memory (`MEMORY.md`, 43 entries) | — | corrections the operator made over months: plain register, report don't prescribe, green is not proven, no forks, check the box before asserting infra, no "shim", no in-place doc edits, and more | an index loaded each session; entries read on recall |
| `sdd-kit-2/AGENTS.md` | 21,640 B | the SDD method: sprint cards, dual contracts, vocabulary as contract, halts | project instructions |

Substrate's driver guidance today, by comparison: `bundle/methodology.md` (317 B: read tools before calling, read results, correct after a failure, say what you did, stop when verified), `prompts/default.md` (848 B: the record is the source of truth; run code before calling it done; name what you are unsure of), four more role prompts (11,191 B together), and an empty `bundle/per-turn.md`.

### 9.3 Sorting it

Each rule is sorted by who it is for and by what stands behind it. The grades follow §3: E (engineering theory), M (measured, cite given), V (vendor guidance), C (craft tradition), O (operator preference, earned by correction on this machine).

**A. Working discipline: every driver, every task.**

| Rule | Grade | Note |
|---|---|---|
| Verify before claiming; say what was checked and how | E, M | the record makes this checkable; the driver's own review (§3.4) failed exactly here |
| A passing check is not proof; read what it verified | O | memory "green is not proven"; the K265 skip episode |
| Absence of evidence is not evidence of failure; one probe settles it | O | the review's "zero ToolCalls means calls fail" |
| A tool failure is an observation; read the error, change the call | E | already in `methodology.md` and `default.md` |
| Run code before calling it done | O | already in `default.md` |
| Do the small work rather than asking the user to | O | the hook's last line |
| Report facts about state; do not invent recommendations | O | memory "report, don't prescribe" |
| When unsure, name the uncertainty, then act; stop and say so when a decision is the user's | O, E | `default.md`; SDD halts |
| Treat web and vendor claims as claims; name the genre of each source | O | CLAUDE.md "adversarial information space" |

**B. The writing standard: every driver that writes for a person.**

| Rule | Grade | Note |
|---|---|---|
| Each sentence carries a fact; particulars over abstractions | C | Orwell, Strunk & White |
| Short words, concrete nouns, active verbs, a named actor | C | same |
| Vary sentence length; prose before lists; bold only where something nearby is plain | C, M | rhythm variance is the measured human property (dellm Layer 1) |
| Hard thing first; stop when the point is made | C | |
| Address no one; third person or bare assertion | O | CLAUDE.md "unaddressed prose" |
| Avoid the measured machine register (delve, robust, pivotal…; participle summary tails; bow-tie endings) | M as detection, untested as instruction | Kobak et al. measured the words in text; telling a model to avoid them is a separate claim (§11) |
| Banned words ("shim", "schoolroom") | O | personal |

**C. Operator profile: true of this operator, not of every user.** Staff engineer, wants density and no hand-holding; no market framing; no Claude attribution in git; read files whole when told to read. These belong in the operator's layer (§9.4), not in Substrate's default.

**D. Claude Code mechanics: do not transfer.** `ListAgents`, `SendMessage`, the Skill tool, `ToolSearch`, the Artifact tool, the memory directory, the rule against forks and subagents. Each names a feature Substrate's drivers do not have. Two have Substrate counterparts that need their own wording: subagents map to `delegate`, and memory maps to the record.

**E. Project methodology: per repository.** The SDD kit, Substrate's vocabulary rules, sprint cards. These belong to the workspace a session opens on, not to every session.

**F. Task skills: loaded when the task calls for them.** `dellm` (rewrite prose), the reviewer (check a change against SDD), `design-theory-pass` (UI). Each is several kilobytes and useful for one kind of task.

### 9.4 Where each part lives in Substrate

Substrate already has the layers; most are empty or thin.

| Part | Substrate home | Exists today | Change |
|---|---|---|---|
| A, working discipline | the shipped `default` role prompt (`prompts/default.md`), resolved at the shipped layer of `roles.py` | 848 B, overlaps A in part | rewrite from table A |
| B, writing standard | a shipped `style` fragment, session-open, every session | — | new; distilled from `plain.md`, the hook and dellm Layer 2 |
| The per-message reminder | the session's `per_turn` text (precedence 10, every model call) | field exists; `bundle/per-turn.md` is empty | one line, the hook's equivalent |
| C, operator profile | the user layer, `~/.substrate/prompts/` (`roles.py` layer 2) | mechanism exists; nothing shipped | the operator writes it; Substrate never ships one |
| E, project methodology | the repo layer, `<workspace>/.substrate/prompts/` (`roles.py` layer 1), or a bundle | mechanism exists | per project |
| F, task skills | bundles (`extends` chains, K265 now keeps every link) or roles chosen at session open; later, a tool that reads a named guide on demand | bundles and roles exist | one bundle per skill; the on-demand tool is open |
| Loop rules | `bundle/methodology.md` | 317 B | keep for bare models; shorten for CLI agents that bring their own |

Every one of these reaches the model as a `PromptFragment` with a `source` and a `provenance`, so the record names which guidance, at which path, produced each prompt. Changing the guidance is then a change to versioned files in the repo, checked like code; a reader of an old record can see which version the model read. That is the SDD fit: guidance is an artifact on the record, not invisible context.

### 9.5 Fitting the set to the model

One set, three renderings, chosen from the §2 inventory:

| Tier | Drivers | Context | Rendering |
|---|---|---|---|
| CLI agents | `claude`, `codex`, `cursor-agent` | large | zero out (§5 D3); A, B and the reminder through the CLI's system-prompt channel where it has one (`claude --append-system-prompt`); loop rules short, since their own harness covers loop discipline; Substrate's tools named as the only ones that count |
| Large open models | kimi, glm, deepseek-v4-pro, nemotron | 200k–1M | A, B, loop rules and the reminder in full, as the system message or session fragments |
| Small local models | `qwen2.5` 7B, `llama3.2:1b`, `llama3:8b`, `deepseek-r1:8b` | 8k–131k | a compressed set under a byte budget: the operator's CLAUDE.md alone is 8,194 bytes, about 2,000 tokens, a quarter of `llama3:8b`'s 8,192-token window; A and B in about ten lines; no skills |

Two conflicts surface when the sources meet, and the Substrate set has to settle them in its own wording:

- **Acknowledge-before-acting against the call format.** CLAUDE.md asks for a one-line reflection at the start of every turn; Substrate's text mode asks for the JSON call alone. In a Substrate session the reflection belongs to answers addressed to the user, not to tool-call steps. With C6 (a call recognised only at the start of the reply, §4) the wording must say so, or every reflected call stops parsing.
- **Do the small work against stop-and-ask.** The hook says do the work; SDD says halt when a decision is the user's. The set needs the line between them in one sentence: act on anything the record can settle; stop on anything only the user can decide.

### 9.6 How it is proven

The §7 program carries it. The instruction set is one more presentation variable, A/B tested on each driver on the seven-task set, with three metrics added:

- claims made without a check in the same turn (a claim about the workspace or the record with no tool call or record read behind it);
- unrecorded side effects (already in §7);
- writing-register markers per thousand words of answers to the user (the dellm Layer 1 catalog), reported, not optimised: it measures register, not clarity.

Until a version beats the current guidance on a driver, that driver keeps the current guidance. The operator's own setup is the strongest prior available, built from months of corrections on real work; it is still a prior.

## 10. Order of work this suggests

Defects first, since each is a fix on evidence: D1 (capability decides mode), D2 (retired tags), D3 (isolation flags for `claude`, the nearest equivalents for `codex` and `cursor-agent`), D4 (call position), D5 and D6 (one labelled tool list), D9 (test tools out of the live suite), D7 (structured CLI usage), D8 (record thinking). Then C1 (one definition per tool), which every later change builds on. Then the instruction set of §9: zeroing the operator's setup comes with D3; the Substrate set itself is versioned text, cheap to write and expensive to prove, so it enters behind the §7 measurements. The "measure" items (C7, C8, C9, role-tagged Ollama history, natural-language or code call formats) wait for the §7 task set to exist in the assay harness.

## 11. Open questions

- Does `--setting-sources ""` keep subscription login in every case, and does it also drop project-level settings Substrate might want?
- Does removing a CLI agent's own tools make it better or worse at Substrate's text convention?
- Does recording Ollama `thinking` change replay determinism or record size enough to matter?
- Should a session's presentation (mode, flags, notes) be part of `SessionStarted`, so a reader knows what the model was shown without re-deriving it?
- Which of the writing rules in §9.3 change what a model produces when they are given as instructions? The measured catalog (Kobak et al.) detects machine register; nobody has shown that telling a model to avoid the words produces clearer prose.
- How should a session started before a guidance change pick up the new version? Session-open fragments are written once (K265), so a running session keeps the guidance it opened with. The review's session shows the cost: it opened on a build before the 2026-10-08 role fix (lens F316) and never received the `default` role prompt.

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
- This machine's Claude setup, read 2026-10-10: `~/.claude/CLAUDE.md` (8,194 bytes), `~/.claude/output-styles/plain.md` (2,655), the `UserPromptSubmit` hook in `~/.claude/settings.json`, `~/.claude/skills/dellm/SKILL.md` (6,429), `~/.claude/skills/reviewer/SKILL.md` (7,335), `~/.claude/agents/reviewer.md` (7,486), `~/.claude/skills/design-theory-pass/SKILL.md` (6,461), the project memory index (43 entries), `sdd-kit-2/AGENTS.md` (21,640).
- Substrate's current driver guidance: `topologies/session/bundle/methodology.md` (317 bytes), `bundle/per-turn.md` (empty), `topologies/session/prompts/default.md` (848) and four other role prompts (11,191 together), `topologies/session/roles.py` (three-layer resolution).
- Kobak, D. et al., excess vocabulary in LLM-era text, *Science Advances* 2025 (arXiv:2406.07016); Liang, W. et al., detector false positives on non-native writers, *Patterns* 2023 (as cited in the dellm skill; not re-read for this round).
