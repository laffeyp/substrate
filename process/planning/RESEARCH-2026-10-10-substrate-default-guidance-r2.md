# RESEARCH (round 2): this machine's Claude setup as Substrate's default guidance

*2026-10-10, round 2. Round 1 (`RESEARCH-2026-10-10-substrate-default-guidance.md`) stays on disk. Round 2 adds what round 1 skipped:*

- *the delivery system Substrate already has, read against the product spec (§7, §7a, §7b, §14, §2a), the tech spec (§1.6.5, §9) and the design spec (2026-08-31), then against the code and two live records;*
- *the full residue after zeroing;*
- *the driver's own review;*
- *dellm as the one skill to port.*

*Status: research; no code changed.*

## 1. The task

This machine's Claude setup works because Claude Code delivers fixed texts to the model at fixed moments, in fixed formats, through fixed channels. Substrate replicates that delivery inside its own abstractions, so every model it runs gets the same guidance at the same moments, and every delivery is an event on the record. When Substrate runs Claude, it clears out the machine's own delivery first. The setup on this machine stays as it is.

Everything is built in except one piece, the `dellm` skill. That one is loaded only when someone asks for it. Every model class gets its own version of it, and it applies to any text. The machine's other skills are not part of this work.

## 2. What Claude Code delivers, when, and how

Sources: Claude Code's hooks, output-styles, memory and skills pages, read 2026-10-10; the reminders as they arrive in this session's own context; two zeroing probes (§5).

| Text | Size | Channel | When | Format |
|---|---|---|---|---|
| `~/.claude/output-styles/plain.md` (`keep-coding-instructions: true`) | 2,655 B | system prompt, after Claude Code's own sections, under `# Output Style: Plain` | every request ("Claude Code sends the active style's instructions with every request") | the file body |
| Style reminder | 1 line | system reminder | repeated during the session, after tool results and user messages (observed) | "Plain output style is active. Remember to follow the specific guidelines for this style." |
| `~/.claude/CLAUDE.md` | 8,194 B | user message after the system prompt ("CLAUDE.md content is delivered as a user message after the system prompt") | at launch; re-read from disk and re-injected after compaction | system reminder opening "Codebase and user instructions are shown below. Be sure to adhere to these instructions. IMPORTANT: These instructions OVERRIDE any default behavior and you MUST follow them exactly as written.", then "Contents of `<path>` (user's private global instructions for all projects):" and the file |
| `MEMORY.md` | 10,948 B, 43 entries | the same reminder, after CLAUDE.md | at launch; first 200 lines or 25 KB | "Contents of `<path>` (user's auto-memory, persists across conversations):" and the file |
| Memory topic files | one per entry | tool result | on demand, through `Read` | the file |
| `UserPromptSubmit` hook | 318 B | system reminder "alongside the submitted prompt" | every submitted prompt | "UserPromptSubmit hook success: STYLE: Write like E. B. White and George Orwell. …", directly after the prompt text |
| `dellm` skill | 6,429 B | listing in context; body as a message | listing always; body when the user types `/dellm` or Claude calls the Skill tool, then it "stays there across later turns" | listing: name and description, capped at 1,536 characters; body: the rendered `SKILL.md` "as a single message" |
| Environment block | about 1 KB | system prompt | every request | working directory, git yes or no, platform, shell, OS version, a rule on untrusted downloads, model name and ID, knowledge cutoff, a token-budget line, today's date |
| Environment update | a few lines | system reminder | when the working directory changes (observed) | "# Environment update", then the new and old directory |
| Account e-mail | 1 block | system reminder on the user turn | every request | "As you answer the user's questions, you can use the following context: # userEmail The user's email address is …", read from the account `claude` is logged in with |
| Commit attribution | 1 block | system reminder | interactive sessions (observed in this session; absent from both zeroed `-p` probes) | "End git commit messages with: Co-Authored-By: Claude …", which CLAUDE.md forbids |

Five channels carry all of this:

1. **System**, on every request: the style and the environment.
2. **One user block at session open**: CLAUDE.md and the memory index, re-sent after compaction.
3. **Beside each message**: the hook line, the style reminder during tool work, and an environment update when something changes.
4. **On demand**: the `dellm` body and memory topic files.
5. **Account context**: the e-mail.

## 3. What Substrate already has

### 3.1 The design, in the three specs

The product spec's §7 delivers context in four layers:

