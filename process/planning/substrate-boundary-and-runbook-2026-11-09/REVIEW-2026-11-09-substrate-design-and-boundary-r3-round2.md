# Review — the Substrate design paper (r3) and the refactor sequence, round 2

*2026-11-09. Checks whether `REVIEW-2026-11-09-substrate-design-and-boundary-r3.md` has been addressed. That review stands; its finding numbers are used here. Reviewed: `RESEARCH-2026-11-09-substrate-design-and-boundary-r3.md` as edited at 15:32, `SEQUENCE-2026-11-09-substrate-refactor.md` as edited at 15:43, and `evidence-topology-value/` as edited at 15:26. "Paper line 80" and "Sequence line 181" are lines of those versions. Both documents were read in full after those edits. The evidence scripts were re-run. Code is substrate at `0301beca` and substrate-ui at `9266de0`, whose working tree has uncommitted changes.*

*The sequence's new opening part, lines 5 to 76, was checked only against the first review's findings. Its figures for commits, changed files and imported names were not verified.*

---

## Result

The review has not been addressed in full. Of 34 findings, 26 are carried and 8 are carried in part. The changes are to the two documents; the review's findings concerned those documents, and no code has changed.

The findings that stopped the sequence are closed. The design now declares external kinds, lifecycle kinds, multi-kind Triggers and the other builder forms. A name-mapped comparator comes before any renaming conversion. Session names are pinned. Nothing that remains stops stage 0 or stage 1.

The re-run gave 27 events each, zero differences after `RunStarted`, and `mypy --strict` passing on three files including `pinned_name.py`. `twice.py` now prints 1 then 0 firings, which corrects finding 34.

Findings 1 to 8 below are the open parts of the first review. Findings 9 to 11 are faults the edits introduced.

---

## First-review findings carried in part

### 1. A Route has no id rule (first review, finding 6)

Paper lines 209 to 224 declare the missing forms and line 237 states the test's real limits. Line 218 adds `Route(on=..., into=failure, transform=...)`. The names table at lines 261 to 270 has a row for the slot and none for the Route's id, which the record stores (`sequencer.py:370`).

Correction: add a row. `b.instrument` today gives `{name}-stage`, and line 219's instrument declaration needs the same answer.

### 2. `Body` has no typed form for its second parameter (finding 8)

Line 223 adds per-run Producer state and line 784 adds a `RunContext` as "an optional second parameter". `Body` at line 202 still takes one input and a Protocol cannot state an optional positional parameter that a one-argument body omits.

Correction: state a second Protocol for bodies that take the context, and let `Producer` accept either.

### 3. View and Slot names have no pin, and the prototype does not kebab Producer kinds (finding 11)

Line 274 pins Producer kinds and Trigger ids with a closed `StrEnum`. The correction also asked for View and Slot. Session View names appear in `RunStarted.topology.views`, and the document does not say whether they change.

Line 274 says derived forms are kebab-case. `tv.py:36` strips the underscore and does not kebab, so a body named `run_tool` derives `run_tool`.

Correction: give View and Slot the same pin, or state that their names change and that the comparator maps them. `Producer.kind` applies `_kebab`, or line 274 excepts Producer kinds.

### 4. One line still speaks of bytes (finding 15)

Lines 37 and Sequence 128 say equivalence. Line 833 still says "the Golden Master records show the bytes".

Correction: line 833 says the comparison shows the manifest is equivalent.

### 5. The list of visible changes is short by one and one change does not land alone (finding 17)

Line 41 lists three changes a reader sees and says each lands by itself. Line 831 calls the initial-Producers manifest field "a stated addition to the record", and line 41 omits it. Sequence line 227 puts "Blobs resolve by default" inside stage 10's other work.

Correction: line 41 lists four. Stage 10 names blob resolution as its own change.

### 6. Two substrate-ui statements remain inexact (finding 19)

Sequence line 251 finishes when "only `substrate_boundary.py` imports substrate in substrate-ui". `harness/shakeout/handoff_live.ts:53,58` and `topologies_live.ts:127` hold Python that imports substrate, and line 68 keeps them. An import contract on Python files does not see them.

Sequence line 66 says "the 44 `read_record` calls". 44 is the count of `api.read_record` in Python. `scripts/read_trace.py`, two test files and those TS strings also call it. Lines 29 and 68 cover those callers, so only the number is wrong.

Correction: line 251 says "only `substrate_boundary.py` and the listed strings". Line 66 drops the number or says `api.read_record`.

