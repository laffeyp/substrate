# Demo — Substrate on real runs

A guided read of the runtime working. Every block below is genuine output from a
committed reference record. `bash demo.sh` reproduces the whole walk. The Producers
are deterministic stand-ins — no LLM, no network — so the record is byte-identical
for everyone. Re-running the topology on any machine produces the same events in the
same order, equivalent modulo run ids and timestamps (the D-8 relation), not
byte-for-byte. The record *is* the run; you read it back.

The vocabulary, since every line uses it:

- **Producer** — a callable that takes typed input and emits typed **Events**. An LLM,
  a parser, a transform. Here, deterministic stand-ins.
- **Event** — one numbered fact on the log (`Candidate`, `Row`).
- **Trigger** — starts a new Producer when a condition over the log holds. The
  `substrate.TriggerFired` line records *what input it saw* when it fired.
- **Route** — carries data from past events into a future Producer's input.
- **TerminationPolicy** — decides when the run ends or pauses for outside input.
- Every line prefixed `substrate.*` is a decision the runtime made, written to the
  same log as the data. Nothing lives in memory.

Four commands read each record: `tail` (the whole log in order), `replay` (rebuild
state and re-verify every decision), `inspect` (provenance queries), and
`conformance` (the release gate). All cite sequence numbers.

---

## 1. Ensemble + adjudicator (R-1)

Five Producers race on the same question. A Trigger fires the adjudicator as soon as
three answers are in. Termination cancels the losers.

```
$ substrate tail docs/walkthroughs/records/r1
seq=0   substrate.RunStarted        config={...vocab_version: 0.2}  run_id=01KV1VGAQQ...
seq=1   substrate.TriggerFired      factory=member-m0  firing_key=__initial__  ...
seq=2   substrate.TriggerFired      factory=member-m1  ...
seq=3   substrate.TriggerFired      factory=member-m2  ...
seq=4   substrate.TriggerFired      factory=member-m3  ...
seq=5   substrate.TriggerFired      factory=member-m4  ...        # five members start
seq=6   substrate.ProducerStarted   producer={kind: member-m0 ...}
seq=7   Candidate                   answer=Paris  member=m0
seq=8   substrate.ProducerCompleted producer={kind: member-m0 ...}
seq=10  Candidate                   answer=Nice   member=m1
seq=13  Candidate                   answer=Nice   member=m2
seq=14  substrate.TriggerFired      factory=adjudicator  trigger_id=adjudicate
                                    resolved_input={candidates: [Paris/m0, Nice/m1, Nice/m2]}
seq=17  Candidate                   answer=Paris  member=m3        # m3, m4 still running
seq=20  Candidate                   answer=Lyon   member=m4        #   concurrently with adjudicator
seq=23  Verdict                     answer=Paris  chosen=m0
seq=25  substrate.TerminationMatched decision=finalise-run  policy=any_of(cancel_all_others,all_completed)
seq=26  substrate.RunFinalised
```

Look at seq=14. The adjudicator's Trigger fired the moment three candidates were on
the log, and its `resolved_input` names the exact three it saw (`Paris/m0, Nice/m1,
Nice/m2`) — while m3 and m4 were still running. Their candidates land later, at seq
17 and 20. Concurrency and the "once-enough-are-in" condition both read straight off
the log. The adjudicator emits its `Verdict` at seq=23 and the run finalises under a
composed policy.

Replay rebuilds every intermediate state and re-checks each decision's input against
its recorded hash:

```
$ substrate replay docs/walkthroughs/records/r1 --level 2
[OK] Level 2 replay successful.
Frames replayed: 27
Decisions verified: 6 (all inputs verified by hash)
```

---

## 2. Retry, escalate, pause for operator (R-2)

A malformed input that cannot even be built. An invalid emission that gets
quarantined. The failure reason routed back into a retry. A bounded retry that
escalates. A run that pauses to wait for an operator and then resumes. All on one
log.

