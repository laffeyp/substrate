# RESEARCH: guidance controls — what the section under the model can set (round 2)

*2026-10-10, late night. Asked by the Architect. Round 1 (`RESEARCH-2026-10-10-guidance-controls.md`) stays on disk. Companion to the moves note (`substrate-ui/process/planning/RESEARCH-2026-09-27-moves-a-typed-vocabulary-of-conversational-redirect.md`) and the mastering note (`…-mastering-layer-and-the-metacognitive-baseline.md`), and the next step after the guidance levels (`ROADMAP-2026-10-10-guidance-levels.md`, `RESEARCH-2026-10-10-substrate-default-guidance-r7.md`). Not a design spec: nothing here commits to a control, a fragment text or a layout.*

**Changes from round 1.**
- **The model is a stochastic text generator, not a person.** No control frames it as a person, a character, a persona or a job role. Person framing appears only in reports of other people's work, marked each time as not adopted (§2).
- **The "Personality" control is gone,** and so is every trait word used as a position.
- **Manufacturer material is treated as PR copy.** A vendor's own text about its product is a claim, not evidence, and §5 labels it that way.
- **A new method control, source discipline,** keeps a model from accepting a claim because of who published it (§6).
- **Evidence on person framing and on de-skilling** is added (§4).

## 1. The construct

The workspace bar is three steps, top to bottom: where to work, which model, and how the model should work. Each step gets a one-line hint beside its heading (open items 13–15):

| Heading | Hint |
|---|---|
| WORKSPACE | choose where to work, or open a previous session |
| MODEL | choose a model to work with |
| GUIDANCE | to be settled with this design; a starting point is "choose how it works" |

Today the third step is one control, the guidance level: `harness`, low, medium or high, with a default that follows the model. This note proposes that the step becomes a set of controls. Each control is one named dimension of the output or the method, such as verbosity or the propensity to delegate. Each has a few named positions. Each position is a short text that Substrate delivers at a chosen moment through a chosen channel. The level stays as the base text, and the controls adjust what comes out on top of it.

Every control is text, and text in a prompt changes a distribution of outputs, not a single output. The input is fixed and recorded, the output is a sample, and the effect is measured over many samples. The system has internal structure, rules and path dependence, and a control works through them. Getting a certain kind of text out is also, in this setting, getting a certain kind of engineering out. A model told to verify before claiming runs more tool calls before it claims. A model told to delegate opens child sessions. Both show up on the record.

## 2. The model is not a person

Substrate treats every model as a stochastic text generator. No control, preset or text gives a model a person's name, a character, a persona, feelings, or a job title from an organization. "You are a product manager" is the kind of line no Substrate control writes.

Two needs that other tools meet with roles are met here in abstract terms:
- **Loading knowledge.** A control or skill that brings in a body of domain material is named for the material, for example a knowledge load on concurrency or on tax law. It is never named for a person who would know it.
- **Places in a topology.** A step in a multi-model topology is an information-processing node with an abstract name for what it does to its input, such as a filter, a checker or a merger. It is never an org-chart job.

Studies of people and personas appear in §4 and §5 because they are part of the field. Each is reported, and none is adopted.

## 3. What Substrate already has

Every piece a control needs exists today, except the controls themselves.

**Texts and sources.** At session open the `session_prompt` producer writes each standing text as a `PromptFragment` with a `source`. `PromptSource` has eleven members: `role`, `bundle_methodology`, `bundle_style`, `baseline`, `memory`, `skill`, `parent_context`, `tools_suite`, `per_turn`, `user_message`, `interrupt` (`topologies/session/vocabulary.py`). Two sets split them:
- `SESSION_OPEN_SOURCES` are written once and used in every prompt;
- `TURN_SCOPED_SOURCES` (`user_message`, `interrupt`) are used in the next prompt only.

**Channels.** `SYSTEM_SOURCES` (`bundle_style`, `baseline`) go on the driver's system channel. The others go at the top of the user turn. `per_turn` is placed directly after the current message.