- a baseline auto-inherited by child sessions;
- a session baseline in a git repo: repo root, branch, `README.md` head and `git diff HEAD`;
- an explicit context slice;
- standing sub-agent accretion.

§7a stores the text in four places on disk:

1. shipped role prompts;
2. `~/.substrate/prompts/`;
3. `<repo>/.substrate/context.md` and `<repo>/.substrate/prompts/`;
4. application seed prompts.

§7b packages the text a user reaches for as a bundle with five categories: corpus, methodology, "personality / voice", per-turn text and retrieval. A bundle is a directory of `methodology.md`, `personality.md`, `per-turn.md`, `corpus/` and `bundle.toml`, and it composes through `extends`.

§14 maps Claude Code onto these:

- CLAUDE.md maps to `context.md` plus the prompt layers.
- Hooks map to "triggers on record events".
- Claude Code's system prompt maps to "session seed assembled from role prompt + project context + task + auto-baseline".

Both specs describe the per-turn slot in Claude Code's terms. The product spec §7b says: "Claude has hooks that inject a fixed string into every turn … `per-turn.md` … prefix every UserMessage before threading. Silent to the eye, visible in the record." The tech spec §1.6.5 says the daemon "prepends it in `UserMessage.assembled_prompt`", and fixes the seed order as personality, role, methodology, project context, seed text, baseline.

The design spec (2026-08-31) makes the prompt line the router. Typing `/` lists the real slash inventory, and `/workspace`, `/name`, `/isolate` and `/bundle` queue parameters for the session they create.

### 3.2 What the code does

The pieces in place:

- **Roles.** `roles.py` resolves a role file through `<repo>/.substrate/prompts/`, `~/.substrate/prompts/` and the shipped `prompts/`. Five roles ship: `default` (848 B), `planner`, `reviewer`, `tester` and `explainer`. A session names one role, default `default`.
- **Bundles.** `bundles.py` loads a bundle's three prose slots, `methodology`, `personality` and `per_turn`. Each slot is a file or a folder. User bundles override shipped ones. Five bundles ship: `session` and four application bundles. A session gets the `session` bundle unless the caller passes another (`server.py`, sprint 054).
- **Prompt fragments.** Since the prompt-composition arc (sprints 058–066, then K263), the `session_prompt` producer writes each session-open source once as a `PromptFragment` with provenance: role at precedence 0, bundle personality at 3, tools suite at 20, parent context at 30, bundle methodology at 50 and up. `assemble_seed` was deleted in sprint 065; the fragments replaced it.
- **Per-step prompt.** The model step rebuilds the whole prompt on every step: seed, head fragments by precedence, `per_turn` at 10, kept turns, notices, then the tool list and directives. It records the result as `PromptComposed` and sends it as one string in the user role. Ollama receives `messages=[{"role":"user"}]`; the responder's `system` argument is never set by a session. `claude -p` receives the prompt as its last argument.
- **Slash commands.** The UI implements `/exit`, `/model`, `/name`, `/list`, `/interrupt`, `/clear` and `/help` (`web/vm/session_controller.ts`, `slashCommands()`).

The gaps between the specs and the code:

| Designed | Built |
|---|---|
| Session baseline: repo root, branch, README head, git diff; outside a repo, cwd, user and hostname (product §7, tech §1.6.5) | not built; `SessionStarted.baseline` is `{}` in every session |
| `<repo>/.substrate/context.md` in the baseline (product §7a, §14) | not built |
| `per-turn.md` from the bundle, prefixed to every UserMessage (product §7b, tech §1.6.5) | the bundle slot loads (`bundles.py:225`) and never reaches a session. A session's `per_turn` comes only from its manifest (default `""`, set by PATCH) and renders in the head at precedence 10, at the top of the prompt. `UserMessage.assembled_prompt` is `""` since K261. |
| Bundles compose through `extends` (product §7b) | a bundle cannot extend a shipped bundle: `resolve_extends` passes an explicit root, so `load_bundle` skips its shipped fallback. Tested: a user bundle with `extends = ["session"]` raises `BundleNotFoundError`. |
| Mid-session `/model`, bundle and per_turn changes | PATCH writes the manifest only; no event reaches the record, and the model is not told |

### 3.3 What the shipped text says