```
$ substrate tail docs/walkthroughs/records/r2
seq=3   Row                              raw=alpha  row=0
seq=7   Row                              raw=gamma  row=2
seq=9   Row                              raw=delta  row=3
seq=10  substrate.InputBuildFailed       error=ValueError('malformed row 3...')  trigger_id=to-transform
seq=13  Transformed                      attempt=1  row=0                         # row 0: clean
seq=16  substrate.ProducerEmittedInvalidEvent  raw_payload={junk: <<invalid>>, row: 1}  reason=unknown_kind
seq=17  substrate.InjectionApplied       route_id=failure-context  target_input_slot=failure
seq=18  substrate.TriggerFired           trigger_id=retry  resolved_input={attempt: 2, prior_reason: unknown_kind, row: 1}
seq=26  Transformed                      attempt=2  row=1                         # row 1: recovered on retry
seq=29  substrate.ProducerEmittedInvalidEvent  raw_payload={<<persistently-invalid>>, row: 2}  reason=unknown_kind
seq=31  substrate.TriggerFired           trigger_id=escalate  resolved_input={attempts: 2, reason: unknown_kind, row: 2}
seq=34  RetryExhausted                   attempts=2  reason=unknown_kind  row=2
seq=35  substrate.TerminationMatched     decision=pause-await-input  resume_condition=OperatorOverride
seq=36  OperatorOverride                 note=operator approved manual recovery  row=2
seq=37  substrate.TriggerFired           trigger_id=on-override  resolved_input={by: operator, row: 2}
seq=39  Recovered                        by=operator  row=2
seq=41  substrate.TerminationMatched     decision=finalise-run
seq=42  substrate.RunFinalised
```

Four different failures, each legible.

At seq=10, row 3 was too malformed to even construct the transform's input.
Recorded, not crashed.

At seq 16 through 26, row 1's Producer emits an event of unknown kind. The runtime
quarantines it (`ProducerEmittedInvalidEvent`). A Route injects the failure reason
back as input (`InjectionApplied` → `target_input_slot=failure`). The `retry`
Trigger fires carrying that reason (`prior_reason: unknown_kind`). The retry
succeeds at seq=26.

At seq 29 through 34, row 2 fails a second time. The bounded policy gives up. The
`escalate` Trigger fires, producing `RetryExhausted`.

At seq 35 through 41, the run pauses (`pause-await-input`) with a named resume
condition. When an `OperatorOverride` event arrives at seq=36, the `on-override`
Trigger spawns a recovery Producer and the run finalises.

```
$ substrate replay docs/walkthroughs/records/r2 --level 2
[OK] Level 2 replay successful.
Frames replayed: 43
Decisions verified: 8 (all inputs verified by hash)
```

---

## 3. Streaming synthesis + concurrent checking (R-3 inner)

One Producer streams output. Another fires per completed unit *as it arrives*,
running alongside the still-streaming first one. (R-3's outer run wraps this as an
embedded sub-run — composition — and emits a single `OuterArtifact`; the interesting
part is inside.)

```
$ substrate tail docs/walkthroughs/records/r3-inner
seq=3   CodeChunk      text="def add(a, b):"
seq=4   CodeChunk      text="    return a + b"
seq=5   substrate.TriggerFired  factory=ast  firing_key=0  trigger_id=on-declaration
                       resolved_input={index: 0, source: "def add(a, b):\n    return a + b"}
seq=6   CodeChunk      text="def mul(a, b): ..."         # writer keeps streaming
seq=7   substrate.TriggerFired  factory=ast  firing_key=1  trigger_id=on-declaration
seq=10  Declaration    index=0  source="def add..."
seq=11  substrate.TriggerFired  trigger_id=to-typecheck
seq=18  TypecheckOk    index=0  ok=True
seq=22  TypecheckOk    index=1  ok=True
seq=25  ArtifactReady  declarations=1
seq=28  substrate.RunFinalised
```

At seq=5 the `on-declaration` Trigger fires for the first complete declaration
(`firing_key=0`). At seq=6 the writer emits its next chunk. The checker is working
on declaration 0 while the writer is still producing declaration 1. Each declaration
flows independently through `ast → typecheck → artifact`. The per-declaration keys
(`firing_key=0`, then `1`) are how the Trigger fires once per unit rather than once
per event.

