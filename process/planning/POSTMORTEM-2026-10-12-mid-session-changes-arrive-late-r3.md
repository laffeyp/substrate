# POSTMORTEM — a mid-session change never reaches the model on its own turn (2026-10-12, round 3)

*Round 3 corrects RC2: K274's own test asserted the delay as intended ("The step that sees the change still reads b1's text; it says so beside the message", then `assert "B1-METHOD" in driver.prompts[1]`). The delay was designed and tested, not missed. Round 2 corrected round 1's scope: only four fields have text a change rewrites (`_REWRITTEN_ON_CHANGE`: bundle, per_turn, length, tone); date and driver changes produce only the history line, which arrives on time. Round 1 counted three date and driver changes as late because another field's rewrite followed them in the same turn.*

*The Architect changed length to full and tone to blunt in a deepseek-v4-pro:cloud session (`s_3ec1557862504de7aa652665`) and asked the model what reached it. The model reported the change lines and said the session had no length or tone setting before. Read against the record, every mid-session change Substrate has recorded since K274 (2026-10-10) reached the model one turn late. The features were built, gated and reported as done on evidence that showed the events were written, never that the model received them on the turn they were for.*

## What the Architect saw

After `/length full`: "That is the first length change in the record. Earlier turns had no length setting at all." Asked what it meant, the model quoted the `full` text and called it "the base instructions". After `/tone blunt`: "Earlier turns carried no tone setting; the base instructions said 'write in a formal register' … two things now pull on tone at once. The base instructions say formal. The environment update says blunt."

## What the record shows

The session opened at length `terse`, tone `formal`, guidance medium; the two control texts were written at seq 12–13, before the first message (seq 19), and were in every prompt. The two changes:

| Seq | Event | The model's system text |
|---|---|---|
| 229 | UserMessage: "I just set something called length to full" | |
| 232 | SessionChanged length terse → full (written by the model step) | |
| 234 | PromptComposed for that message | **terse**, formal |
| 236–237 | the rewritten control fragments: full, formal | |
| 248 | PromptComposed for the next message | full, formal |
| 255 | UserMessage: "what about the tone settings?" | |
| 258 | SessionChanged tone formal → blunt | |
| 260 | PromptComposed for that message | full, **formal** |
| 262–263 | the rewritten control fragments: full, blunt | |

With each message on which a change was made, the history carried "Environment update: length changed from terse to full" while the system text still said "Keep replies short". The model was told of a change it had not been given.

## Scope

Every `SessionChanged` of a field whose text a change rewrites (bundle, per_turn, length, tone) in the user's records: **11 of 11 prompts were built before the rewrite.** Bundle (guidance) 4, per_turn 3, length 3, tone 1, across two sessions. Since K274 (`10fec6f7`, 2026-10-10) no mid-session change of guidance, the reminder line, length or tone has reached the model with the message on which it was made. Date and driver changes write no text; their only effect, the history line, arrives with that message.

What does work: settings chosen when a session opens are in the prompt from the first message; a change's text is in every prompt from the turn after the change; the change line is in the history with the message on which the change was made.

## Root causes

**RC1. The new text is written after the prompt has gone to the model.** When a message arrives, the `model-on-user-message` trigger starts the model step with the instructions as they stand (the fragments `_prompt_input` reads from the `fragment_cohort` view). On its first step the model step compares the session's settings with the record, finds the change and records it as `SessionChanged` (`topologies/session/__init__.py`, the K274 block). It then builds the prompt from the instructions it started with. The recorded `SessionChanged` is what starts the session-prompt producer writing the new text (`session-prompt-on-session-changed`), so that text always lands after the prompt for the message has been sent. Vocabulary § P.4 says a change "writes those sources again" and never says which prompt must carry the new text.

**RC2. The delay was the design, and the test asserted it.** K274 chose to have the step that finds a change still read the old text and say so beside the message; its test asserts exactly that (`assert "B1-METHOD" in driver.prompts[1]`, with the comment "The step that sees the change still reads b1's text"). K296 and K298 built length, tone and guidance on that path; their tests and U161's gate checked the recorded change, the manifest and a later message's prompt, which all hold under the delay. Nobody asked whether a user who changes a setting expects the reply to their next message to follow it; the Architect does.

## Contributing factors

**CF1. Done was claimed from wiring.** U161 and K298 were reported as "guidance, length and tone can change mid-session" on the strength of a recorded event and a passing gate. The standing rule "green is not proven; read what the test checks" was not applied to what a model receives.

**CF2. The app states what was intended, not what happens.** After a change the transcript says "it applies from the next message". It applies from the message after that.

**CF3. The length experiment read late delivery as a finding.** `RESEARCH-2026-10-12-length-drift` rounds 1 and 2 measured reply length per turn with the change applied "before turn 2" and "before turn 5". The instruction reached turns 3 and 6. The short reply seen on turns 2 and 5 came with the change line and the old instruction, which fits round 2's suggestion that the line itself shortens replies. Every figure after a change is one turn off; only the comparison of terse-from-start against normal, which no change touches, was read correctly.

**CF4. The design was settled on top of an unchecked base.** Controls research round 2 chose "system text plus a marker in the history" without checking that the new system text arrived with the message on which the change was made.

## Open question: does the model need to know a setting is set?

No control text says what it is: a length or tone text sits unlabelled among the standing instructions, so when asked, the model calls it a base instruction and says no setting was made. The Architect does not count this a defect (few users ask the model about its settings); whether a named setting ("Length setting: full.") changes replies more than the bare text does is a question to test, not a fault to fix.

## What working looks like

- The prompt built for the message on which a change is recorded carries the new text and the change line together; the old text is gone from it.
- The checks read what the model received: the `PromptComposed` for the message on which the change was made, from the record, for every field `SessionChanged` covers.

## Discipline for prevention

**A feature that shapes the prompt is observed in the prompt.** Its observation contract names the `PromptComposed` of the exact turn the feature is for, and asserts on that text. A recorded event, a manifest field or a later turn's prompt is evidence of wiring.

**A test of a change checks the prompt for the message on which the change was made.** Checking a later message's prompt passes whether the new text arrived on time or a message late.

**Text shown to the user about what the model gets is checked against the record.** "It applies from the next message" is a claim about the prompt.

## One-line summary

Since 2026-10-10 every mid-session change of guidance, the reminder line, length or tone has reached the model one message late: the new text is written after the prompt for the message has been sent, and every check confirmed the change was recorded without reading what the model received.