- The `session` bundle: `methodology.md` is 317 B of loop rules (read the tools, read results, correct after a failure, say what you did, stop when verified). `personality.md` and `per-turn.md` are empty.
- The `default` role (848 B): "You are a working companion in a terminal session…"; the record is the source of truth; run code before calling it done; name what you are unsure of.
- The application bundles' `personality.md` files hold one line each: "Blunt. Specific. Name the file and the line every time." (`code_review`); "Rigorous. A verified answer beats a plausible answer." (`best_of_n_verified`); "Collaborative. Read each other's work…" (`pair_coding`); "Thorough. A missing document is a hole in the answer." (`research_sweep`).
- The wizard templates (`templates/bundles/*.tmpl.md`) ask for "personality (blunt? gentle? terse?)". The `writing` template already holds an early version of this machine's setup. Its methodology says "Every sentence carries a fact… Replace each abstraction with the particular it covers for". Its per-turn slot bans "delve, seamless, robust, comprehensive, underscore, showcase, tapestry, journey, landscape".

### 3.4 What a model actually received

The two latest sessions, `s_9eee1b3a…` (`glm-5.2:cloud`) and `s_6aa52a8f…` (`claude`, the review's session), both opened on the `session` bundle and the `default` role. Their records show:

- **Fragments.** Two session-open fragments, bundle methodology and tools suite. No role fragment: both opened on a build from before the 2026-10-08 role fix (lens F316), and session-open fragments are written once.
- **First prompt.** The first `PromptComposed`, at seq 29, is about 3.3 KB. It opens with the line `add(a, b) -> a+b`, then the rest of the tool list, then the methodology and the transcript.
- **Context.** The baseline is `{}` and the seed is `""`. Nothing told either model its workspace path, the date, its own model name, or who it worked for.

## 4. "Personality" is the wrong name

The slot holds instructions for how the model writes. The product spec calls it "Personality / voice. How the model should sound", and every shipped file in it is a writing instruction ("Name the file and the line every time."). No persona sits behind it. Claude Code calls the same thing an output style, and this machine's version is `plain.md`.

The slot is renamed `style`:

- the file becomes `style.md`, or a `style/` folder;
- the field becomes `Bundle.style`;
- the fragment source becomes `PromptSource.BUNDLE_STYLE = "bundle_style"`;
- the wizard slot becomes `style`, with the prompt "How should the model write?".

This is a session vocabulary change. Records written before it keep `bundle_personality`, and readers map it through a legacy table, as `LEGACY_SESSION_END_REASONS` maps `timeout` to `turn_cap`.

## 5. Zeroing the Claude driver, and what remains

`claude -p` runs with `--tools "" --strict-mcp-config --setting-sources "" --disable-slash-commands --system-prompt <Substrate's system text>`. It was probed twice on 2026-10-10, once in a plain directory and once in a fresh git repository:

- **Totals.** 678 and 656 input tokens.
- **Removed.** No CLAUDE.md, memory, hook, output style, skill, MCP tool, built-in tool, Claude Code system section or commit-attribution reminder reached the model. `--system-prompt` replaces Claude Code's system prompt, where `--append-system-prompt` only adds to it.
- **Remaining.** Three things, and no flag removes them:
  1. "You are a Claude agent, built on Anthropic's Claude Agent SDK.", fused to the front of Substrate's system text.
  2. The environment block. Every line of it:
     - "Primary working directory", which is the session workspace, since `CliResponder` runs in it;
     - "Is a git repository";
     - "Platform: darwin";
     - "Shell: zsh";
     - "OS Version: Darwin 25.5.0";
     - the rule on downloaded files and archives as untrusted data;
     - "You are powered by the model named Opus 5.5. The exact model ID is claude-opus-5-5. Assistant knowledge cutoff is June 2026.";
     - "\<total_tokens>15000000 tokens left\</total_tokens>";
     - "Today's date is 2026-10-10.".
  3. The account e-mail reminder. Claude Code reads the e-mail of the claude.ai account the CLI is logged in with and attaches it to the user turn, with the instruction to use it only to identify the user.

The environment block agrees with Substrate's own baseline (§6.3), because both describe the same workspace and date. The e-mail identifies the operator who logged the CLI in. `SessionStarted` records the zeroing flags, so a reader of the record sees that the Claude driver ran without the machine's setup.

## 6. The replication, channel by channel

### 6.1 System channel: the style

Claude Code sends the style in the system prompt on every request. Substrate does the same:

- **Text.** `plain.md`, the CLAUDE.md sections "Every output is writing" and "Unaddressed prose", and the memory's writing rules go into the `session` bundle's `style.md`.
- **Record.** It is written once at session open as `PromptFragment(source=bundle_style)`, with the bundle path as provenance.
- **Channel.** `PromptComposed` gains a `system` field holding the text sent on the system channel, so the record still equals the model's input. `vocabulary.py` gains `SYSTEM_SOURCES = {bundle_style}`.
- **Delivery.** The model step sends `system` through each driver's own channel: `--system-prompt` for `claude -p`, and a `{"role":"system"}` message for Ollama, with `OllamaResponder` taking `system` per call. Every model step rebuilds `PromptComposed`, so the style rides every step, including tool steps.

### 6.2 Session-open user block: the working rules

Claude Code sends CLAUDE.md once, as the first user block, and re-sends it after compaction. Its rules hold whatever the task.

In Substrate the matching slot is the bundle's `methodology`, not the role. A session picks one role at a time: `reviewer`, `planner`, `tester`, `explainer` or `default`. Each role says who the model is for this session, and CLAUDE.md's rules hold under all of them. The working rules go into the `session` bundle's `methodology.md`:

- **From CLAUDE.md:** acknowledge before acting; research, don't fabricate; the adversarial information space; no model attribution in git; read files whole when told to; the reverse explainer.
- **From the memory index:** the working rules.
- **From the 317 B loop rules** already there.

They are delivered under Claude Code's header ("Codebase and user instructions are shown below… These instructions OVERRIDE any default behavior and you MUST follow them exactly as written.").

The `default` role keeps its own job: who the model is (a working companion in a terminal session) and that the record is the source of truth. Its overlap with the methodology (run code before calling it done, say what you did) moves into the methodology, so each rule is written once.

Every model step's head carries the methodology fragment, so compaction cannot drop it. `plan_window` drops old turns, never the head. Methodology now sits at precedence 50, after the tool list (20). It moves to 1, right after the role (0), so the working rules come before the tool list, as CLAUDE.md comes before the conversation.

The application bundles get the same rules by declaring `extends = ["session"]`. That needs `resolve_extends` to fall back to shipped bundles (§3.2). Then a `code_review` session gets the working rules, the style and the per-message line, and then its own methodology on top.

### 6.3 System channel: the environment

Claude Code sends an environment block on every request. The product spec's baseline is Substrate's version of it, designed and never built. It is built here:

- **Computed at session open, into `SessionStarted.baseline`.** The field exists and is empty today. Contents:
  - the workspace path;
  - in a git repo: repo root, branch, commit, `README.md` head (8 KiB) and `git diff HEAD` (32 KiB), per the tech spec;
  - outside a repo: cwd, user, hostname;
  - platform;
  - the driver and its model ID;
  - the date;
  - `<repo>/.substrate/context.md` when it exists.
- **Recorded.** It reaches the model as `PromptFragment(source=baseline)`, a new `PromptSource`, on the system channel. Claude Code puts the same facts in its system prompt.

### 6.4 Beside each message: the hook line and environment updates

Claude Code places the hook line directly after each prompt and adds an environment update when the working directory changes. Both specs already describe the hook's Substrate form. Built:

1. **Source.** The hook line goes into the `session` bundle's `per-turn.md`. A session's `per_turn` defaults to its bundle chain's `per_turn` slot; the manifest value, set by PATCH, overrides it.
2. **Record.** The `session_prompt` producer writes `per_turn` once at session open as `PromptFragment(source=per_turn)`, with the bundle path or `"manifest"` as provenance. `PER_TURN` moves from `TURN_SCOPED_SOURCES` to `SESSION_OPEN_SOURCES`. It is written once and placed many times.
3. **Position.** `compose_model_prompt` renders it directly after the current turn's `USER:` line, where Claude Code puts it. It no longer renders at the top of the prompt. Every model step of the turn carries it there, which also covers Claude Code's repeated style reminder.
4. **Changes.** A PATCH of `driver`, `bundle` or `per_turn` writes a `SessionChanged{field, old, new}` event to the record. The next model step carries one line beside the message, "Environment update: model changed from glm-5.2:cloud to claude.", as Claude Code does when the directory changes. A date rollover writes the same event. This answers the review's F7: environment facts that went stale with no marker.

The specs said "prefix every UserMessage"; Claude Code places the line after the message. Placement after the message is the one built, and session vocabulary records it.

### 6.5 On request: `dellm`

The skill keeps its two Claude Code entry points, each on the record:

1. **The user types `/dellm` in the prompt line.** The text after it, a passage or a file path, becomes the turn's message. The UI's slash table gains `/dellm`. The daemon injects `SkillRequested{name: "dellm"}` onto the session's record, the same path `/interrupt` takes with `InterruptRequested`. A `skill` fragment producer answers with `PromptFragment(source=skill)`, whose provenance names the file and the model class. The fragment stays in every later step's head for the rest of the session, as the body stays in Claude Code's context.
2. **The user asks in words ("de-LLM this paragraph").** The model calls the `skill("dellm")` tool. The `ToolResult` is the body, and it stays in history like any result. The tool's description lists `dellm` with its one-line description, as Claude Code's skill listing does.

Resolution follows the role layers: `<repo>/.substrate/skills/dellm/`, `~/.substrate/skills/dellm/`, then the shipped `topologies/session/skills/dellm/`. Each holds one file per model class (§7). The model applies the skill to any text: a passage in the conversation, a file it reads with `read_file` and rewrites with `edit_file` or `write_file`, or its own draft.

### 6.6 What the record gains

Claude Code shows its deliveries through `/context` in a live session and nowhere after. In Substrate:

- every text reaches the model as a fragment naming its file;
- every step's input is a `PromptComposed` with its `system` part;
- every change mid-session is an event;
- every `dellm` load is a fragment or a `ToolCall` and `ToolResult`.

Any old record shows which version of each text a model read, through which channel, and where in the prompt.

## 7. Each class of model

| Class | Drivers | How chosen | System channel | User turn | `dellm` | Texts |
|---|---|---|---|---|---|---|
| Claude | `claude` | CLI adapter name | `--system-prompt`, zeroed (§5) | the `-p` prompt; Substrate's tool list and call format move to the system channel | slash and tool, text mode | full |
| Large open models | kimi, glm, deepseek-v4-pro, nemotron | Ollama `/api/show` `details.parameter_size` ≥ 30B | `system` message | `user` message | slash and tool, native schema | full |
| Small local models | qwen2.5 7B, llama3.2:1b, llama3:8b, deepseek-r1:8b | `parameter_size` < 30B | `system` message | `user` message | slash; the tool only where the model reports `tools` capability | compressed |

`parameter_size` comes back as `"8.0B"` for `llama3:8b` and `"1042000000000"` for `kimi-k2.6:cloud`; the classifier reads both forms.

For Claude, moving the tool list and call format into the system channel answers the review's F3: the list sat inside the user turn, where Claude Code's training treats instructions as possibly injected. It also answers R1. With `--tools ""` Claude has no tools of its own, so the system text names Substrate's tools as the only ones.

The small class gets its own files in the same slots: `style.small.md`, `methodology.small.md`, `per-turn.small.md` and `skills/dellm/small.md`. The loaders pick them when the class is small. The full set measures about 11.2 KB, roughly 2,800 tokens: style 2,655 B, CLAUDE.md 8,194 B, hook 318 B. The small set fits 800 tokens, a tenth of `llama3:8b`'s 8,192-token window. Each rule becomes one short imperative line, with the examples and reasons dropped. The small `dellm` keeps the Layer 1 word and structure lists and the four passes.

`SessionStarted` records the class.

## 8. The review, answered

| Review finding (`s_6aa52a8f…`, 2026-10-10) | Answer here |
|---|---|
| F2, R1, R2: two tool systems, nothing says which counts | §5 removes Claude Code's tools; §7 names Substrate's tools as the only ones, on the system channel |
| F3: the tool list reads as injected text | §7: the list and call format move to the system channel for Claude |
| F4: four instruction layers in conflict (Claude Code's system prompt, CLAUDE.md, the hook, Substrate's prompt); the commit trailer | §5 removes Claude Code's prompt, CLAUDE.md, the hook and the attribution reminder; Substrate's set is the only layer. The acknowledgement line and the JSON call fit in one reply, line first, then the object, which `parse_tool_call` already accepts |
| F4: `methodology.md` duplicates Claude Code's loop rules | §5: `--system-prompt` replaces Claude Code's loop rules, so Substrate's methodology is the only copy |
| F7, R8: environment facts go stale with no marker | §6.3 baseline; §6.4 `SessionChanged` and the update line |
| §6: unchecked claims stated flat | the methodology carries "research, don't fabricate" and "name your evidence" in the same block as the writing rules, so "fact" means checked; the record shows whether a tool call stands behind each claim |

R3–R11, the tool-presentation items, belong to `RESEARCH-2026-10-10-how-substrate-presents-tools.md`.

## 9. How the record proves it

A gate reads every `PromptComposed` of a live session per class and checks:

- `system` holds the style and the baseline, on every step;
- the head opens with the role, then the methodology under the header, on every step;
- the `per_turn` text sits directly after the current `USER:` line, on every step;
- a `/dellm` writes `SkillRequested` and a `skill` fragment present at every later step, and a `skill("dellm")` call writes a `ToolCall` and a `ToolResult` holding the body;
- a `/model` writes `SessionChanged`, and the next step carries the update line;
- for `claude`, `SessionStarted` holds the zeroing flags, and the driver's input tokens on an empty turn equal the 656–678 token floor plus Substrate's own text.

How well each class follows the texts is measured on the round-1 task set:

- machine-register markers per 1,000 words, against the `dellm` catalog, with a target of zero;
- the acknowledgement line present;
- claims with no tool call or record read behind them, with a target of zero.

The small-class texts are tuned until they meet all three.

## 10. Order of work

1. Zeroing flags and `--system-prompt` for `claude` (§5).
2. The `personality` → `style` rename, with its legacy map (§4).
3. Session vocabulary:
   - `PromptComposed.system`;
   - `SYSTEM_SOURCES`;
   - `PromptSource` `baseline` and `skill`;
   - `PER_TURN` moved to session-open;
   - the `SessionChanged` and `SkillRequested` Structs;
   - methodology precedence 1.
4. The system channel in both responders (§6.1).
5. The texts: `style.md`, `methodology.md`, `per-turn.md` and the trimmed `default.md`, from the machine's setup (§6.1, §6.2, §6.4).
6. `resolve_extends` falls back to shipped bundles, and the application bundles extend `session` (§6.2).
7. The baseline (§6.3).
8. `per_turn` from the bundle, recorded once and placed after the message; `SessionChanged` on PATCH (§6.4).
9. `dellm`: the slash command, the injected event and fragment producer, the `skill` tool, the resolver (§6.5).
10. The class classifier and the small-class files (§7).
11. The gates (§9).

## Sources

- Product spec `current-design-direction/product-spec/PRODUCT-SPEC-2026-08-17-round12.md` §2a, §7, §7a, §7b, §14; tech spec `current-design-direction/tech-spec/TECH-SPEC-2026-08-25-round6.md` §1.6.5, §9; design spec `handoff_latest/docs/DESIGN-SPEC -2026-08-31-.md`.
- Claude Code documentation, read 2026-10-10: https://code.claude.com/docs/en/hooks, https://code.claude.com/docs/en/output-styles, https://code.claude.com/docs/en/memory, https://code.claude.com/docs/en/skills.
- This session's own context: the CLAUDE.md and memory reminder, the hook line after each prompt, the style reminder, the environment and environment-update blocks, the account e-mail and commit-attribution reminders, the `# Output Style: Plain` system section.
- Probes, 2026-10-10, `claude` 2.1.296: `-p --tools "" --strict-mcp-config --setting-sources "" --disable-slash-commands --system-prompt … --output-format json`, in a plain directory (678 input tokens) and in a fresh git repository (656).
- The driver's review, "How Substrate presents tools to its drivers", session `s_6aa52a8f0e3b436c8092fd21`, 2026-10-10.
- Records `~/.substrate/sessions/s_9eee1b3a4d094346bb30039c` and `s_6aa52a8f0e3b436c8092fd21`: manifests, `SessionStarted`, `PromptFragment` events, the first `PromptComposed`.
- Substrate:
  - `bundles.py` (slots, `load_bundle`, `resolve_extends`; the extends test);
  - `topologies/session/` (`session_prompt_producer.py`, `roles.py`, `transcript.py`, `__init__.py` `_model_factory`, `interrupt_fragment_producer.py`, `bundle/`, `prompts/`);
  - `topologies/applications/*.bundle/`;
  - `templates/bundles/*.tmpl.md`;
  - `adapters/models.py`;
  - `process/signals/session-vocabulary.md` § I.
- substrate-ui: `server.py` (session create, `_build_session_topology_from_manifest`, PATCH), `web/vm/session_controller.ts` (`slashCommands`).
- `~/.claude/`: `CLAUDE.md`, `output-styles/plain.md`, `settings.json`, `skills/dellm/SKILL.md`, the project `memory/MEMORY.md`.
- Ollama 0.34.1 `/api/show` for `llama3:8b` and `kimi-k2.6:cloud`.
