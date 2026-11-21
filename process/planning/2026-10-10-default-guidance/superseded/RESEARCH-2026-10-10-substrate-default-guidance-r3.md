# Proposal: Substrate's default guidance, built from this machine's Claude setup

*2026-10-10, round 3. Rounds 1 and 2 stay on disk. Round 3 turns the research into a proposal. It also adds:*

- *a permanent ban on model attribution and on account e-mail;*
- *a memory design;*
- *caching measurements;*
- *a rewrite in plain register.*

*No code has changed.*

## 1. The proposal

Claude works well on this machine because Claude Code hands it the same texts, at the same moments, every time. The style arrives with every request. CLAUDE.md arrives once at the start. The hook line arrives beside every message. The `dellm` skill arrives when someone asks for it.

Substrate already has a place for each of those texts: a bundle with methodology, style and per-turn slots, a role, a seed, and fragments on the record. The specs designed most of it, and half of it was built.

This proposal does three things:

1. It moves the texts into those places.
2. It finishes the half that was never built.
3. It gives Substrate a system channel, so the parts Claude Code puts in the system prompt land there for every model.

When Substrate runs Claude, it first strips out everything the machine would load on its own.

Today, on this machine:

```
 ~/.claude/                       Claude Code                          what Claude reads
 ─────────────────────────────    ──────────────────────────────       ─────────────────────
 output-styles/plain.md      ──▶  system prompt, every request    ──▶  SYSTEM
 (built in)                  ──▶  environment block, every request──▶  SYSTEM
 CLAUDE.md + memory index    ──▶  first user block, once          ──▶  USER (top)
 settings.json hook          ──▶  after every prompt              ──▶  USER (beside message)
 skills/dellm                ──▶  /dellm or the Skill tool        ──▶  a message that stays
```

Proposed, inside Substrate:

```
 files in the repo                     event on the record                    where it lands
 ───────────────────────────────       ──────────────────────────────────     ──────────────────────────────
 bundle/style.md                  ──▶  PromptFragment(bundle_style)      ─┐
 baseline, computed at open       ──▶  PromptFragment(baseline)          ─┴─▶ PromptComposed.system
                                                                               └─▶ claude --system-prompt
                                                                               └─▶ Ollama {"role":"system"}
 prompts/default.md               ──▶  PromptFragment(role)              ─┐
 bundle/methodology.md            ──▶  PromptFragment(bundle_methodology)─┼─▶ PromptComposed.text, head
 tool suite                       ──▶  PromptFragment(tools_suite)       ─┘
 bundle/per-turn.md               ──▶  PromptFragment(per_turn), once   ───▶ after the current USER: line
 /model, PATCH                    ──▶  SessionChanged                   ───▶ one update line, same place
 /dellm                           ──▶  SkillRequested → PromptFragment(skill) ─▶ head, rest of session
 skill("dellm") tool call         ──▶  ToolCall → ToolResult            ───▶ history, rest of session
```

Every arrow on the right is an event a reader can find later. Claude Code keeps no such trail: `/context` shows what loaded in a live session, and nothing shows it afterwards.

The prompt each model step sends, top to bottom:

```
 SYSTEM   style · baseline                                  same every step
 USER     role · methodology · tool list · parent context    same every step
          transcript, turns 0 … n-1                           grows at the end
          USER: <current message>
          <per-turn line> · <environment update, if any>     changes every turn
          tool results so far · call directive               changes every step
```

The order puts what never changes first and what changes last. §8 shows why that order matters.

## 2. What Claude Code delivers

| Text | Size | When | Where |
|---|---|---|---|
| `plain.md` | 2,655 B | every request | system prompt, under `# Output Style: Plain` |
| style reminder | 1 line | during tool work (observed) | system reminder: "Plain output style is active…" |
| environment block | ~1 KB | every request | system prompt: working directory, git yes/no, platform, shell, OS, model and ID, knowledge cutoff, token budget, date |
| environment update | a few lines | when the directory changes (observed) | system reminder, "# Environment update" |
| `CLAUDE.md` | 8,194 B | once, and again after compaction | first user block, under "These instructions OVERRIDE any default behavior and you MUST follow them exactly as written." |
| `MEMORY.md` | 10,948 B | once | the same block, after CLAUDE.md |
| memory topic files | one per entry | on demand | `Read` results |
| hook line | 318 B | every prompt | directly after the prompt text |
| `dellm` | 6,429 B | listing always; body on `/dellm` or a Skill call | the body arrives as one message and stays |

