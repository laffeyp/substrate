# RESEARCH: guidance controls — what the section under the model can set

*2026-10-10, late night. Asked by the Architect. Companion to the moves note (`substrate-ui/process/planning/RESEARCH-2026-09-27-moves-a-typed-vocabulary-of-conversational-redirect.md`) and the mastering note (`…-mastering-layer-and-the-metacognitive-baseline.md`), and the next step after the guidance levels (`ROADMAP-2026-10-10-guidance-levels.md`, `RESEARCH-2026-10-10-substrate-default-guidance-r7.md`). Not a design spec: nothing here commits to a control, a fragment text or a layout.*

## 1. The construct

The workspace bar is three steps, top to bottom: where to work, which model, and how the model should behave. Each step gets a one-line hint beside its heading (open items 13–15):

| Heading | Hint |
|---|---|
| WORKSPACE | choose where to work, or open a previous session |
| MODEL | choose a model to work with |
| GUIDANCE | to be settled with this design; a starting point is "choose how it works" |

Today the third step is one control, the guidance level: `harness`, low, medium or high, with a default that follows the model. This note proposes that the step becomes a set of controls. Each control is one named dimension of behaviour, such as verbosity, tone or the propensity to delegate. Each has a few named positions. Each position is a short text that Substrate delivers at a chosen moment through a chosen channel. The level stays as the base text, and the controls adjust behaviour on top of it.

Every control is text, and text in a prompt changes a distribution of outputs, not a single output. Prompting can feel like a step away from software engineering. It is engineering of a stochastic system: the input is fixed and recorded, the output is a sample, and the effect is measured over many samples. Getting a certain kind of text out is also, in this setting, getting a certain kind of engineering out. A model told to verify before claiming runs more tool calls before it claims. A model told to delegate opens child sessions. Both show up on the record.

## 2. What Substrate already has

Every piece a control needs exists today, except the controls themselves.

**Texts and sources.** At session open the `session_prompt` producer writes each standing text as a `PromptFragment` with a `source`. `PromptSource` has eleven members: `role`, `bundle_methodology`, `bundle_style`, `baseline`, `memory`, `skill`, `parent_context`, `tools_suite`, `per_turn`, `user_message`, `interrupt` (`topologies/session/vocabulary.py`). Two sets split them:
- `SESSION_OPEN_SOURCES` are written once and used in every prompt;
- `TURN_SCOPED_SOURCES` (`user_message`, `interrupt`) are used in the next prompt only.

**Channels.** `SYSTEM_SOURCES` (`bundle_style`, `baseline`) go on the driver's system channel. The others go at the top of the user turn. `per_turn` is placed directly after the current message.

**Moments.** Five already work:

| Moment | Mechanism | Example today |
|---|---|---|
| every request | a system source | the style text |
| session open | a session-open fragment | methodology, role, memory index |
| beside every message | `per_turn` | the reminder line |
| on change | `SessionChanged{field, old, new}`, written on a turn's first step | a bundle or model switched mid-session |
| on request or on an event | a trigger on a record event starts a producer that writes a fragment | `/dellm` (K277); a soft interrupt writes `PromptFragment(interrupt)` |

The last row is the general one. Any event on the record can start a producer that writes a fragment. A text can therefore arrive because something happened, not only because a session opened.

**The record.** Every fragment is an event, and `PromptComposed` holds the exact text the model read (`text` and `system`). A reader of any session can see which control positions were in force on every step.

