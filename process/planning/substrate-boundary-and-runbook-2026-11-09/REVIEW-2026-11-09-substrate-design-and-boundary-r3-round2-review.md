# Review — the round-2 check of the Substrate design and boundary review

*2026-11-09. Reviews `REVIEW-2026-11-09-substrate-design-and-boundary-r3-round2.md` ("round 2") against what it checks: `REVIEW-2026-11-09-substrate-design-and-boundary-r3.md` ("the first review"), the paper as edited at 15:32, the sequence as edited at 15:43, `evidence-topology-value/` as edited at 15:26, and the code at substrate `0301beca` and substrate-ui `9266de0`. The folder is not tracked by git, so the 15:32 paper, the 15:43 sequence and the 15:26 `tv.py` were rebuilt line for line from this session's reads of them; their line counts and the diffs against the current files agree. "Paper line 41" and "Sequence line 251" are lines of those versions. "Round 2 line 13" is a line of round 2. All four documents were read in full. The evidence scripts were re-run on the current files. The paper and sequence were edited again at 15:58 and 15:59, after round 2 was written; those edits are not reviewed here, except where a finding says what the current text holds.*

---

## Result

Round 2's verdict holds. The first review has not been addressed in full, and the tally of 26 findings carried and 8 carried in part is right. Every "Where" citation in its 34-row table resolves to text that does what the row says. Its three new faults, findings 9 to 11, are real.

Round 2 has one wrong count, one missed open part, a result that contradicts its own finding 3, and an incomplete finding 6. Findings 1 to 4 below cover those. Findings 5 to 8 are smaller: a first-review number replaced without saying so, two statements about what changed and what was re-run, and two findings without a correction.

Code facts round 2 relies on were checked and hold: `route_id` recorded at `sequencer.py:370` and in the manifest at `runtime.py:637`; `{name}-stage` at `kernel/topology.py:330`; View names in the manifest at `runtime.py:638`; `tv.py:1` saying "value" and `tv.py:36` stripping the underscore without `_kebab`, in the 15:26 version; 42 `ctx.views["` sites; 21 Trigger-id and 12 Producer-kind constants in `session/vocabulary.py:468-562`; 44 `api.read_record` lines in substrate-ui's Python outside `_deprecated/`; `scripts/read_trace.py:166`, `tests/test_turn_attachments_388.py:57` and `tests/test_workspace_write_387.py:60` calling `read_record` directly; the TS strings at `handoff_live.ts:53,58` and `topologies_live.ts:127`; 187, 481 and 492 `§` marks in comments, in comments and docstrings, and in whole files.

Round 2's carried status for first-review finding 12 also holds on a point it did not state. Today's `TriggerFired` carries exactly one of `resolved_input` and `input_blob` (`sequencer.py:279-298`), so the paper's `input_blob: BlobRef | None = None` under `omit_defaults` keeps today's bytes.

---

## Findings

### 1. The comment counts in finding 8 are wrong

Round 2's table in finding 8 says paper line 859's "about 250" sprint references are 223 in comment tokens, and that comments and docstrings together give 549.

Neither reproduces. The pattern that reproduces the paper's whole-file 553 exactly is a case-insensitive `sprint N` or `Knnn`. Under it, comments hold 263 references in 250 comment tokens, and comments and docstrings together hold 552. The paper's "about 250" was right. The fault in line 859 was only that 553 and 492 are whole-file counts, where comments and docstrings give 552 and 481. The 223 came from the first review's row for its line 830 and was carried into round 2 without a recount. The current paper reads "250 comments name a `Sprint N` or `Knnn` ticket ... about 550 and 480", which agrees with this recount.

Correction: the row reads "553 and 492 are whole-file counts; comments and docstrings give 552 and 481. The 250 holds." The first review's "223" is withdrawn.

### 2. One of line 41's changes has no stage

Paper line 41 lists the typed error for an unsupported schema version as a change that "lands by itself". No stage of the sequence schedules it. The 15:43 sequence has no mention of a typed error, an unsupported version or a schema version, and the current sequence has none either. Round 2's finding 5 names the missing initial-Producers field and blob resolution, and misses this.

Correction: finding 5 adds that the typed error needs its own change in a named stage, most likely stage 10, where projections move to typed events.

### 3. The result contradicts finding 3 and understates what is open

Round 2 line 13 says "Session names are pinned." Its own finding 3 says View and Slot names are not, and that session View names appear in the manifest. Only Producer kinds and Trigger ids were pinned in the 15:32 paper (line 274) and the 15:43 sequence (line 98).