The sources are Claude Code's hooks, output-styles, memory and skills pages, read 2026-10-10; the reminders as they arrive in this session; and the probes in §6.

Claude Code also sends two things Substrate will never send: the account e-mail and a commit-attribution instruction. §6 covers both.

## 3. What Substrate has today

Two specs describe the delivery system:

- The product spec, §7 to §7b, lays out four disk layers for context, and a bundle made of methodology, style ("personality / voice"), per-turn text, corpus and retrieval. Bundles compose through `extends`.
- The tech spec, §1.6.5, gives the seed order: style, role, methodology, project context, seed text, baseline. It also says per-turn text "prefixes every UserMessage".

Product spec §14 maps CLAUDE.md onto the prompt layers and hooks onto "triggers on record events". The design spec, 2026-08-31, makes the prompt line the router for slash commands.

Most of this is built:

- Roles resolve through the repo, user and shipped layers.
- Bundles load their slots and fall back to the shipped defaults.
- Since K263, one producer writes every session-open text as a `PromptFragment`, recorded once and placed at a fixed precedence:
  - role, 0;
  - style, 3;
  - tool list, 20;
  - parent context, 30;
  - methodology, 50.
- The model step rebuilds the prompt on every step and records the exact text as `PromptComposed`.

Four pieces were designed and not built.

**The baseline.** `SessionStarted.baseline` is `{}` in every session. The specs list its contents:

- the repo root;
- the branch;
- the README head;
- `git diff HEAD`;
- `<repo>/.substrate/context.md`.

**The per-turn slot.** It loads from the bundle and never reaches a session. A session's `per_turn` comes only from its manifest, which is empty unless a PATCH sets it, and it renders at the top of the prompt rather than beside the message.

**`extends` onto a shipped bundle.** It fails. `resolve_extends` passes an explicit root, so `load_bundle` skips the shipped fallback; a test bundle with `extends = ["session"]` raised `BundleNotFoundError`.

**Mid-session changes.** `/model` and a PATCH of the bundle or `per_turn` change the manifest only. Nothing reaches the record, and the model is never told.

There is also only one channel. Ollama gets `[{"role":"user", "content": <everything>}]`, and `claude -p` gets everything as one argument.

The shipped text is thin:

- The `session` bundle has 317 B of loop rules in its methodology, and empty style and per-turn files.
- The `default` role is 848 B.
- The four application bundles each carry one style line, for example "Blunt. Specific. Name the file and the line every time."

The two latest sessions show what a model actually got. Their first prompt opened with `add(a, b) -> a+b`, then the rest of the tool list and the methodology. There was no role, because both sessions opened before the 2026-10-08 fix. No workspace path, no date, no model name.

## 4. The translation, channel by channel

### Style: system channel, every step

Claude Code sends `plain.md` in the system prompt on every request. In Substrate the text goes into `bundle/style.md`. It is joined by CLAUDE.md's "Every output is writing" and "Unaddressed prose" sections and the memory's writing rules.

The session-open producer records it once as `PromptFragment(bundle_style)`. `PromptComposed` gains a `system` field, and the model step sends that field through each driver's own system channel: `--system-prompt` for Claude, a system message for Ollama. Every step sends the whole prompt again, so the style rides every step. That includes tool steps, which Claude Code's repeated style reminder exists to cover.

The slot was called `personality`. Nothing in it describes a person. Every shipped line is an instruction about writing. It becomes `style`:

- `style.md`;
- `Bundle.style`;
- `PromptSource.BUNDLE_STYLE`;
- the wizard question "How should the model write?".

Old records keep `bundle_personality`, and a legacy table maps it, as `LEGACY_SESSION_END_REASONS` maps `timeout`.

### Environment: system channel, every step