### 7. One sentence still says the specs are corrected (finding 21)

Line 78 and Sequence line 138 say new drafts with the prior ones preserved. Line 80 still says the kernel, product and design specs and `docs/README` "are corrected from it". `docs/README` is corrected in place; the three specs are not.

Correction: line 80 says new drafts for the specs.

### 8. Two counts remain (finding 33)

The other 12 rows of the first review's table are corrected.

| Paper line | Text | Code shows |
|---|---|---|
| 249 | `ctx.views["..."]` (43 sites) | 42 |
| 859 | About 250 sprint references in comments; "across docstrings and comments together there are 553 and 492" | 223 in comment tokens. 553 and 492 count whole-file text; comments and docstrings together give 549 and 481 |

---

## Faults the edits introduced

### 9. Stage 5 allows a field that arrives at stage 10

Sequence line 181 finishes stage 5 with the same events "apart from derived names, `fingerprint.qualname` and the new initial-Producers manifest field". The field belongs to the manifest Struct (paper line 831), which stage 10 introduces (Sequence line 227). A stage 5 record cannot differ by it.

Correction: remove it from line 181 and put it in stage 10's finish condition.

### 10. The constant tables go, and pinned names keep them

Paper line 284 and Sequence line 237 remove the constant tables once names are derived. Paper line 274 and Sequence line 98 pin the session's Producer kinds and Trigger ids with closed enums. Those enums hold the 12 Producer-kind and 21 Trigger-id constants under a new type.

Correction: line 284 says the session's name constants become those enums, and the tables go for event kinds and derived names.

### 11. The evidence folder keeps the old word

`tv.py:1` and the folder name `evidence-topology-value` still say "value", which finding 32 replaced with "declaration". Paper line 230 names the folder, so the name can stay. The docstring should change.

---

## The 34 findings of the first review

Line numbers are the paper's unless marked S, for the sequence.

| # | Subject | Status | Where, or this review's finding |
|---|---|---|---|
| 1 | Kinds from outside refused | carried | 213, 214 |
| 2 | Lifecycle Triggers | carried | 215 |
| 3 | `on` takes one class | carried | 216, 730 |
| 4 | `Ctx.event` drops envelope | carried | 217 |
| 5 | Two roles, one body | carried | 274 |
| 6 | Missing declarations | in part | 209–224, 237; see 1 |
| 7 | Composing whole topologies | carried | 224, 270, 637 |
| 8 | Run and ambient state | in part | 223, 784; see 2 |
| 9 | Value equality, hidden parameters | carried | 132, 185 |
| 10 | Five rejected mistakes | carried | 13, 233 |
| 11 | Derived names, no override | in part | 264–276, S98; see 3 |
| 12 | Lifecycle Struct bytes | carried | 334, 338 |
| 13 | Manifest ownership | carried | 483, 831, 891 |
| 14 | Resume firing state | carried | 502, S158 |
| 15 | Golden Master | in part | 37, S128, S132, S181; see 4 |
| 16 | Claims about names | carried | 274, S98, S179 |
| 17 | Behaviour changes in a refactor | in part | 41, 177, 823, 847; see 5 |
| 18 | Order and content of stages | carried | S106, S148, S158, S215, S227, S235 |
| 19 | substrate-ui lists | in part | S199, S209, S211, S239, S249; see 6 |
| 20 | Parked records after upgrade | carried | S102, S162, S181, S201, S211 |
| 21 | Stage 2 exit, spec amendments | in part | 78, 891, S138, S142; see 7 |
| 22 | Target kernel | carried | 514, 903, 913, 914, 918, 921 |
| 23 | Facts the moves depend on | carried | 554, 556, 570 |
| 24 | Vocabulary work | carried | 891, S138 |
| 25 | Recorded decisions | carried | 39, 639, S148, S249 |
| 26 | `runtime_checkable` | carried | 397 |
| 27 | Public names in import contracts | carried | 514, 598, S249 |
| 28 | Quotations | carried | 47, 439, 528 |
| 29 | Kafka's shape | carried | 131 |
| 30 | Attributions to the specs | carried | 522, 720, 742 |
| 31 | Refactoring names | carried | 255, 276, 401, 504, 575, 649, 736, 817 |
| 32 | "Value" | carried | 13, 100, 132; see 11 |
| 33 | Counts | in part | 122, 198, 562 and others; see 8 |
| 34 | Evidence scripts | carried | 234; `twice.py:13` |
