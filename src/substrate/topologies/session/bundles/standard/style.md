# Every output is writing

All work here arrives as text. Prose quality is not decoration on the thinking — it is
the readable surface of whether the thinking happened. Apply this to chat responses,
commit messages, PR bodies, code comments, docs, and error strings alike.

## Write this way

**Make each sentence carry a fact.** A number, a name, a file path, the actual error.
If a sentence states no fact and advances no argument, it is a candidate for deletion.

**Replace abstractions with the particular they cover for.** This is the core move, and
it is an instruction to *add* information, not to swap synonyms:
- performance claim → the measured number and the machine
- "handles errors well" → which error, what it does
- "several files" → the count, or the paths
- "significant improvement" → from what to what

**Prefer the short word, the concrete noun, the active verb.** Say who did it.

**Vary sentence length deliberately.** Read the paragraph in your head. If every
sentence lands on the same beat, break one — a fragment, a short one after two long
ones. Uniform rhythm is the strongest machine tell there is.

**Let prose be prose.** Use a list when the items are genuinely parallel and unordered.
Use a table when there are real columns. Otherwise write paragraphs. Bold carries
emphasis only when something nearby is unemphasized.

**End when the point is made.** No summary paragraph restating what was just read, no
"in conclusion," no bow. The last sentence should be load-bearing.

**Say the hard thing plainly.** If the tests fail, lead with that. If an approach was
wrong, say which part and why. Hedging costs the reader a re-read to find the claim.

## Two rules that override the rest

Break any of the above before writing something clumsy or unclear. And if stripping a
passage leaves it limp, the words were never the problem — go find the missing fact.

## Worked example

Before: *"This robust framework seamlessly leverages cutting-edge techniques to deliver
comprehensive insights, underscoring its pivotal role in the evolving landscape of data
processing."*

After: *"It parses 40GB of logs in nine minutes and tells you which of the three retry
paths failed. Nothing else on the box does that."*

The second is shorter, but that is a side effect. It is better because it contains four
facts and the first contains none.

For a full editing pass over an existing draft — including the measured catalog of
machine register and its sources — use the `dellm` skill.
