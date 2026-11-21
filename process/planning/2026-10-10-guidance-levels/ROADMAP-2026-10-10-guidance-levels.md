# ROADMAP: guidance levels

*2026-10-10, late night.*

**Input.** Open items 1–3 (`substrate-ui/process/planning/OPEN-ITEMS-2026-10-10.md`) and the Architect's direction of 2026-10-10:
- go through the imported Claude text with a fine-tooth comb, make it generic, and `dellm` it;
- offer three levels (high for strong models, medium, low for weak ones) plus the default;
- add a control for the level in the workspace bar.

**Goal.** Every session runs on one of four guidance levels. Each level is a bundle, written for any model and harness, with nothing particular to Claude, one operator or this project. A new session's level follows its model by default, and the operator can choose another in the workspace bar.

## What the texts hold today (read in full, 2026-10-10)

| File | State |
|---|---|
| `bundles/harness/methodology.md` | Substrate's own loop rules, generic. Stays as the default level. |
| `bundles/standard/style.md` | The plain-writing standard. Generic; needs a `dellm` pass. |
| `bundles/standard/per-turn.md` | The reminder line. Generic. |
| `bundles/standard/methodology.md` (16 KB) | Four problems. It opens with Claude Code's own header ("Codebase and user instructions are shown below…"). "No Claude attribution in git, ever" names Claude six times. Several rules speak as the operator ("When I tell you to read a file", "I'd rather have nuance"). "Working rules from memory" is 25 lines of one operator's memory index: a profile of the operator, written as "he", and rules about this project's own code and history. |
| `bundles/standard-small/*` | The short version for small models. Generic. |
| `skills/dellm`, `skills/dellm-small` | Generic. |
| `prompts/default.md`, `prompts/default-small.md` | Substrate's own role prompt. Generic. |

## Decisions

| Decision | What it decides |
|---|---|
| Four levels, four bundles | `harness` (the default level: loop rules only), `standard-low`, `standard-medium`, `standard` (high). `standard-small` is renamed `standard-low`; the old name still resolves (`LEGACY_BUNDLE_NAMES`). |
| The operator's memory leaves the bundle | "Working rules from memory" goes. Memory already loads at session open from `~/.substrate/memory/` and `<repo>/.substrate/memory/` (K276), which is where one operator's rules belong. Rules in it that are general writing or working rules and are not already stated elsewhere move into the methodology, in generic form. |
| One voice | The texts speak about "the user", never as "I"; they name no model, vendor or person. |
| Attribution stated for any model | "No model attribution in git" keeps every rule (no co-author trailer, no generated-by footer, no model credit in a file) and names no vendor. |
| The level follows the model by default | `harness_agent` and `large` get high; a new `medium` class (Ollama models from 14 to under 70 billion parameters) gets medium; `small` (under 14 billion) gets low. The `small` boundary moves from 30 billion to 14 billion so medium has room. A bundle chosen by the operator always wins. |
| Low also picks the small role prompt and skill | As K278 does today for `small`: `default-small`, `dellm-small`. Medium uses the full role prompt and skill. |

## Cards

1. **K287: the high text.** Rewrite `standard/methodology.md` and `dellm` all of `standard`. The four problems above go. The rules stay, each in generic form.
   *Check:* no "Claude", "Anthropic" or "I"/"my" in any shipped guidance text; a test pins that. Golden heads regenerated and the diffs read.
2. **K288: medium and low; the level follows the model.** `standard-medium` (new, written down from high) and `standard-low` (from `standard-small`, after the same edit). A `medium` model class, and `class_variant` mapping class to level.
   *Check:* golden heads for every level; class tests at the new boundaries; the old name still resolves.
3. **U132: the guidance-level control.** A guidance column in the workspace bar, beside or below the model half: default, low, medium, high, preselected from the chosen model's class. The pick goes to the session as its bundle. Folded and greyed like the model half until a folder is armed.
   *Check:* in the installed app, a session opened on each level records that bundle and its head.
4. **K289: amend the specs.** New rounds for product, tech and design specs. Earlier rounds untouched.
