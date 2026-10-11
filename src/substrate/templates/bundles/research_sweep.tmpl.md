---
slots:
  - name: reader_depth
    kind: pick
    prompt: "Reader depth per document"
    choices: ["skim", "read", "close-read"]
  - name: synthesis_length
    kind: pick
    prompt: "Synthesis length target"
    choices: ["one-paragraph", "one-page", "long-form"]
  - name: cite_source
    kind: bool
    prompt: "Require the synthesis to cite each source document by label?"
---
== bundle.toml ==
[bundle]
name = "{{name}}"
description = "Research sweep — reader {{reader_depth}}, synthesis {{synthesis_length}}"
schema_version = 1
extends = ["research_sweep"]

== methodology.md ==
Reader ({{reader_depth}}): read each document. Extract every finding
that touches the question, one line each, with the document label.

Critic: read the findings across all documents. Name any question the
findings raise but do not answer, and any answer that contradicts
another.

Synthesizer ({{synthesis_length}}): fold the findings into one answer
to the question.{% if cite_source %} Cite each source document by
its label; a claim with no label is not admitted.{% endif %} When
the findings do not answer the question, say so and stop; do not
fill the gap with speculation.

== style.md ==
Thorough. A missing document is a hole in the answer.

== per-turn.md ==