Claude Code tells the model where it is and when. Substrate's spec already had this as the baseline. It is built now. At session open the daemon computes:

- the workspace path;
- for a repo, the root, branch, commit, README head and diff;
- the platform;
- the driver and its model ID;
- the date;
- `context.md`, when present.

It stores the result in `SessionStarted.baseline` and records it as `PromptFragment(baseline)` on the system channel.

### Working rules: top of the user turn, every step

Claude Code sends CLAUDE.md once, as the first user block, and it holds for any task. In Substrate the matching slot is the bundle's methodology, not the role. A session picks one role at a time, say `reviewer` or `planner`, and CLAUDE.md's rules must hold under every one.

`bundle/methodology.md` takes:

- CLAUDE.md's working sections: acknowledge before acting; research, don't fabricate; the adversarial information space; read files whole; the reverse explainer;
- the memory's general working rules;
- the current loop rules.

All of it goes under Claude Code's header. The `default` role keeps who the model is and that the record is the source of truth, and gives its duplicated rules to the methodology.

Methodology moves from precedence 50 to 1, ahead of the tool list, as CLAUDE.md comes ahead of the conversation. Every step carries it at the top. History compaction drops old turns and never touches the top, so the rules survive what Claude Code has to re-inject after `/compact`.

The application bundles get the same rules by declaring `extends = ["session"]`, once `resolve_extends` learns to fall back to shipped bundles.

### The hook line: beside every message

Claude Code puts the hook line directly after each prompt. The specs describe the same slot. In Substrate the line goes into `bundle/per-turn.md`. A session's `per_turn` defaults to its bundle's slot, and a PATCH overrides it.

The producer records it once, as `PromptFragment(per_turn)`, since the text is the same every turn. `PER_TURN` moves to the session-open set.

The composer places the line right after the current `USER:` line on every step of the turn. It no longer goes at the top of the prompt. The specs said "prefix"; Claude Code places it after. After is the choice, and session vocabulary records it.

### Changes mid-session: the same place

Claude Code adds "# Environment update" when the directory changes. In Substrate, a PATCH of driver, bundle or `per_turn` writes `SessionChanged{field, old, new}` to the record. A date rollover writes one too. The next step carries one line beside the message: "Environment update: model changed from glm-5.2:cloud to claude." The driver's review called this out as F7, environment facts going stale with no marker.

### `dellm`: only when asked

`dellm` is the one skill that crosses over. Nothing loads it until someone asks. There are two ways to ask, the same two Claude Code has.

- **`/dellm` in the prompt line.** The UI's slash table gains the command, and the text after it becomes the turn's message. The daemon injects `SkillRequested{name: "dellm"}`, by the path `/interrupt` already uses. A small producer answers with `PromptFragment(skill)`, which stays at the top of every later step.
- **Asking in words.** "De-LLM this paragraph." The model calls `skill("dellm")`. The body comes back as a `ToolResult` and stays in history. The tool's description lists `dellm` and what it does, as Claude Code's skill listing does.

The file resolves through the same layers as roles:

1. `<repo>/.substrate/skills/dellm/`;
2. `~/.substrate/skills/dellm/`;
3. the shipped copy.

Each layer holds one file per model class. The model can apply it to anything: a passage in the conversation, a file it reads and rewrites, or its own draft.

## 5. What changes in Substrate

1. **Rename `personality` to `style`**, with the legacy map for old records.
2. **Add the system channel.**
   - `PromptComposed.system`, filled by `SYSTEM_SOURCES = {bundle_style, baseline}`.
   - `OllamaResponder` takes `system` on each call.
   - The Claude driver passes it as `--system-prompt`.
3. **Build the baseline** into `SessionStarted.baseline` and `PromptFragment(baseline)`.
4. **Make `per_turn` work as designed:**
   - it defaults from the bundle;
   - it is recorded once;
   - it is placed after the current message.
5. **Add `SessionChanged`**, written on PATCH and on a date rollover, with the update line it drives.
6. **Let a bundle extend a shipped bundle**, and have the four application bundles extend `session`.
7. **Move methodology to precedence 1.**
8. **Add `dellm`:**
   - the `/dellm` slash command;
   - `SkillRequested` and its fragment producer;
   - the `skill` tool;
   - the skill resolver;
   - one file per class.
