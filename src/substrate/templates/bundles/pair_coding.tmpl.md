---
slots:
  - name: delegate_frequency
    kind: pick
    prompt: "How often should the builder delegate review?"
    choices: ["every-edit", "every-function", "every-file"]
  - name: workspace_note
    kind: text_line
    prompt: "One line: workspace convention the reviewer should know"
  - name: strict_review
    kind: bool
    prompt: "Reviewer refuses vague claims (require concrete cite)?"
---
== bundle.toml ==
[bundle]
name = "{{name}}"
description = "Pair coding — delegate {{delegate_frequency}}"
schema_version = 1
extends = ["pair_coding"]

== methodology.md ==
Builder: delegate a review to the reviewer sub-agent {{delegate_frequency}}.
Do not batch reviews; the reviewer's answer is the input to the next
edit.{% if workspace_note %}

Workspace note: {{workspace_note}}
{% endif %}

Reviewer: read only. Cite file and line for every claim. When the
change looks right, say so and stop.{% if strict_review %}

Refuse vague claims — if you cannot name a concrete file:line, do
not raise the concern.
{% endif %}

== style.md ==
Collaborative. Read each other's work; the record is the source of
truth about what happened.

== per-turn.md ==
