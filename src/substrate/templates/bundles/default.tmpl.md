---
slots:
  - name: role
    kind: text_line
    prompt: "One line: what role should this bundle play?"
  - name: methodology
    kind: text_paragraph
    prompt: "Multi-line: the working methodology (how to approach the task)"
  - name: style
    kind: text_paragraph
    prompt: "Multi-line: how should the model write? (blunt? gentle? terse?)"
  - name: per_turn_prefix
    kind: text_paragraph
    prompt: "Prefixed to every UserMessage; empty for none"
  - name: security_flag
    kind: bool
    prompt: "Ask the model to flag unsafe patterns on every turn?"
---
== bundle.toml ==
[bundle]
name = "{{name}}"
description = "{{role}}"
schema_version = 1
extends = []

== methodology.md ==
{{methodology}}

== style.md ==
{{style}}

== per-turn.md ==
{{per_turn_prefix}}{% if security_flag %}

Flag any unsafe pattern before you leave the file.
{% endif %}
