# ROADMAP: a mid-session change reaches the model with the next message

*2026-10-12. From `POSTMORTEM-2026-10-12-mid-session-changes-arrive-late-r2.md`. A change of guidance (bundle), the reminder line (`per_turn`), length or tone reaches the model's prompt one message after the change: the model step finds the change, records `SessionChanged`, and builds the prompt from the instructions it started with; the recorded change is what starts the rewrite. The Architect's direction: the first message after a change is answered under the new setting.*

## The fix

The kernel already makes the model wait for text it needs: a `/dellm` message starts the skill-fragment producer, and `model-on-skill-fragment` starts the model when that producer completes. A change gets the same shape. On its first step, when a field whose text a change rewrites differs from the record, the model step records `SessionChanged` and stops without building a prompt. One rewrite covers every field changed that step, and its completion starts the model again, which builds the prompt from the new text. The record then reads: the message, the change, the new text, the prompt, the reply. Date and driver changes write no text and keep today's path.

## Steps

| Card | Repo | What | Done when |
|---|---|---|---|
| K299 | kernel | Vocabulary round v0.10 § V: the prompt for the message on which a change is recorded carries the new text. The model step stops after recording a change with rewritten text; one rewrite per step for all changed fields; a new trigger starts the model on that rewrite's completion. | For each of bundle, per_turn, length, tone, and two at once, the `PromptComposed` for the message after the change holds the new text and not the old. |
| K300 | kernel | The K274, K296 and K298 change tests check the prompt for the message after the change, not a later one. | Each fails on the current kernel and passes after K299. |
| U167 | UI | `controls_mid_session` reads the `PromptComposed` for the message after `/tone blunt` and `/guidance low` from the record; a live check on a cloud model asks the reply after `/length terse` and reads its prompt. The transcript's "it applies from the next message" is then true. | The gate fails on the current kernel and passes after K299. |
| K301 | kernel | The length experiment's switch arms run again on the fixed kernel; research round 3 replaces round 2's per-turn reading. | Round 3 written from the new data. |

K300 is written before K299's code (its tests are K299's red). U167 and K301 follow K299.
