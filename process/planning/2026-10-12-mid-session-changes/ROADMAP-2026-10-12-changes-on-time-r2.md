# ROADMAP: a mid-session change reaches the model with the next message (round 2)

*2026-10-12, round 2, after a pressure test against Substrate's own ideas (the Architect: "adhering … using the correct ideas"). Round 1's fix had the model step record a change and stop early. Three objections: it leaves change detection inside the producer that consumes the prompt, which the postmortem names as the root cause; it records a model step with no prompt and no reply, an event that means nothing; and the kernel already orders this kind of dependency twice, with a trigger predicate over views and a producer whose completion starts the next step (`first-message-on-session-prompt`; `model-on-skill-fragment`). Round 2 uses that shape. Steps and their order are unchanged; K299's design changes.*

## The fix

- **Detection in a predicate.** One helper compares the `SessionSettings` view (the record's last driver, bundle, reminder line, date, length, tone) with the settings the turn runs with. `model-on-user-message` fires only when nothing changed (and, as now, the message names no skill).
- **One producer records the change and writes its text.** A new trigger, `session-prompt-on-user-message-change`, starts the session-prompt producer with the changes. That one run records each `SessionChanged` and writes the rewritten sources for the fields that have them (bundle, per_turn, length, tone), with the message's seq as the generation. Date and driver changes are recorded the same way and write no text.
- **Its completion starts the model.** A new trigger, `model-on-session-prompt-change`, starts the model when that run completes and the turn's first model step has not run.
- **Removed:** the model step's step-0 detection block and the `session-prompt-on-session-changed` trigger.
- **A message that names a skill and follows a change:** the change's run first, the skill's fragment on its completion, the model on the skill's.

The record for the message on which a change is made reads: the message, the change(s), the new text, the prompt, the reply. The history line is drawn from the recorded `SessionChanged` as now.

## Vocabulary v0.10 (§ V)

- `SessionChanged` moves from the model producer to the session-prompt producer.
- The prompt for the message on which a change is recorded carries the new text.
- Two trigger ids added, one removed.

## Steps

| Card | Repo | What | Done when |
|---|---|---|---|
| K300 | kernel | The K274, K296 and K298 change tests check the prompt for the message after the change. | Each fails on the current kernel. |
| K299 | kernel | Vocabulary v0.10; the predicate, the producer run and the two triggers above; the old block and trigger removed. | K300's tests pass, for each rewritten field and two at once, and for a skill message after a change; the record's order is as above; the driver is called once for the message. |
| U167 | UI | `controls_mid_session` reads the prompt for the message after `/tone blunt` and `/guidance low`; a live check. | Fails on the current kernel, passes after K299. |
| K301 | kernel | The length experiment's switch arms again; research round 3. | Round 3 from the new data. |