```
$ substrate replay docs/walkthroughs/records/r3-inner --level 2
[OK] Level 2 replay successful.
Frames replayed: 29
```

---

## 4. Provenance — causality read off the log

Because every decision is on the log, ask why any Producer exists and get the full
causal chain back to run start. No tracing, no guessing.

```
$ substrate inspect docs/walkthroughs/records/r3-inner \
    --producer "artifact[01KV1VGAYWVBTJ35V5Q54W7A72]" --ancestry
artifact[01KV1VGAYWVBTJ...]   caused_by TriggerFired at seq=19 (trigger=to-artifact)
typecheck[01KV1VGAYNJN...]    caused_by TriggerFired at seq=11 (trigger=to-typecheck)
ast[01KV1VGAYK13...B]         caused_by TriggerFired at seq=5  (trigger=on-declaration)
writer[01KV1VGAYK13...A]      caused_by RunStarted    at seq=1  (trigger=__initial__)
```

`inspect --why` gives the single proximate cause; `--ancestry` walks it back to
`RunStarted`. Both cite sequence numbers, so every claim is checkable against `tail`.

---

## 5. The release gate — conformance

The three runs above show the runtime doing things. Conformance is the standing check
that it does the *required* things: one canonical topology per spec property, run as
the v1.0 release gate.

```
$ substrate conformance --no-perf
Running 17 conformance checks (product §7)...
  [01/17] Retry enrichment            ... PASS
  [02/17] Single legal cascade        ... PASS
  [03/17] Backpressure liveness       ... PASS
  [04/17] Invalid-emission cascade    ... PASS
  [05/17] Quiescence                  ... PASS
  [06/17] Replay round-trip           ... DEFERRED (spec-amended A1.1)
  [07/17] Export boundary             ... PASS
  [08/17] Quarantine visibility       ... PASS
  [09/17] Determinism                 ... PASS
  [10/17] Persistent-bus locking      ... PASS
  [11/17] Provenance closure          ... PASS
  [12/17] View-at fidelity            ... PASS
  [13/17] Divergence localization     ... PASS
  [14/17] Diagnostic invariance       ... PASS
  [15/17] Performance floor (N-PERF-1)... SKIPPED (--no-perf)
  [16/17] Torn-tail recovery          ... PASS
  [17/17] InputBuildFailed visibility ... PASS

15 passed, 0 failed, 1 deferred, 1 skipped. No check FAILED.
```

Two honest notes, both deliberate.

Check 6 (replay round-trip) is deferred, not passed. Level 2 replay — state and
decision reconstruction, verified by hash — ships and passes. Full byte-for-byte
re-execution (Level 3b) is post-1.0 under spec amendment A1.1. The suite reports it
as deferred rather than quietly counting it green.

Check 15 (performance floor) is hardware-dependent, so it is excluded from CI
(`--no-perf`) and run on controlled hardware. The floor is 40,000 appends/sec; the
shipping implementation measures around 56,000 on commodity hardware and passes. The
dominant per-append cost is the RFC-8785 canonical-JSON encode, which is
correctness-critical. The 100k floor in earlier drafts predated that encode; it was
revised down to 40k with a recorded reason (product amendment A2). The number moves
with the host, which is exactly why it is not a CI gate. Checks 1–14 and 16–17 are
hardware-independent and pass everywhere.

The full test suite passes (`uv run python -m pytest` — the `python -m` uses the
project's pinned pytest rather than whatever `pytest` resolves on PATH). The
public-API import boundary is enforced by `import-linter` in CI on every push.

---

## Run it yourself

The records above are in a source checkout of the repository. From its root:

```
uv venv --python 3.12 && uv pip install -e ".[dev]"
bash demo.sh                       # the whole walk, against committed records
uv run python -m pytest            # the full suite (about 1,700 tests; realmodel tests run live when Ollama is present)
uv run substrate conformance       # the release gate (includes the perf floor)
```

With a pip install (`pip3 install --upgrade substrate-kernel`, then `python3 -m substrate install`), the
bundled records replay without a checkout: `substrate demo replay code_review`.

The committed records are deterministic CI-mode artifacts. For the same topologies
driven by a real local LLM, see `docs/walkthroughs/README.md`.
