# ROADMAP: language measurement

*2026-10-12. The Architect: "prepare to work on language measurement … make sure we have all the research correctly understood, we have a correct roadmap, and we understand the task exactly. Pay extra special attention to the task breakdown on the research phase." Source: `RESEARCH-2026-10-10-language-metrics-r4.md` (the current text; rounds 1–3 read for its history), checked against the repository and the records on 2026-10-12.*

## The task

Measure, without judging meaning, the language of every Substrate session: the user's text, the model's text, the relation between them, and the composed prompt. Keep everything later research needs to build reference distributions. First, find out which measures actually detect what Substrate's controls and guidance levels change.

## What round 4 settles

- **Two kinds of measure only:** form (counting, compression, distributions) and lookup-table meaning (fixed word lists). Both are deterministic and recomputable from the record. Judged meaning and embeddings are out.
- **Four texts:** `UserMessage.text` (excluding `slash_source="delegate"`, which the parent model wrote), `ModelReply.text` (with `stop_reason` separating final answers from text beside a tool call), the relation per turn (paired with the final reply and with all the turn's replies), and `PromptComposed.text`/`.system`.
- **The measures,** each with a window (one text, one turn, sliding, session, many sessions), a shortest useful window, and a basis (sourced, definition, or working value).
- **Mergeability,** which decides storage: counts, frequency tables, n-gram counts, function-word category counts and the sentence-length series merge exactly; the Heaps curve merges at text boundaries; MATTR, MTLD, compression ratio, NCD, phrase copy, cross-window repetition and burstiness are recomputed from text.
- **Three pieces on one library of pure functions:** a producer in the session topology (one-text measures and relation measures as a `LanguageProfile` event; Page–Hinkley within the session as `LanguageDrift`); an app process outside the run (long-window measures, one line per text to `<workspace>/.substrate/language/<session_id>.jsonl`); research later (reference distributions, KS, PSI).
- **Every stored line names** the library version, the preprocessing identity, every parameter, the lexicon versions and the category schema, so a live value and a recomputed one agree.

## What round 4 gets wrong or leaves open

1. **The lexicons are not in the repository.** Round 4 says they are (`skills/dellm/SKILL.md`, "Substrate already ships these lists"). The skill names about twenty of Kobak's words, a few puffery phrases and a few scaffolding phrases as prose examples. There is no hedge list, no intensifier list, no function-word list, no LSM category schema, and not Kobak's 291-word list. Every lexicon has to be built, with its source and licence.
2. **It predates the controls.** Round 4 was written before length and tone existed (K296, 2026-10-11) and before the length experiment (2026-10-12) showed that word count cannot measure terseness: terse removes padding, not content, and the high guidance level already removes padding (`RESEARCH-2026-10-12-length-drift-r2.md`, `-r3.md`). It has no measure of padding (restating the question, background before the answer, closing summaries, offers of more), and none for the tone positions (blunt, formal, dry).
3. **No measure has been validated on Substrate's own output.** The literature cited shows a stylometric footprint between human and model text. Nothing yet shows that any measure moves when a guidance level, a length or a tone changes. Without that, a profile is numbers with no known meaning.
4. **Working values are unset.** The windows marked "working value", MATTR's window, the compression-ratio minimum and the Page–Hinkley δ, λ and warm-up have no values and no plan to set them.
5. **The order is reversed.** Round 1 put a projection over the record first, writing nothing new; round 4 starts with a live producer and two new event kinds. New events are vocabulary, and vocabulary should follow evidence. The measures should be built and validated offline on existing records before any event is added.

## The data that exists

- 77 recorded sessions: 305 user messages, 287 model replies (35,171 words). Drivers: kimi-k2.7 (32 sessions), claude (14), codex (9), cursor-agent (5), others. Mostly unlabeled for any control.
- 1,200 model replies from the two length experiments (`process/runs/assays/length_drift_2026-10-12/`, `…_k299/`), each with its model, arm, turn and length setting. The only labeled corpus. All explanation questions.
- No labeled corpus for tone or guidance level.

## Research phase

Seven tasks, in order. Each is a card with `pass_kind: research`; each ends in a file someone else can check.

| # | Task | Input | Method | Output | Done when |
|---|---|---|---|---|---|
| R1 | **Preprocessing spec v1** | Round 4's preprocessing key | Decide Unicode normalization, case folding, the word tokenizer (apostrophes, contractions, hyphens, URLs, numbers), the sentence splitter (abbreviations, list items, headings), markdown stripping, and code-block handling (out of prose measures, counted in format). | `substrate-text-1` spec, and a fixture set of texts with their expected tokens and sentences, taken from real replies | Every fixture's expected split is written down before code |
| R2 | **Lexicons v1, each with a source and licence** | The measures in round 4 and gap 2 | Kobak's 291 style words (the paper's supplement); hedges and boosters (Hyland's published lists, or an open equivalent); padding phrases (restatement openers, background lead-ins, closing summaries, offers of more), from the guidance texts and from the 1,200 saved replies; address words; contractions and slang (formality); exclamation and enthusiasm words (dryness); an open function-word list and an LSM category schema | One versioned file per lexicon, each naming its source, licence and version | Each list's source is cited and its licence permits shipping it; any list built from Substrate's own replies is marked as such |
| R3 | **Measure library v0** | R1, R2, round 4's definitions | Pure functions for the kind 1, kind 2 and relation measures, plus padding and tone measures from R2's lists | A kernel module with unit tests against hand-computed values; MATTR and MTLD cross-checked against a published implementation | Tests pass; one 1,500-token text in under 5 ms |
| R4 | **Labeled corpora** | The `assay_length_drift.py` pattern | Generate the contrasts that do not exist: tone (four positions), guidance level (harness, low, medium, high), and length (terse, normal, full) on a mixed question set (yes/no, opinion, quick fact, follow-up, explanation), on at least two models | Records and per-reply files under `process/runs/assays/` | Each contrast has a stated size, chosen from the project's power finding, and every reply keeps its labels |
| R5 | **Construct validation** | R3, R4, and the 1,200 length replies | Before looking at results, write down which measures each control position and guidance rule should move, and in which direction. Then compute them and report effect sizes per contrast, per model and per question type | A validation table: measure × contrast, predicted against observed | Each control position has at least one measure that moves as predicted, or a stated finding that none does; measures that move for the wrong reason are named |
| R6 | **Windows and drift calibration** | R3, R4, the switch arms of the length experiment (known change turns) | Check the working-value minimums by subsampling. Tune Page–Hinkley's δ, λ and warm-up for detection rate on sessions with a known change and false alarms on sessions with none | Parameter values with their measured detection and false-alarm rates | Every working value in round 4's window table has a measured value or a stated reason it stays open |
| R7 | **Research round 5** | R1–R6 | Write the corrected note: the five corrections above, the validated measure set, the lexicons, the preprocessing spec, the parameters | `RESEARCH-<date>-language-metrics-r5.md` | Read and signed by the Architect before any build card starts |

R1 and R2 can run together; R3 needs both; R4 can run beside R1–R3; R5 needs R3 and R4; R6 needs R3 and R4; R7 closes the phase.

## Build phase (after round 5)

| # | What | Done when |
|---|---|---|
| B1 | **Offline projection.** A command (`substrate language <record>`) that writes round 4's line format for any record, past or present, adding nothing to the record. | It reproduces R5's numbers from the records alone. |
| B2 | **Vocabulary round and live producer.** `LanguageProfile` and `LanguageDrift` events; the producer on `UserMessage` and `ModelReply`, beside the model step. | A live value equals B1's recomputed value for the same text, under the same versions. |
| B3 | **The app's process.** Long-window measures to `<workspace>/.substrate/language/<session_id>.jsonl`. | Lines rebuild from the record. |
| B4 | **What the app shows.** Not yet designed. | Decided after B1–B3. |

## Later research

Reference distributions (per driver, per guidance level, per user, per task) and the distribution tests (KS, PSI) stay research's, after enough measured sessions exist, as round 4 says.