**Moments.** Five already work:

| Moment | Mechanism | Example today |
|---|---|---|
| every request | a system source | the style text |
| session open | a session-open fragment | methodology, memory index |
| beside every message | `per_turn` | the reminder line |
| on change | `SessionChanged{field, old, new}`, written on a turn's first step | a bundle or model switched mid-session |
| on request or on an event | a trigger on a record event starts a producer that writes a fragment | `/dellm` (K277); a soft interrupt writes `PromptFragment(interrupt)` |

The last row is the general one. Any event on the record can start a producer that writes a fragment. A text can therefore arrive because something happened, not only because a session opened.

**The record.** Every fragment is an event, and `PromptComposed` holds the exact text the model read (`text` and `system`). A reader of any session can see which control positions were in force on every step.

**Calls the model can already make.** A session model can call `delegate`, which opens a child session (`topologies/tool_loop/delegate.py`; the child's `UserMessage` carries `slash_source="delegate"`). It can also call `list_topologies`, `run_topology` and `run_topology_poll`, which run a named application as a child run (`topologies/tool_loop/substrate_tools.py`). No tool lets a model write a new topology. "Build its own topology" is therefore two different controls: one for how readily the model runs an existing topology, available now, and one for authoring a new one, which needs a tool that does not exist yet.

**Measurement.** The language-metrics note (`RESEARCH-2026-10-10-language-metrics-r4.md`) measures the form of every user and model text and the relation between them. The assay harness runs arms against cases over trials. Between them they can tell whether a control does anything.

## 4. What the evidence says about steering by text

**Small wording changes move results a lot.** Formatting changes that keep the meaning of a few-shot prompt shifted LLaMA-2-13B's accuracy by up to 76 points (Sclar et al., ICLR 2024, arXiv 2310.11324). A control's exact text is part of its definition and gets versioned like code.

**Length instructions are followed loosely.** Across 26 models, LIFEBench found length instructions unreliable, especially for long targets. Most models handled short targets reasonably and fell off sharply past a threshold (Zhang et al., NeurIPS 2025 Datasets and Benchmarks, arXiv 2505.16234). A verbosity control works better as a direction (shorter, longer) than as a number of words, and its effect has to be measured, not assumed.

**Person framing: reported, not adopted.** Four studies tested what happens when a model is told it is a person, or is made to act like one. In each, the framing did not help and often did harm.
- *Personas in system prompts.* Across 4 model families, 2,410 factual questions and 162 social and job roles, a persona did not improve accuracy over no persona. Which persona helped on a given question was close to random (Zheng et al., Findings of EMNLP 2024, arXiv 2311.10054).
- *Bias under assigned personas.* Over 24 reasoning datasets and 19 socio-demographic personas, assigning a persona surfaced stereotyped assumptions. For ChatGPT-3.5, 80% of personas showed bias, and some datasets dropped more than 70%. GPT-4-Turbo still showed it in 42% of personas (Gupta et al., ICLR 2024, arXiv 2311.04892).
- *Role-play prompts.* A role-play prompt degraded Llama 3's reasoning on 7 of 12 datasets. The authors' remedy runs a neutral prompt beside it and keeps the better answer (Kim, Yang & Jung, Findings of IJCNLP 2025, arXiv 2408.08631).
- *Warmth.* Fine-tuning five models to be warmer raised their failure rates on safety-critical tasks by 10 to 30 points. It made them about 40% more likely to agree with a user's wrong belief, most of all when the user expressed sadness (Ibrahim, Hafner & Rocher, Oxford; arXiv 2507.21919). That study changed weights, not prompts.

**De-skilling.** In a randomized trial, 52 developers, mostly junior, learned a new Python library. Those using an AI assistant scored 50% on the follow-up quiz against 67% for those coding by hand, with the widest gap on debugging. The developers who handed the coding over entirely learned least; those who asked for explanations and conceptual answers kept most of their learning (Shen & Tamkin, arXiv 2601.20245). The study is the model maker's own research. Its finding runs against the maker's product, which is the one direction in which a manufacturer's paper earns some weight.

## 5. What other tools ship

These are facts of existence: what each product offers. Nothing here adopts their framing, and a manufacturer's description of its own product is PR copy. Its vocabulary is chosen to produce a reaction, not an understanding, so none of it counts as evidence that a feature works.

- **ChatGPT personalities.** A default and four named presets (Cynic, Robot, Listener, Nerd), introduced with GPT-5 in August 2025. This is person framing; Substrate does not do it. Source: press coverage of the launch.
- **Claude styles.** Normal, Concise, Explanatory and Formal, plus custom styles built from a user's writing samples. Source: the vendor's announcement.
- **Claude Code output styles.** Named texts that replace part of the system prompt; this machine's `plain` style is one. Source: vendor documentation, not re-read for this note.
- **OpenAI API `verbosity`.** A request parameter for GPT-5 (`low`, `medium`, `high`), beside `reasoning_effort`. Source: the vendor's cookbook. The vendor's claims about its effect are not used here.
- **Activation steering.** Anthropic's "persona vectors" (August 2025) add directions to a model's internal activations. The name is person framing, and the source is the vendor's own research. It needs access to the weights, which none of Substrate's drivers exposes: the harness CLIs don't, and Ollama's API doesn't.
- **Rule files.** `CLAUDE.md`, `AGENTS.md` and Cursor rules are static text files read at session start.

What these share: one or two dimensions, set as a preset, with the delivered text out of the user's sight. The search behind this note found no product with all four of these properties:
- several independent controls;
- each delivered at its own moment;
- each recorded beside the reply it shaped;
- each with a measured effect.

That covers the products named here, not the market.

## 6. Candidate controls

These are candidates, not a set. Each one names three things: what it changes, how it reaches the model, and what on the record shows whether it worked. A control with no observable is decoration and does not ship. Every position is named for what the text does, never for a kind of person.

### Method: how it works

| Control | Positions | Delivery | Observable |
|---|---|---|---|
| **Source discipline** | standard, strict | methodology; per-turn line when strict | share of cited sources by genre (lookup table of vendor, press and independent domains); presence of a genre label beside each cited claim; marketing-lexicon rate in quoted passages |
| Verification | claim freely, verify before claiming | methodology | tool calls before a reply that states a fact; share of replies with no tool call behind them |
| Research depth | settle and move on, research fully | methodology | `web_fetch` and read calls per turn |
| Ask or act | act unless blocked, ask when unsure | methodology | share of turns that end in a question to the user |
| Planning | act directly, plan first | methodology | a plan in the first reply of a turn; steps per turn |
| Counterargument | off, on contested claims | methodology | needs a lookup-table marker of a counter-position; otherwise not observable by form |

**Source discipline** answers the failure the Architect named: accepting a claim as true because of who published it. A manufacturer's paper, a press release, a vendor's documentation and the words of someone famous in the news all count as claims to check, never as findings. The strict position does three things:
- it makes the model label every source's genre: vendor, press, paid placement, independent study, postmortem, forum;
- it bars a vendor's or a celebrity's statement from standing as evidence on its own;
- it treats marketing vocabulary in a source as a sign of copy written to persuade, a kind of lexical poisoning.

The high guidance text already carries part of this ("Default to skepticism"). The control makes it a dial and makes its effect countable.

### Output form: how the text reads

| Control | Positions | Delivery | Observable |
|---|---|---|---|
| Verbosity | terse, normal, full | style, system channel | tokens per reply; sentences per reply (`LanguageProfile`) |
| Register | plain, formal, technical | style | lexicon rates (hedges, intensifiers, address); excess-vocabulary rate |
| Format | prose first, structured allowed | style | bullets, headings and bold per 1,000 words |

A preset is a named setting of these controls, with an abstract name (`dense`, `plain-terse`). It carries no character.

### Calls: what it reaches for

| Control | Positions | Delivery | Observable |
|---|---|---|---|
| Delegation | never, when the task splits, eagerly | methodology, and the `delegate` tool's description | `delegate` calls per turn; child sessions opened |
| Topologies | never, when one fits, eagerly | methodology, and the `run_topology` description | `run_topology` calls per turn |
| Topology authoring | — | needs a tool that writes a topology; none exists | — |
| Autonomy | report after each step, run to the end | methodology | steps per turn before `Returned` |
| Tool order | read first, act first | methodology | read-type calls before the first write per turn |

The call controls fit Substrate better than anything in §5, because their observables are typed events: a `delegate` call is a `ToolCall` with a name. Their effect can be counted exactly, with no text measure in between.

## 7. Moments: when a control speaks

A static file speaks once. A control in Substrate can choose its moment:

- **At session open,** like the guidance level today.
- **Beside every message,** for a control that drifts. LIFEBench's result suggests length drifts, so verbosity is a candidate for a reminder line. So is strict source discipline.
- **On change.** A control changed mid-session writes `SessionChanged` and its new fragment. The path exists for `bundle` and `per_turn`; controls would add fields.
- **On an event.** A trigger starts a producer that writes a turn-scoped fragment. For example, a `LanguageDrift` event on reply length (language-metrics note, round 4) could start a one-turn reminder of the verbosity position, and a `web_fetch` of a domain on the vendor list could start a reminder that its content is a claim. The control then becomes a feedback loop: a target, a measure on the record, and a correction delivered as text. Each correction is an event, so every action the loop takes is visible.

## 8. Composition and conflict

Controls stack on the level's base text, and some positions contradict it. The high text says "stop when the point is made"; a verbosity position of *full* pulls the other way. Three designs:

1. **The base text wins.** Controls only narrow within the base text's rules. Verbosity *full* then means "complete", not "padded". This is safe, but it limits what a control can do.
2. **The control wins on its own dimension.** The control's fragment comes after the base text and says it overrides the named rule. This is flexible, but the model reads two contradicting texts.
3. **The control rewrites the base.** The level's text is assembled from the control positions, so it never contradicts them. This is the cleanest for the model, but the most work: the base texts become templates.

The model class also limits what helps. Low exists because small models follow fewer rules, and a small model given eight controls may follow none of them well. Which controls a class actually honours is a measurement, per class.

Mechanically, every candidate reuses an existing piece:
- a new `PromptSource` (`control`), session-open;
- one fragment per control, with the control and position named in `provenance`;
- `SessionChanged` for changes mid-session;
- the bundle `extends` chain unchanged underneath.

The positions belong in the session vocabulary as a typed set, as the moves note proposes for moves. An unknown position is then drift the record shows.

## 9. Controls, moves and mastering

The mastering note (§8) splits standing dispositions from per-turn acts: the mastering layer conditions every turn, and a move intervenes on one reply. Controls belong to the standing side. They are the mastering layer cut into dials. The guidance level is the whole layer at one of four sizes; a control is one dimension of it, set on its own.

Moves stay per-turn. Some moves name a control directly: the moves note's `meta/lock/keep-under-N-words` and `stay-in-register` are a one-turn way to set what a verbosity or register control sets for the session. A move could promote itself to a control ("keep this for the session"), which writes `SessionChanged`. The two vocabularies should share names wherever they touch.

## 10. The control surface

Today GUIDANCE is one line under the model column with four levels, and choosing one is required before a session starts. The candidate shape:

- GUIDANCE folds like the model half, with one row per control and the level first.
- The level stays required. Every other control has a default that follows the model, so choosing the level alone still starts a session.
- Keys work as in the model half: arrows to move, ⇧↵ or ⌥↵ to open, ↵ to pick.
- Each row shows its position in grey metadata, and the hint names what the row changes.
- A change after the session starts writes `SessionChanged`, and the transcript shows it.

How many controls fit the bar's height without crowding the model column is a layout question for the design spec.

## 11. Open questions

- **Which controls ship first.** Source discipline and the call controls have clear observables and no counterpart in §5. Verbosity is the one users expect. One from each group would let the assay compare a typed-event measure with a text-form measure.
- **Conflict rule.** Choose one of §8's three designs.
- **Per-class honouring.** Which controls each model class follows, measured before a control is offered for that class.
- **User-authored positions.** A closed, versioned set (as the moves note recommends), or user-written positions in `~/.substrate/` and `<repo>/.substrate/`, resolved like skills.
- **Feedback loops.** Whether a control may correct itself through `LanguageDrift` (§7), and how often, so that corrections do not themselves become noise.
- **The vendor list.** Who keeps the lookup table of manufacturer and press domains that source discipline measures against, and how it is versioned.
- **The guidance hint's wording.**

## Sources

Independent studies:
- Sclar, M., Choi, Y., Tsvetkov, Y. & Suhr, A., "Quantifying Language Models' Sensitivity to Spurious Features in Prompt Design" (ICLR 2024, [arXiv 2310.11324](https://arxiv.org/abs/2310.11324)); read: abstract.
- Zhang et al., "LIFEBench: Evaluating Length Instruction Following in Large Language Models" (NeurIPS 2025 Datasets and Benchmarks, [arXiv 2505.16234](https://arxiv.org/abs/2505.16234)); read: abstract as summarized by search.
- Zheng, M. et al., "When 'A Helpful Assistant' Is Not Really Helpful: Personas in System Prompts Do Not Improve Performances of Large Language Models" (Findings of EMNLP 2024, [arXiv 2311.10054](https://arxiv.org/abs/2311.10054)); read: abstract of the latest version.
- Gupta, S. et al., "Bias Runs Deep: Implicit Reasoning Biases in Persona-Assigned LLMs" (ICLR 2024, [arXiv 2311.04892](https://arxiv.org/abs/2311.04892)); read: abstract.
- Kim, J., Yang, N. & Jung, K., "Persona is a Double-Edged Sword" (Findings of IJCNLP 2025, [arXiv 2408.08631](https://arxiv.org/abs/2408.08631)); read: abstract as summarized by search.
- Ibrahim, L., Hafner, F. S. & Rocher, L., "Training language models to be warm and empathetic makes them less reliable and more sycophantic" ([arXiv 2507.21919](https://arxiv.org/abs/2507.21919)); read: abstract as summarized by search.

Manufacturer research, weighed only where it cuts against the manufacturer:
- Shen, J. H. & Tamkin, A., "How AI Assistance Impacts the Formation of Coding Skills" ([arXiv 2601.20245](https://arxiv.org/abs/2601.20245)); read: the vendor's summary page.

Manufacturer and press material, cited as facts of existence only:
- ChatGPT personalities: [Tom's Guide](https://www.tomsguide.com/ai/chatgpt-5-just-got-4-new-personalities-heres-how-to-use-them-and-why-you-should) (press).
- Claude styles: [announcement](https://www.anthropic.com/news/styles) (vendor).
- OpenAI `verbosity` and `reasoning_effort`: [cookbook](https://developers.openai.com/cookbook/examples/gpt-5/gpt-5_new_params_and_tools) (vendor).
- Activation steering: [persona vectors](https://www.anthropic.com/research/persona-vectors) (vendor research).

Substrate:
- `topologies/session/vocabulary.py`, `topologies/tool_loop/delegate.py`, `topologies/tool_loop/substrate_tools.py`;
- `RESEARCH-2026-10-10-substrate-default-guidance-r7.md`, `ROADMAP-2026-10-10-guidance-levels.md`, `RESEARCH-2026-10-10-language-metrics-r4.md`;
- substrate-ui `web/reveal.html`, `process/planning/OPEN-ITEMS-2026-10-10.md` items 13–15, and the moves and mastering notes of 2026-09-27.
