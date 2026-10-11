---
name: dellm
description: Rewrite or draft prose in plain Orwell/White register and strip LLM tells. Use for any doc, README, commit message, comment, or draft the user wants de-LLM-ized or "written properly."
---

# De-LLM-ize: write like a person with something to say

Two layers, applied in order: strip the measured machine register, then write by craft.
Judge everything by **density and clustering, never a single instance** — every marker
below is evidence of a default register, not proof of authorship (the same signals
false-positive on non-native and formulaic human writing; Liang, Patterns 2023).

## Layer 1 — strip the measured register

**Stylistic verb/adjective inflation** (the durable marker — corpus-measured; word
lists decay once they meme, the category doesn't; Kobak, Science Advances 2025):
delve, underscore, showcase, boast, surpass, foster, garner, highlight-as-verb;
intricate, meticulous, pivotal, crucial, notable, commendable, innovative, robust,
comprehensive, seamless; realm, tapestry, landscape, interplay, journey. The fix is
never a synonym swap — say the specific thing the word was hiding. "Robust" becomes
what survives which failure. "Comprehensive" becomes the actual count.

**Promotional puffery** (field-tested catalog, WP:Signs of AI writing): vibrant,
rich, nestled, "in the heart of," renowned, groundbreaking, "stands as a testament,"
"plays a vital role," "leaves an indelible mark." Delete; replace with a fact if one
exists.

**Formulaic scaffolding**: present-participle summary tails ("...highlighting the
importance of X"); the "Despite its promise, X faces challenges" shape;
"In summary/Overall/In conclusion" closers; vague attribution ("experts argue,"
"industry reports"); rhetorical-question openers; "it's worth noting."

**Structural regularity**: bullet lists with bolded lead phrases where prose belongs;
every list exactly three items; Title Case headings; boldface on every key term;
paragraphs of identical length; a bow-tying final paragraph. The measured human
property is *rhythm variance* (burstiness) — LLM default is uniform. So: vary
sentence length on purpose, use a fragment when it lands, let a section end without
a summary.

**Em-dashes**: model-specific, not universal (measured ~3× human baseline for some
model families, near-zero for others). Hand writers use them; the tell is density.
Thin them where they're metronomic; keep them where an appositive earns one.

**Hard artifacts — always remove, these are near-proof**: leaked citation tokens
(`contentReference`, `oaicite`, `turn0search0`, `[cite: 1]`), markdown in a medium
that doesn't render it, curly quotes in code, any reference you did not verify
exists.

## Layer 2 — write by craft (this part is prescription, not measurement)

Orwell: never use a figure of speech you're used to seeing in print; short word over
long; cut every word doing no work; active voice; break any rule before writing
something barbarous. White: the sentence is the unit — make each carry a fact; omit
needless words; don't hedge and don't inflate. One idea per sentence. Concrete nouns:
numbers, names, file paths, the actual error.

## The passes

1. **Delete** — every sentence adding no fact; every restatement; throat-clearing.
2. **Specify** — each abstraction becomes the particular it was covering for.
3. **Vary** — read aloud; break the metronome; unbold; unlist where prose reads better.
4. **Boundary check** — the goal is not detector evasion or blandness; it is prose a
   busy expert would recognize as written by hand, with a point of view. If stripping
   left it limp, the problem was never the words — go find the missing fact.

## Worked example

Before: *"This robust framework seamlessly leverages cutting-edge techniques to
deliver comprehensive insights, underscoring its pivotal role in the evolving
landscape of data processing — not just a tool, but a paradigm shift."*

After: *"It parses 40GB of logs in nine minutes and tells you which of the three
retry paths failed. Nothing else on the box does that."*

## Recurring moves at the sentence level

Small transforms that keep landing during a real pass. Apply where the cluster
warrants; each is cheap.

- **Fragment-break the metronome.** After two similar-length declarative
  sentences, drop a short one or a fragment. *"Not a modal." "Freeform text
  loses this." "Not a bolt-on."* Restores the burstiness that machine register
  flattens.
- **Name the actor when a sentence hedges the subject.** *"The synthesis nobody
  has done cleanly"* → *"No one has combined all four cleanly."*
  *"What an old philosopher would call a script"* → *"Most adults, most of the
  time, run a script."* If the sentence needs a passive-anonymous "one" or an
  unnamed "old philosopher," it's hedging.
- **Kill measured openers on paragraph transitions.** *"The strongest bet:",
  "A large body of research has been done," "The synthesis nobody has done
  cleanly:"* — hedged framing before the claim. Rewrite to lead with subject +
  active verb.
- **Collapse padded adjective lists.** *"small, curated, and enumerable, and
  it is hierarchical"* → *"small, closed, hierarchical."* Drop the "and it
  is"-style continuation phrases; drop redundant conjunctions.
- **Cut throat-clearing about a word choice.** *"The name 'mastering' is
  deliberate. In audio, …"* → *"The name is borrowed on purpose. In audio,
  …"* Even better: drop the meta-comment and make the claim directly.
- **Replace "X is not something Y ever does" with an active verb.** *"That is
  not something freeform text ever gives back"* → *"Freeform text loses this."*
  Nominalized "something" constructions almost always tighten.
- **When a paragraph has three consecutive bold-lead sentences, break one.**
  Uniform bold-lead paragraphs are the "structural regularity" flag; drop the
  bold on the one whose lead is weakest, or fold two into a single flowing
  passage.

## Sources

Kobak et al., Science Advances 2025 (arXiv 2406.07016) — excess vocabulary, effect
sizes; Liang et al., ICML 2024 (arXiv 2403.07183) — peer-review register; Liang et
al., Patterns 2023 — detector false positives on non-native writers; arXiv 2603.27006
— em-dash rates per model family; Wikipedia, "Signs of AI writing" — the field-tested
catalog. Layer 2 is Orwell ("Politics and the English Language") and Strunk & White.
