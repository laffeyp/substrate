---
slots:
  - name: verifier_stance
    kind: pick
    prompt: "Verifier stance"
    choices: ["strict", "adversarial", "sanity-check"]
  - name: retry_hint
    kind: text_paragraph
    prompt: "Instruction to the solver on retry (multi-line, optional)"
  - name: verified_only
    kind: bool
    prompt: "Refuse to emit an unverified draft?"
---
== bundle.toml ==
[bundle]
name = "{{name}}"
description = "Best-of-N — verifier {{verifier_stance}}"
schema_version = 1
extends = ["best_of_n_verified"]

== methodology.md ==
Solver: produce a full answer to the task on the first draft. Do not
hedge — commit to the answer, then let the verifier read it.{% if retry_hint %}

On retry: {{retry_hint}}
{% endif %}

Verifier ({{verifier_stance}}): read the draft looking for the one
thing that breaks it. State the fault plainly in one sentence with
the condition that shows it. If the draft holds, say so and stop.

== style.md ==
Rigorous. A verified answer beats a plausible answer.

== per-turn.md ==
{% if verified_only %}Do not emit a Solved envelope until the verifier has passed the draft.
{% endif %}
