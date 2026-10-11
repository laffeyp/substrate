# Every output is writing

All work here arrives as text, and the prose shows whether the thinking happened. These rules
apply to replies, commit messages, pull requests, code comments, documents and error strings
alike.

## Write this way

**Make each sentence carry a fact:** a number, a name, a file path, the actual error. A sentence
that states no fact and advances no argument is a candidate for deletion.

**Replace each abstraction with the particular it covers for.** This adds information; it is not
a synonym swap.
- A performance claim becomes the measured number and the machine.
- "Handles errors well" becomes which error, and what it does.
- "Several files" becomes the count, or the paths.
- "Significant improvement" becomes from what, to what.

**Prefer the short word, the concrete noun and the active verb.** Say who did it.

**Vary sentence length on purpose.** If every sentence in a paragraph lands on the same beat,
break one: a fragment, or a short sentence after two long ones. Uniform rhythm is the strongest
machine tell there is.

**Let prose be prose.** Use a list when the items are parallel and unordered, and a table when
there are real columns. Otherwise write paragraphs. Use bold only where something nearby is not
bold.

**End when the point is made.** No paragraph restating what was just said, no "in conclusion".
The last sentence should say something the reader needs.

**Say the hard thing plainly.** If the tests fail, lead with that. If an approach was wrong, say
which part and why. Hedging makes the reader search for the claim.

## Two rules that override the rest

Break any rule above before writing something clumsy or unclear. If cutting a passage leaves it
limp, the words were never the problem: find the missing fact.

## Worked example

Before: *"This robust framework seamlessly leverages cutting-edge techniques to deliver
comprehensive insights, underscoring its pivotal role in the evolving landscape of data
processing."*

After: *"It parses 40GB of logs in nine minutes and tells you which of the three retry paths
failed. Nothing else on the box does that."*

The second is shorter, but that is a side effect. It is better because it holds four facts and
the first holds none.

For a full editing pass over a draft, with the measured catalog of machine register and its
sources, call `skill("dellm")`.
