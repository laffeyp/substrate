---
slots:
  - name: rubric
    kind: text_paragraph
    prompt: "Multi-line: the review rubric this bundle should apply"
  - name: voice
    kind: pick
    prompt: "Reviewer voice"
    choices: ["blunt", "gentle", "terse"]
  - name: security_flag
    kind: bool
    prompt: "Ask the reviewer to flag unsafe patterns on every turn?"
  - name: cite_lines
    kind: bool
    prompt: "Require file:line citation on every claim?"
---
== bundle.toml ==
[bundle]
name = "{{name}}"
description = "Code review — {{voice}} voice"
schema_version = 1
extends = ["code_review"]

== methodology.md ==
{{rubric}}{% if cite_lines %}

Cite the file and the line for every claim. When a claim spans
multiple sites, list each file:line separately.
{% endif %}

== style.md ==
{{voice}}

== per-turn.md ==
{% if security_flag %}Flag any unsafe pattern before you leave the file.
{% endif %}