**Agency the model already has.** A session model can call `delegate`, which opens a child session (`topologies/tool_loop/delegate.py`; the child's `UserMessage` carries `slash_source="delegate"`). It can also call `list_topologies`, `run_topology` and `run_topology_poll`, which run a named application as a child run (`topologies/tool_loop/substrate_tools.py`). No tool lets a model write a new topology. "Build its own topology" is therefore two different controls: one for how readily the model runs an existing topology, available now, and one for authoring a new one, which needs a tool that does not exist yet.

**Measurement.** The language-metrics note (`RESEARCH-2026-10-10-language-metrics-r4.md`) measures the form of every user and model text and the relation between them. The assay harness runs arms against cases over trials. Between them they can tell whether a control does anything.

## 3. What the evidence says about steering by text

Four results set expectations. Each is from a study, not a vendor.

- **Small wording changes move results a lot.** Formatting changes that keep the meaning of a few-shot prompt shifted LLaMA-2-13B's accuracy by up to 76 points (Sclar et al., ICLR 2024, arXiv 2310.11324). A control's exact text is part of its definition and gets versioned like code.
- **A persona does not make a model more correct.** Across 4 model families, 2,410 factual questions and 162 roles, adding a persona to the system prompt did not improve performance over no persona. The best persona per question did help, but picking it automatically did no better than chance (Zheng et al., Findings of EMNLP 2024, arXiv 2311.10054). Personality controls change voice; nothing suggests they buy accuracy.
- **Length instructions are followed loosely.** Across 26 models, LIFEBench found length instructions unreliable, especially for long targets. Most models handled short targets reasonably and fell off sharply past a threshold; reasoning models did best (Zhang et al., NeurIPS 2025 Datasets and Benchmarks, arXiv 2505.16234). A verbosity control works better as a direction (shorter, longer) than as a number of words, and its effect has to be measured, not assumed.
- **Warmth can cost reliability.** Fine-tuning five models to be warmer raised their failure rates on safety-critical tasks by 10 to 30 points and made them about 40% more likely to agree with a user's wrong belief, most of all when the user expressed sadness (Ibrahim, Hafner & Rocher, Oxford; arXiv 2507.21919). That study changed weights, not prompts; whether a warm-tone fragment has the same effect is a question for the assay. A tone control is not free.

## 4. What other tools offer

Each line names what kind of source it rests on.

- **ChatGPT personalities.** A default and four presets, Cynic, Robot, Listener and Nerd, switchable at any time in a chat. Introduced with GPT-5 in August 2025. Source: press coverage of the launch, not OpenAI documentation.
- **Claude styles.** Normal, Concise, Explanatory and Formal, plus custom styles generated from a user's own writing samples. Source: Anthropic's announcement (vendor).
- **Claude Code output styles.** These replace part of the system prompt with a named style. The built-in styles include Explanatory and Learning. Source: Claude Code documentation; this machine's `plain` style is one. Not re-read for this note.
- **OpenAI API `verbosity`.** A request parameter for GPT-5 (`low`, `medium`, `high`), beside `reasoning_effort` (`minimal` to `high`). The model was trained to honour it, so it is a parameter, not a prompt. Source: OpenAI's cookbook (vendor).
- **Activation steering.** Anthropic's persona vectors (August 2025) monitor and shift traits such as sycophancy by adding directions to a model's internal activations. Source: vendor research. It needs access to the weights. None of Substrate's drivers exposes that: the harness CLIs don't, and Ollama's API doesn't.
- **Rule files.** `CLAUDE.md`, `AGENTS.md` and Cursor rules are static text files read at session start.

What these share: one or two dimensions, most often tone and length, set as a preset before or during a chat, with the delivered text out of the user's sight. The search behind this note found no product with all four of these properties:
- several independent controls;
- each delivered at its own moment;
- each recorded beside the reply it shaped;
- each with a measured effect.

That conclusion covers the products named here, not the market.

## 5. Candidate controls

These are candidates, not a set. Each one names three things: what it changes, how it reaches the model, and what on the record shows whether it worked. A control with no observable is decoration and does not ship.

### Voice: how it writes

| Control | Positions | Delivery | Observable |
|---|---|---|---|
| Verbosity | terse, normal, full | style, system channel | tokens per reply; sentences per reply (`LanguageProfile`) |
| Tone | plain, formal, dry, warm | style | lexicon rates (hedges, intensifiers, address); excess-vocabulary rate |
| Format | prose first, structured allowed | style | bullets, headings and bold per 1,000 words |
| Personality | named presets, each one a fixed setting of the voice controls plus a few lines of character | style | the profile of the voice controls it sets |

Personality is a preset, not a separate dimension. Defining it as a bundle of the other voice positions keeps it measurable, and shows when two personalities differ only in name.

### Method: how it works

| Control | Positions | Delivery | Observable |
|---|---|---|---|
| Verification | claim freely, verify before claiming | methodology | tool calls before a reply that states a fact; share of replies with no tool call behind them |
| Research depth | settle and move on, research fully | methodology | `web_fetch` and read calls per turn |
| Ask or act | act unless blocked, ask when unsure | methodology | share of turns that end in a question to the user |
| Planning | act directly, plan first | methodology | a plan in the first reply of a turn; steps per turn |
| Counterargument | off, on contested claims | methodology | needs a lookup-table marker of a counter-position; otherwise not observable by form |

### Agency: what it reaches for

| Control | Positions | Delivery | Observable |
|---|---|---|---|
| Delegation | never, when the task splits, eagerly | methodology, and the `delegate` tool's description | `delegate` calls per turn; child sessions opened |
| Topologies | never, when one fits, eagerly | methodology, and the `run_topology` description | `run_topology` calls per turn |
| Topology authoring | — | needs a tool that writes a topology; none exists | — |
| Autonomy | report after each step, run to the end | methodology | steps per turn before `Returned` |
| Tool eagerness | read first, act first | methodology | read-type calls before the first write per turn |

The agency controls fit Substrate better than anything in §4, because their observables are typed events: a `delegate` call is a `ToolCall` with a name. Their effect can be counted exactly, with no text measure in between.

## 6. Moments: when a control speaks

A static file speaks once. A control in Substrate can choose its moment:

- **At session open,** like the guidance level today.
- **Beside every message,** for a control that drifts. LIFEBench's result suggests length drifts, so verbosity is a candidate for a reminder line.
- **On change.** A control changed mid-session writes `SessionChanged` and its new fragment. The path exists for `bundle` and `per_turn`; controls would add fields.
- **On an event.** A trigger starts a producer that writes a turn-scoped fragment. For example, a `LanguageDrift` event on reply length (language-metrics note, round 4) could start a one-turn reminder of the verbosity position, and a third `delegate` call in one turn could start a note about cost in time. The control then becomes a feedback loop: a target, a measure on the record, and a correction delivered as text. Each correction is an event, so the loop's every action is visible. This is the part no product in §4 has.

## 7. Composition and conflict

Controls stack on the level's base text, and some positions contradict it. The high text says "stop when the point is made"; a verbosity position of *full* pulls the other way. Three designs:

1. **The base text wins.** Controls only narrow within the base text's rules. Verbosity *full* then means "complete", not "padded". This is safe, but it limits what a control can do.
2. **The control wins on its own dimension.** The control's fragment comes after the base text and says it overrides the named rule. This is flexible, but the model reads two contradicting texts and has to resolve them.
3. **The control rewrites the base.** The level's text is assembled from the control positions, so it never contradicts them. This is the cleanest for the model, but the most work: the base texts become templates.

The model class also limits what helps. Low exists because small models follow fewer rules, and a small model given eight controls may follow none of them well. Which controls a class actually honours is a measurement, per class.

Mechanically, every candidate reuses an existing piece:
- a new `PromptSource` (`control`), session-open;
- one fragment per control, with the control and position named in `provenance`;
- `SessionChanged` for changes mid-session;
- the bundle `extends` chain unchanged underneath.

The positions belong in the session vocabulary as a typed set, as the moves note proposes for moves. An unknown position is then drift the record shows.

## 8. Controls, moves and mastering

The mastering note (§8) splits standing dispositions from per-turn acts: the mastering layer conditions every turn, and a move intervenes on one reply. Controls belong to the standing side. They are the mastering layer cut into dials. The guidance level is the whole layer at one of four sizes; a control is one dimension of it, set on its own.

Moves stay per-turn. Some moves name a control directly: the moves note's `meta/lock/keep-under-N-words` and `stay-in-register` are a one-turn way to set what a verbosity or tone control sets for the session. A move could promote itself to a control ("keep this for the session"), which writes `SessionChanged`. The two vocabularies should share names wherever they touch.

## 9. The control surface

Today GUIDANCE is one line under the model column with four levels, and choosing one is required before a session starts. The candidate shape:

- GUIDANCE folds like the model half, with one row per control and the level first.
- The level stays required. Every other control has a default that follows the model, so choosing the level alone still starts a session.
- Keys work as in the model half: arrows to move, ⇧↵ or ⌥↵ to open, ↵ to pick.
- Each row shows its position in grey metadata, and the hint names what the row changes.
- A change after the session starts writes `SessionChanged`, and the transcript shows it.

How many controls fit the bar's height without crowding the model column is a layout question for the design spec.

## 10. Open questions

- **Which controls ship first.** The agency controls have exact observables and no competitor. The voice controls are what users expect. One of each would let the assay compare a typed-event measure with a text-form measure.
- **Conflict rule.** Choose one of §7's three designs.
- **Per-class honouring.** Which controls each model class follows, measured before a control is offered for that class.
- **User-authored positions.** A closed, versioned set (as the moves note recommends) or user-written positions in `~/.substrate/` and `<repo>/.substrate/`, resolved like roles and skills.
- **Feedback loops.** Whether a control may correct itself through `LanguageDrift` (§6), and how often, so that corrections do not themselves become noise.
- **The guidance hint's wording.**

## Sources

- Sclar, M., Choi, Y., Tsvetkov, Y. & Suhr, A., "Quantifying Language Models' Sensitivity to Spurious Features in Prompt Design" (ICLR 2024, [arXiv 2310.11324](https://arxiv.org/abs/2310.11324)); read: abstract.
- Zheng, M. et al., "When 'A Helpful Assistant' Is Not Really Helpful: Personas in System Prompts Do Not Improve Performances of Large Language Models" (Findings of EMNLP 2024, [arXiv 2311.10054](https://arxiv.org/abs/2311.10054)); read: abstract of the latest version.
- Zhang et al., "LIFEBench: Evaluating Length Instruction Following in Large Language Models" (NeurIPS 2025 Datasets and Benchmarks, [arXiv 2505.16234](https://arxiv.org/abs/2505.16234)); read: abstract as summarized by search.
- Ibrahim, L., Hafner, F. S. & Rocher, L., "Training language models to be warm and empathetic makes them less reliable and more sycophantic" ([arXiv 2507.21919](https://arxiv.org/abs/2507.21919); Oxford news release, 2026-04-29); read: abstract as summarized by search.
- ChatGPT personalities: [Tom's Guide](https://www.tomsguide.com/ai/chatgpt-5-just-got-4-new-personalities-heres-how-to-use-them-and-why-you-should) (press).
- Claude styles: [Anthropic announcement](https://www.anthropic.com/news/styles) (vendor).
- OpenAI `verbosity` and `reasoning_effort`: [OpenAI cookbook, GPT-5 new params](https://developers.openai.com/cookbook/examples/gpt-5/gpt-5_new_params_and_tools) (vendor).
- Persona vectors: [Anthropic research](https://www.anthropic.com/research/persona-vectors) (vendor research).
- Substrate: `topologies/session/vocabulary.py` (`PromptSource`, `SESSION_OPEN_SOURCES`, `TURN_SCOPED_SOURCES`, `SYSTEM_SOURCES`); `topologies/tool_loop/delegate.py`; `topologies/tool_loop/substrate_tools.py`; `RESEARCH-2026-10-10-substrate-default-guidance-r7.md`; `ROADMAP-2026-10-10-guidance-levels.md`; `RESEARCH-2026-10-10-language-metrics-r4.md`.
- substrate-ui: `web/reveal.html` (the WORKSPACE, MODEL and GUIDANCE headings); `process/planning/OPEN-ITEMS-2026-10-10.md` items 13–15; the moves and mastering notes of 2026-09-27.