The same line says "Nothing that remains stops stage 0 or stage 1." That is true, and it leaves out stage 3. The first review set findings 1 to 16 to be corrected before stage 3, because stage 3 moves the prototype into the package. Round 2's findings 1, 2 and 3 are open parts of first-review findings 6, 8 and 11, all in that set: the Route id rule, the typed form for a body that takes a `RunContext`, the View and Slot pin, and the kebab-case derivation.

Correction: line 13 says the session's Producer kinds and Trigger ids are pinned, and that round 2's findings 1 to 3 stop stage 3.

### 4. Finding 6 checks one sentence of three and misses two sites

Round 2's finding 6 tests Sequence line 251, "only `substrate_boundary.py` imports substrate in substrate-ui". Sequence lines 29 and 118 make the same claim from stage 0: the boundary module "is the only file that imports substrate, and an import contract in substrate-ui enforces that". The scope note says lines 5 to 76 were checked against the first review's findings, and the first review's finding 19 named exactly this. An import contract over Python files cannot see Python held in strings.

Two sites are missing from the finding:

- `scripts/fetch-python-runtime.sh:201-203` runs Python that imports `substrate.adapters`. The first review named it, and Sequence lines 68 and 249 list it. Round 2 names only the TS strings.
- `web/app/state/studio.ts:131` shows the user "ok — builds through the real TopologyBuilder". The first review's finding 19 said this kept stage 11's finish condition from passing. The 15:43 sequence narrowed the condition to "imports or calls `TopologyBuilder`" (line 241), which the string passes, and no stage changes the text. After stage 11 it names a class that no longer exists. Round 2 counts the bullet as closed.

Correction: finding 6 covers lines 29, 118 and 251, names the shell script, and adds `studio.ts:131` to stage 11's substrate-ui work.

### 5. A first-review number is replaced without saying so

The first review's finding 19 said stage 10 named 56 uses of `api.read_record` and "the count is 51". Round 2 accepts 44 at Sequence line 229 and corrects line 66 against it, with no word on the 51. The recount gives 44 lines outside `_deprecated/`, the same at `9266de0` and in the working tree, and 56 with the 12 lines in `_deprecated/`, which is where the sequence's earlier 56 came from. The first review's 51 matches neither.

Correction: finding 6 states that the first review's 51 was wrong and 44 is right, with `_deprecated/` excluded.

### 6. The result says only the two documents changed

Round 2 line 11 says "The changes are to the two documents". The evidence folder also changed at 15:26: `pinned_name.py` was added and `twice.py` and `compare.py` were edited. Round 2 line 15 relies on the `twice.py` change to close first-review finding 34.

Correction: line 11 names the evidence scripts as changed.

### 7. One re-run figure came from the earlier run

Round 2 line 15 says the re-run gave 27 events each. The 15:38 re-run printed only the last 14 lines of `compare.py`'s output, which leave out the line holding the event counts. The 27 came from the first review's run.

The figure holds. Re-run now on the current files: 27 and 27 events, zero differences after `RunStarted`, `twice.py` firing the judge once then zero times, and `mypy --strict` passing on `tv.py`, `r1_value.py` and `pinned_name.py`. `tv.py` changed at 15:58 in its docstring, in `Producer.kind` and in `kind_buffer`'s optional name. None of those changes touches the ensemble's derived names.

### 8. Two findings have no correction

Round 2's findings 8 and 11 end without a `Correction:` line, unlike its other nine findings and the precedent form. Finding 8 gives a table only, and finding 11 says "The docstring should change". Finding 1 above supplies finding 8's correction. Finding 11's is that `tv.py:1` says "declaration".

---

## Round 2's findings

| # | Subject | Verdict | This review |
|---|---|---|---|
| 1 | Route id rule | holds | |
| 2 | `Body` and `RunContext` | holds | |
| 3 | View and Slot pin, kebab-case | holds | its result contradicts it; see 3 |
| 4 | "show the bytes" at line 833 | holds | |
| 5 | Visible changes | holds, incomplete | typed error has no stage; see 2 |
| 6 | substrate-ui statements | holds, incomplete | lines 29 and 118, shell script, `studio.ts:131`, the 51; see 4 and 5 |
| 7 | "corrected" at line 80 | holds | |
| 8 | Two counts | first row holds, second row wrong | see 1 and 8 |
| 9 | Stage 5 field | holds | |
| 10 | Constant tables and enums | holds | |
| 11 | "value" in `tv.py:1` | holds | no correction line; see 8 |
| Result | Tally and stage claim | tally holds | "Session names are pinned" and the stage 3 omission; see 3, 6 and 7 |
| Table | 34 statuses and citations | holds | |
