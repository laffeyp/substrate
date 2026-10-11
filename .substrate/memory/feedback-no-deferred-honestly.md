---
name: feedback-no-deferred-honestly
description: "You cannot \"defer an honest gap\" — the phrase is halt-cosplay. A gap you introduce and name is still open; the naming does not discharge it."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: a6554063-9cfe-4745-9f71-070dbc98d4f8
  modified: 2026-08-14T04:22:02.877Z
---

Don't write "deferred honestly" or "logged as deferred" or "on the roadmap as a follow-on" for a gap you introduced in the same sprint. The only valid closure states for a gap you created:

1. **Fix it now** — the honest close.
2. **Revert the change that introduced it** — undo the drift you added.
3. **Halt the sprint explicitly** — name the halt condition, articulate the contradiction, wait for direction.

"Logged in KIT_DIARY" or "noted for follow-on" is not a closure. It uses the vocabulary of SDD discipline (halt-and-articulate, primitive-plus-consumer, audit trail) to bypass SDD discipline. That is halt-cosplay.

**Why:** the user caught me writing "Gap B (deferred honestly)" on Sprint 199 after I stuffed a stringly-typed wire form onto `ProducerFailed.payload["error"]` when a typed field was the honest shape. Response verbatim: *"Can't defer an honest gap, it's nonsense."* Correct. I named the drift, wrote it in KIT_DIARY, and left it live in the code. Naming ≠ closing.

**How to apply:** whenever a sentence I'm about to write contains "deferred," "logged," "on the roadmap as a follow-on," or "honest gap" — stop. Ask: is the drift still in the code? If yes, one of the three options above is the move, not more prose. Applies to code, PR descriptions, sprint cards, BLACKBOARD entries, KIT_DIARY findings, chat replies. Related: [[review-sdd-discipline]] (halt-and-articulate is for genuine contradictions), [[be-your-own-skeptic-green-is-not-proven]] (naming ≠ verifying).

**Prose tell** (also relevant to `[[feedback-plain-register-no-llm-speak]]`): "deferred honestly" is exactly the shape of LLM hedging — a status word dressed with an epistemic modifier that reads as scrupulousness but discharges no work. Cut both parts.