9. **Write the texts:** `style.md`, `methodology.md`, `per-turn.md`, and a trimmed `default.md`, all taken from this machine's setup.
10. **Strip out the Claude driver's own setup**, ban attribution and e-mail, and build the gate (§6).
11. **Add memory** (§7).
12. **Choose texts by model class** (§9).

Items 1 to 5, 8 and 11 change session vocabulary. They ship as one bump with a ratification note.

## 6. Stripping out the Claude driver's setup, and the two things that never come back

`claude -p` loads the machine's setup unless told not to. It runs with these flags:

- `--tools ""`;
- `--strict-mcp-config`;
- `--setting-sources ""`;
- `--disable-slash-commands`;
- `--system-prompt <Substrate's system text>`.

`--system-prompt` replaces Claude Code's own prompt rather than adding to it. Two probes on 2026-10-10, one in a plain directory and one in a fresh git repo, came to 678 and 656 input tokens. Nothing from `~/.claude` reached the model, and no built-in tool, no MCP tool and no Claude Code instructions did either.

Three things remained:

- **The SDK line.** "You are a Claude agent, built on Anthropic's Claude Agent SDK."
- **The environment block.** It agrees with Substrate's own baseline, since both describe the same workspace.
- **The account e-mail.**

**Attribution.** No model run by Substrate ever adds attribution: no `Co-Authored-By` trailer, no "Generated with" footer, no model credit in any file. Substrate's own code has none; a search of `substrate/src`, `server.py` and `web/` found no attribution or e-mail string.

Claude Code adds its commit-attribution instructions inside its git instructions. Neither zeroed probe received them, and `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS=1` removes them outright, so the Claude driver sets it as well.

The methodology carries the rule for every model: a model is a tool, and tools take no credit.

**E-mail.** No model run by Substrate ever learns anyone's e-mail address, and none ever sends mail. Claude Code builds its `userEmail` block from `oauthAccount.emailAddress` in its config file, the one CLI login stores. In the 2.1.296 binary: `Hn()?.emailAddress`, where `Hn()` returns `ce().oauthAccount`.

A login fills that field, and no flag clears it. The way around it is to keep the login out of the driver's config:

1. The operator runs `claude setup-token` once, which makes a long-lived token.
2. Substrate runs the driver with that token in `CLAUDE_CODE_OAUTH_TOKEN`.
3. It also points `CLAUDE_CONFIG_DIR` at a directory Substrate owns, `~/.substrate/drivers/claude/`, which holds no account profile.

A test run with an empty config directory and no token came back "Not logged in", which confirms the directory is the account's only source. Nothing in Substrate reads, stores or sends an address.

**The gate.** It runs on every build. It starts the Claude driver as Substrate starts it, asks the driver to quote its full context, and fails the build if any of the following appears:

- an `@` address;
- `userEmail`;
- `Co-Authored-By`;
- "Generated with".

## 7. Memory

Claude Code's memory is a directory. A `MEMORY.md` index loads at the start of every session. One topic file per memory gets read when needed. Claude writes the files itself, following instructions in its system prompt, and nothing records those writes.

On this machine the directory holds 43 entries, and they come in two kinds:

- **General working rules.** "Green is not proven", "check the box before asserting infra", "read the code and grep repeated literals", "report, don't prescribe", "never pkill by pattern". §4 already moves these into the shipped methodology. Every model gets them, with no memory system involved.
- **Facts about one project.** The Substrate roadmap, the SWE-bench plan, a test-invocation gotcha. These belong to this repo.

Product spec §7a settled how Substrate keeps knowledge: as text files a user owns, in named places, and never as a database. A memory system that fits that rule:

- **Where it lives.** Two directories: `~/.substrate/memory/` for the operator, and `<repo>/.substrate/memory/` for a project. Each holds a `MEMORY.md` index, one line per entry, plus a topic file per entry.
- **Loading.** At session open, both indexes load as `PromptFragment(memory)`, capped at 200 lines or 25 KB each, the same limits Claude Code uses.
- **Reading.** A model reads a topic file with `read_file` when it needs it.
- **Writing.** A model saves a memory with `write_file` or `edit_file`, by rules that sit in the methodology. Those rules are distilled from Claude Code's memory instructions: the four kinds (user, feedback, project, reference), one fact per file, and a why and a how-to-apply for every correction.
- **The record.** Every memory write is a `ToolCall` on the record, so a reader can see which session learned what, from which turn.

This also answers how Claude comes to use Substrate's memory. With the machine's setup stripped out, Claude has no memory of its own. The methodology tells every model, Claude included, how to save to Substrate's memory and how to recall from it. It works the same for Kimi or Qwen.

The project entries on this machine move into `<repo>/.substrate/memory/` for this repo. The operator directory starts empty.

## 8. Prompt caching

Sending the whole prompt every step is how chat models work. What matters is whether the provider can reuse the part it has already seen. Both drivers were measured on 2026-10-10.

**Ollama**, local `qwen2.5:7b-instruct`, with CLAUDE.md as the prompt prefix. The model reported 1,914 prompt tokens on every call, but the time to read them changed:

| Call | Time to read the prompt |
|---|---|
| first call | 707 ms |
| same prompt again | 11 ms |
| same prefix with three lines appended | 56 ms |
| one line added at the top | 691 ms |

Ollama keeps the last prompt's computed state and reuses the longest matching prefix. A change near the top throws it all away.

**Claude**, `claude -p`, with CLAUDE.md and `plain.md` in the prompt. With everything in the one `-p` argument, as Substrate sends it today, two calls with the same opening both wrote about 4,280 tokens to the cache and read none. With the same text in `--system-prompt` instead, the second call read 3,689 tokens from the cache and wrote 578.

The cache matches on whole blocks. One long user string gives it nothing to match.

Two rules follow, and the layout in §1 obeys both:

1. **The stable text goes in the system channel and at the top.** The system channel is what makes Claude's cache hit at all. The fixed head makes Ollama's prefix reuse work.
2. **Everything that changes goes at the end.** That covers the per-turn line, environment updates, the current message, tool results and the call directive.

This is also why the per-turn line moves to after the message. At the top of the prompt it is only harmless while it never changes, and an update line placed there would break the cache on every change.

Compaction is the one thing that breaks the prefix: dropping the oldest turn shifts everything after the head. The head stays cached across it.

The probe showed Claude Code's cache entries living for one hour.

## 9. Model classes

| Class | Drivers | Chosen by | System channel | `dellm` | Texts |
|---|---|---|---|---|---|
| Claude | `claude` | adapter name | `--system-prompt` | slash and tool | full |
| Large open models | kimi, glm, deepseek-v4-pro, nemotron | `/api/show` parameter size ≥ 30B | system message | slash and tool | full |
| Small local models | qwen2.5 7B, llama3.2:1b, llama3:8b, deepseek-r1:8b | parameter size < 30B | system message | slash; tool only when the model reports `tools` | compressed |

Ollama reports parameter size two ways, `"8.0B"` for `llama3:8b` and `"1042000000000"` for `kimi-k2.6:cloud`, and the classifier reads both.

For Claude, Substrate's tool list and call format move into the system channel. That settles two of the review's findings. F3: a list inside the user turn read as injected text. R1: with its own tools removed, Claude needs telling that Substrate's tools are the only ones.

Small models get their own files in the same slots: `style.small.md`, `methodology.small.md`, `per-turn.small.md` and `skills/dellm/small.md`.

The full set runs to about 11 KB, close to 2,800 tokens. The small set fits in 800 tokens, a tenth of `llama3:8b`'s 8,192-token window. Each rule is cut to one short imperative line. The small `dellm` keeps the word and structure lists and the four passes.

`SessionStarted` records the class.

## 10. The driver's review, answered

The review came from session `s_6aa52a8f…`, where Claude drove Substrate.

- **F2, R1, R2: two tool systems, with no rule for which counts.** §6 removes Claude's own tools, and §9 names Substrate's as the only ones, on the system channel.
- **F3: the tool list read as injected text.** For Claude it moves to the system channel.
- **F4: four instruction layers fought each other.** They were Claude Code's prompt, CLAUDE.md, the hook and Substrate's prompt. Stripping out Claude Code's layers leaves Substrate's set alone. The commit trailer is gone (§6). The acknowledgement line and a JSON tool call share one reply, the line first and then the object, which `parse_tool_call` already accepts.
- **F4: the methodology duplicated Claude Code's loop rules.** `--system-prompt` removes Claude Code's copy.
- **F7, R8: environment facts went stale.** The baseline (§4) and `SessionChanged` fix this.
- **§6: unchecked claims stated flat.** The methodology puts "research, don't fabricate" and "name your evidence" beside the writing rules, and the record shows whether a tool call stands behind each claim.

The tool-presentation items, R3 to R11, belong to `RESEARCH-2026-10-10-how-substrate-presents-tools.md`.

## 11. Proof, and the order of work

A gate reads every `PromptComposed` in a live session for each class. It checks that:

- the system part holds the style and the baseline;
- the head opens with the role and then the methodology;
- the per-turn line sits right after the current message;
- a `/dellm` leaves a `SkillRequested` and a fragment;
- a `skill` call leaves a `ToolCall` and `ToolResult`;
- a `/model` leaves a `SessionChanged` and an update line;
- a memory save leaves a `ToolCall` into a memory directory.

The §6 gate covers attribution and e-mail. A second Claude step in the same session shows a cache read.

How well each class follows the texts is measured on the round-1 task set:

- machine-register words per 1,000, against the `dellm` catalog;
- the acknowledgement line;
- claims with no tool call behind them.

The small texts are tuned until they pass.

The order of work:

1. The Claude driver setup: strip-out flags, token, config directory, git instructions off, and the gate (§6).
2. The vocabulary bump (§5, items 1–5, 8 and 11).
3. The system channel in both responders.
4. The texts.
5. Shipped `extends`, with the application bundles extending `session`.
6. The baseline.
7. `per_turn` and `SessionChanged`.
8. Memory.
9. `dellm`.
10. Model classes and the small files.
11. The record gates.

## Sources

- Product spec `current-design-direction/product-spec/PRODUCT-SPEC-2026-08-17-round12.md` §2a, §7–§7b, §14; tech spec `current-design-direction/tech-spec/TECH-SPEC-2026-08-25-round6.md` §1.6.5, §9; design spec `handoff_latest/docs/DESIGN-SPEC -2026-08-31-.md`.
- Claude Code docs, read 2026-10-10: hooks, output-styles, memory, skills, env-vars, settings (code.claude.com/docs/en/…).
- The `claude` 2.1.296 binary: the `userEmail` construction (`Hn()?.emailAddress`, `Hn()` returning `ce().oauthAccount`) and `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS`; `~/.claude.json` `oauthAccount` keys.
- Probes, 2026-10-10:
  - zeroed `claude -p` in a plain directory (678 tokens) and in a git repo (656);
  - an empty config directory ("Not logged in");
  - cache with the text in `-p` (two writes, no reads) and in `--system-prompt` (3,689 read on the second call);
  - Ollama `qwen2.5:7b-instruct` prefix reuse (707 / 11 / 56 / 691 ms).
- The driver's review, session `s_6aa52a8f0e3b436c8092fd21`.
- Records `s_9eee1b3a4d094346bb30039c` and `s_6aa52a8f0e3b436c8092fd21`.
- Substrate:
  - `bundles.py`;
  - `topologies/session/` (producer, roles, transcript, model step, interrupt producer, bundle, prompts);
  - `topologies/applications/*.bundle/`;
  - `templates/bundles/`;
  - `adapters/models.py`;
  - `process/signals/session-vocabulary.md` § I.
- substrate-ui: `server.py` (session create, topology build, PATCH) and `web/vm/session_controller.ts` (slash commands).
- `~/.claude/`: `CLAUDE.md`, `output-styles/plain.md`, `settings.json`, `skills/dellm/SKILL.md`, the project memory.
