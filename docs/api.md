# API reference — `substrate.api`

The complete public surface (F-API-1). Everything else is private; the CLI imports only
this module (F-API-6). **This page is GENERATED from the live `substrate.api.__all__` and
the symbols' own docstrings** (`scripts/gen_api_docs.py`) so it cannot drift from the
code. Regenerate (`uv run python scripts/gen_api_docs.py`) after any public-surface change.

## Data types

### `Event(seq: int, kind: str, schema: str, producer: substrate.types.ProducerRef | None, t: float, payload: Any)`

One bus event, persisted as one frame (technical §3.4).

`seq` is the bus sequence number (identity + total order, assigned at append).
`kind` is the event kind ("substrate." prefix reserved). `schema` is "<kind>@<ver>".
`producer` is the emitting Producer's ref, or None for runtime-emitted events.
`t` is a supplementary wall-clock timestamp (never used for ordering; excluded
from the D-8 equivalence relation). `payload` is the inline payload or a blob
reference. The `crc` field is added by the record layer at frame time (§3.3),
not carried on the in-memory Event.

### `BlobRef(sha256: str, bytes: int)`

Reference to a content-addressed payload in the blob store (technical §3.7).

Serialized in an envelope payload as {"$blob": "sha256:<hex>", "bytes": n}; this
Struct is the typed in-memory form. `sha256` is the canonical-bytes hash; `bytes`
is the stored length.

### `ProducerRef(kind: str, instance: str, parent: str | None = None)`

A Producer's on-the-wire identity (envelope `producer` field, technical §3.4).

Distinct from the in-memory ProducerId {kind, instance_id, parent_id, metadata}
(kernel Decision #2): the wire form carries only what a reader needs to identify
and link the Producer. `parent` is the spawning Producer's instance, or None for
topology-declared initial Producers.

### `Subscription(kinds: frozenset[str] = frozenset(), producers: frozenset[str] = frozenset())`

What a Predicate / View / Route is consulted on (technical §16, §6.5).

The writer's subscription index consults a subscriber only when an event matches
its `kinds` and/or `producers`. Both empty is a registration error (enforced at
topology registration, not here); "subscribe to everything" must be spelled
explicitly. Frozensets keep the subscription immutable and hashable.

## Primitives & protocols

### `Producer(*args, **kwargs)`

A callable `(input) -> AsyncIterable[Event]` (kernel §1; design §4.2/§9.6).

The factory returns this callable per instantiation; the runtime calls it with the
sealed, resolved input and consumes the event stream until the Producer completes,
fails, or is cancelled — emitting the corresponding lifecycle event. A Producer has
no runtime-level identity, planning, or goal state (kernel non-goals); state lives
on the log.

NOTE (flow-back): technical §16 shows the object-with-`.start()` form; design §9.6
chooses the callable form deliberately (simpler, asyncio-native, no class
hierarchy) and rejects the class form. We follow the design spec; technical §16
should be updated to the callable form to match.

### `ProducerFactory(*args, **kwargs)`

_(no docstring)_

### `Responder(*args, **kwargs)`

The application-layer model seam: turn a prompt into a text response. A Producer depends
on this, not on a concrete model — CI hands it a deterministic stand-in, the walkthrough a
real local LLM. NOT a kernel primitive (the runtime never sees it); it lives among the
structural protocols because, like Producer and View, the user implements it by shape.
The reference adapters (DeterministicResponder, OllamaResponder) live in `substrate.reference`.

### `View(*args, **kwargs)`

A deterministic incremental projection over the bus (kernel §4).

Updated synchronously in append-cycle step 3, before any Route or Predicate.
`deterministic` declares whether `value()` is composed of RFC-8785-encodable
types and so participates in N-DET-1 (its state re-derives identically on replay);
a View holding non-canonical types sets it False and is flagged
`determinism: excluded` at registration (technical §4.2). (N-DET-1 is View-state
determinism — distinct from full byte-identical L3b re-execution, which is post-1.0.)

### `TriggerContext(event: 'Event', views: 'Mapping[str, View]', staged: 'Mapping[str, Any]') -> None`

What a Trigger's `predicate` and `input_builder` callbacks receive — both take ONE of
these: `predicate(ctx) -> bool` decides whether the Trigger fires; `input_builder(ctx) -> input`
builds the started Producer's input. One context is constructed per appended event and shared
by every Trigger's callbacks, so it allocates once per event, not per evaluation.

- `event`  — the just-appended Event that matched the Trigger's subscription.
- `views`  — the named Views (deterministic projections over the bus); read
             `ctx.views["name"].value()`.
- `staged` — the Route slots: data a Route staged forward for this firing; read
             `ctx.staged.get("slot")`. (A predicate may read it too; usually only the
             input_builder does.)

### `BufferView(producer: 'str') -> 'None'`

Accumulated payloads from one Producer kind (kernel §4 — the most common View).

MEMORY (same class as PerKey's N-MEM-1): holds EVERY matching payload for the run's lifetime —
unbounded for a high-volume kind — and `value()` returns an O(history) copy, so a Predicate
that scans it each event is O(history)/event (→ quadratic over the run). For a long,
high-volume kind use KindCount / PerKindLatest, or a bounded/windowed View, not a growing
buffer. Negligible at small scale (tens–hundreds of items); a real cost only in the thousands.

### `KindBuffer(kind: 'str') -> 'None'`

Accumulated payloads of one event KIND (a kind-subscribed sibling of BufferView, which
subscribes by Producer kind). Useful when several Producer kinds emit the same event kind
and a Predicate gates on the aggregate (e.g. R-1's "≥K Candidate answers" Bus-view).

MEMORY: same unbounded-growth + O(history) `value()` caveat as BufferView (above) — use
KindCount / PerKindLatest or a bounded View for a long, high-volume kind.

### `KindCount(kind: 'str') -> 'None'`

Count of events of one kind.

### `PerKindLatest(kind: 'str') -> 'None'`

Latest payload seen for one kind.

### `StartedCompletedCounts() -> 'None'`

Per-Producer-kind started vs ended (completed+failed+cancelled) counts — the
substrate of the progress-gating / cohort-frontier predicate (kernel §"Progress
gating"). Keys on the subject Producer identity carried in the lifecycle payload
(P-SUBJECT-ID, ratified into vocabulary v0.1).

### `Once() -> 'None'`

First satisfaction fires; further satisfactions ignored.

### `PerEvent()`

Each newly-satisfying event fires the Trigger once.

### `PerKey(fn: 'Callable[[Event], Any]') -> 'None'`

One firing per distinct key extracted from the event (CEP window-and-key).

N-MEM-1 (memory bound — documented behavior, v1.0): `_seen` grows by one canonical-key
entry per DISTINCT key the Trigger ever fires on, for the lifetime of the run. It is NOT
evicted. For a bounded-key topology (e.g. PerKey over a fixed set of categories) this is
O(distinct keys) and fine. For an UNBOUNDED-key, long-running topology (e.g. PerKey over a
per-message id that never repeats) `_seen` grows without bound — the dedup set is the cost
of the "fire exactly once per key, forever" guarantee. v1.0 does NOT bound it: a windowed
/ LRU eviction would silently let an evicted key RE-FIRE (a dedup-correctness change, not a
free optimization), so it needs a decision (a key-window/TTL on PerKey) rather than a quiet
cap. The operational guidance for v1.0: do not key PerKey on an unbounded-cardinality field
in a long-lived run; use PerEvent (no dedup state) or a bounded key. (Route `staged` is
bounded by construction — keyed by the static set of declared Route slots, latest-wins per
slot — so it is NOT part of this growth; only `_seen` is.)

### `WhileTrue(cooldown: 'Cooldown | None' = None) -> 'None'`

Fires continuously while the predicate holds, throttled by a cooldown.

The cooldown is a TRIGGER-level concept (kernel §6 — "throttled by a cooldown"):
cooldown enforcement lives in the runtime, which owns the single, replayable
append-counter (subscription-matched cycles) and the wall-clock clock + replay-ceiling
demotion. WhileTrue therefore does NOT self-throttle (that would double-enforce);
`cooldown` is exposed so TopologyBuilder.trigger can lift it to the trigger level.

### `Logical(appends: int = 0)`

Cooldown counted in append cycles (deterministic, replayable).

### `WallClock(seconds: float = 1.0)`

Cooldown in seconds. Opt-in; flagged at registration; demotes replay to 3(b).

### `TerminationPolicy(name: 'str', fn: 'Callable[[TermContext], Decision]', resume_condition: 'str | None' = None, finalisation: 'Callable[[TermContext], Any] | None' = None) -> 'None'`

A named decision callback. `name` is recorded in substrate.TerminationMatched.

`finalisation`, when set, is a callable run at finalise-run time that produces the
run's final output payload; it is recorded in substrate.RunFinalised.finalisation_payload
and surfaced on RunResult.finalisation_payload. None → no payload (an empty RunFinalised).
The payload must be canonical (§4.2); a non-canonical payload is dropped to None with the
failure noted, never crashing finalisation.

### `Decision(*values)`

The verdict a TerminationPolicy returns each cycle. v1.0 ships four of the kernel §8
outcomes: CONTINUE (do nothing), FINALISE_RUN (end the run), CANCEL_OTHERS (cancel every
other live Producer), PAUSE_AWAIT_INPUT (halt, resumable). Recorded on
substrate.TerminationMatched. (The fifth kernel outcome, `let-finish` — drain in-flight then
finalise — is DEFERRED post-1.0: it has no runtime dispatch branch yet, so shipping the enum
value would be a silent no-op. See CONTRIBUTING.md's deferral list.)

## Termination recipes

### `threshold_count(kind: 'str', n: 'int') -> 'TerminationPolicy'`

Finalise once `n` events of `kind` have been appended.

### `finalise_on(kind: 'str') -> 'TerminationPolicy'`

Finalise when the event just appended is of `kind`.

For a terminal event a RESUMABLE run can see more than once. `threshold_count(kind, 1)` reads
the run's count of `kind`, which a resume restores from the whole log, so a record that
already holds one such event finalises the resumed run on its first new event. This policy
reads only the event that just landed: an earlier one in the record never ends the run (lens
audit F309: the console rebuilt the session's termination with a raised threshold, counted
by reading the whole record on every turn).

### `all_completed() -> 'TerminationPolicy'`

Finalise on quiescence once every started Producer has ended.

NOT for a RESUMABLE run: this compares started vs ended COUNTS, which are restored from the
whole log on resume — but a pause leaves the emitting Producer started-without-a-durable-end
across the pause, so on resume `completed >= started` can never be met and the run would
hang. A pausable topology MUST finalise on a process-local terminal instead (quiescence /
threshold); see `pause_await_input`. (The runtime fails such a run loudly, not silently.)

### `quiescence() -> 'TerminationPolicy'`

Finalise when the run goes quiescent: no Producer running, nothing queued.

This was `quiescence_with_watchdog(seconds)`. No watchdog ever existed: `seconds` only
capped the writer's 10 ms idle poll, so every value of 0.01 or more did nothing, and call
sites passing 2400 s or `watchdog_seconds + grade_timeout_seconds` expected a deadline
the kernel never set (lens audit F021). A deadline on one Producer is
`Budget(wall_seconds=Cap(...))`.

### `pause_await_input(when: 'Callable[[TermContext], bool]', resume_condition: 'str') -> 'TerminationPolicy'`

Pause and emit a typed resume_condition when `when` holds (kernel halt-with-resume).

RESUMABLE-TERMINAL CONSTRAINT: a topology that can PAUSE here and later resume MUST pair
this with a PROCESS-LOCAL finalisation terminal — quiescence (`quiescence`)
or a count threshold (`threshold_count`) — NOT `all_completed`. `all_completed` compares
started vs ended COUNTS, but a pause trips while the emitting Producer is still inflight, so
its ProducerStarted has no durable end across the pause: on resume the restored started >
ended and `completed >= started` can never be met, so the resumed run would never finalise.
The runtime guards this (a stuck-quiescent resumed run is recorded as a RunFinalised with
reason "stuck_quiescent" and FAILS loudly rather than hanging), but the fix is to choose a
process-local terminal. The reference R-2 pipeline does exactly this (quiescence, not
all_completed) and documents why.

### `cancel_all_others(when: 'Callable[[TermContext], bool]') -> 'TerminationPolicy'`

Cancel every OTHER running Producer (all but the subject — the producer of the
just-appended event) when `when(ctx)` holds (kernel §8; F-LIFE-2). CANCEL_OTHERS does NOT
finalise: the cancelled Producers emit substrate.ProducerCancelled on the log and the run
continues (typically to quiescence). The canonical R-1 use: fire on the adjudicator's
completion, cancel the still-running candidates, then a quiescence/all-completed policy
finalises. Compose: any_of(cancel_all_others(adjudicated), all_completed()).

### `any_of(*policies: 'TerminationPolicy') -> 'TerminationPolicy'`

Finalise/pause when any composed policy returns a non-CONTINUE decision.

### `all_of(*policies: 'TerminationPolicy') -> 'TerminationPolicy'`

Finalise only when all composed policies agree to finalise.

## Topology & execution

### `TopologyBuilder() -> 'None'`

Declares a topology — the Producers, Triggers, Routes, Views, and TerminationPolicy a run
is built from. A `topology(b)` function receives one of these and calls its methods; the
runtime builds + statically validates it (`build`) before the run opens. This is the primary
authoring surface.

- `baseline(self, **metadata: 'Any') -> 'None'` — Attach run metadata (fixtures, seeds, environment identifiers) recorded in the RunStarted manifest, so every record is interpretable from a known baseline.
- `build(self) -> 'Registration'` — Freeze and statically validate (design §5.5).
- `initial(self, kind: 'str', *, input: 'Any' = None) -> 'None'` — Declare an initial Producer started at run open (seq 0), with `input`.
- `instrument(self, name: 'str', *, on: 'str', schemas: 'Sequence[type]', input_builder: 'Callable[[TriggerContext], Any]', factory: 'Callable[[], Producer] | None' = None, start: 'Producer | None' = None, schema_version: 'int' = 1, deterministic: 'bool' = False, into: 'str | None' = None, via: 'Callable[[Any], Any] | None' = None) -> 'None'` — Wire a side-Producer INSTRUMENT in one call — the common observe-(and-stage) pattern.
- `producer_kind(self, kind: 'str', *, schemas: 'Sequence[type]', schema_version: 'int', factory: 'Callable[[], Producer] | None' = None, start: 'Producer | None' = None, deterministic: 'bool' = False, author_version: 'str | None' = None, budget: 'Budget | None' = None) -> 'None'` — Register a Producer kind: its name, the frozen msgspec Struct event schemas it may emit (+ schema_version), and the Producer to run.
- `route(self, id: 'str', *, subscription: 'Subscription', slot: 'str', transform: 'Callable[[Any], Any]') -> 'None'` — Register a Route: on an event matching `subscription`, stage `transform(event)` into the named `slot` so a later Trigger's input_builder can read it (carrying context — e.g. a failure reason — forward into the Producer it starts).
- `termination(self, policy: 'TerminationPolicy', *, scope: 'str' = 'run') -> 'None'` — Set the TerminationPolicy that decides when the run ends (see the termination recipes: quiescence, threshold_count, all_completed, pause_await_input, ...).
- `trigger(self, id: 'str', *, subscription: 'Subscription', predicate: 'Callable[[TriggerContext], bool]', starts: 'str', input_builder: 'Callable[[TriggerContext], Any]', policy: 'FiringPolicy | None' = None, cooldown: 'Cooldown | None' = None) -> 'None'` — Register a Trigger: when an event matching `subscription` is appended and `predicate` (over the Views) holds, start a `starts` Producer with the input from `input_builder`. `policy` (default PerEvent) controls how often it fires — Once, PerEvent, PerKey, WhileTrue; `cooldown` throttles it.
- `view(self, name: 'str', view: 'View') -> 'None'` — Register a named View — a deterministic incremental projection over the bus (e.g. KindBuffer, KindCount) that Predicates read.

### `register_topology(name: 'str', factory: 'Callable[[TopologyBuilder], None]') -> 'None'`

Register a topology factory under a name so the CLI can run it by `--topology <name>`.

### `get_topology(name: 'str') -> 'Callable[[TopologyBuilder], None]'`

Look up a topology factory registered with `register_topology`; raises KeyError if
unknown (naming the registered topologies).

### `Runtime(record_root: 'Path | str', *, persistent: 'bool' = False, fsync: 'FsyncPolicy' = Interval(milliseconds=100), admission: 'int' = 1024, budget_us: 'int' = 100, hysteresis_k: 'int' = 3, writer_stats: 'bool' = False, diagnostics: 'bool' = False) -> 'None'`

Executes one topology and produces one run record (single-use).

- `cancel_producer(self, instance: 'str', *, cause: 'str' = 'external', caller: 'str | None' = None) -> 'dict[str, Any] | None'` — Cancel one live Producer by instance id.
- `inject_event(self, event: 'Any') -> 'None'` — Inject an APPLICATION event onto a live run's inbox from OUTSIDE any Producer.
- `resume(self, topology: 'Callable[[TopologyBuilder], None]', *, resume_event: 'Any') -> 'RunResult'` — Resume a PAUSED persistent-bus run at its existing record (F-TERM-3 / F-PERS-2).
- `run(self, topology: 'Callable[[TopologyBuilder], None]', *, name: 'str | None' = None) -> 'RunResult'` — Run a topology to a fresh run record.

### `RunResult(run_id: str, record_root: str, status: substrate.constants.RunStatus, final_event: substrate.types.Event | None, elapsed_seconds: float, finalisation_payload: Any | None)`

What `Runtime.run()` / `.resume()` returns: the run's outcome and where its record lives.

`status` is "finalised" (reached a terminal), "paused" (halted on pause-await-input,
resumable), or "failed". `record_root` is the on-disk run record — the canonical account;
`final_event` is the last bus event (or None); `finalisation_payload` is the optional output
a TerminationPolicy attached at finalise. `run_id` survives across a resume.

### `RunStatus(*values)`

A run's outcome, as `run_graph` reads it from the record and as `Runtime.run()` returns it
(`RunResult.status`, which is never INCOMPLETE). INCOMPLETE is no terminal RunFinalised: the
record is still being written, or torn. UI sprint 107: bare strings before, compared in eight
places in the console and typed as a Literal in the runtime.

### `RunFailureReason(*values)`

The RunFinalised reasons that mean the run itself failed (RunStatus.FAILED), as opposed to
a clean finalise with Producer failures inside it (lens audit F033: three literals written in
the sequencer and runtime and re-listed in graph.py).

### `Budget(wall_seconds: substrate.kernel.topology.Cap | None = None, event_counts: dict[str, substrate.kernel.topology.Cap] | None = None)`

A producer_kind's declared resource caps. All caps optional; None means unbounded
on that axis. Additive kernel primitive (Sprint 164, amended Sprint 166 to use the
named `Cap` struct at the reviewer's F6 request; roadmap v2 S1); every existing
producer without a budget behaves identically.

`wall_seconds` — `Cap(limit=cap_seconds, reason=...)`. Max elapsed wall-clock from
`substrate.ProducerStarted` to any terminal for this producer instance. On overrun the
Producer is stopped and recorded as `substrate.ProducerFailed` with
`budget_exceeded: {axis: "wall_seconds", limit, reason}`.

`event_counts` — `{event_kind_name: Cap(limit=cap_count, reason=...)}`. Per-kind cap
on events of that name that this producer instance may emit; names are the event
Struct's class name. The emission that would pass the cap is not recorded; the Producer
stops with `substrate.ProducerFailed` carrying
`budget_exceeded: {axis: "event_counts", kind, limit, reason}`.

### `Cap(limit: int | float, reason: str)`

One named cap in a `Budget`. `limit` is the ceiling value the runtime enforces; `reason`
is the human-readable string the breach records: a `substrate.ProducerFailed` whose payload
carries `budget_exceeded: {axis, limit, reason}` (lens audit F023: these docs named a
`substrate.BudgetExceeded` kind that never existed).
Named fields keep the enforcement site legible: `budget.wall_seconds.reason` reads as
the reason for the wall-clock cap, not `budget.wall_seconds[1]` — a positional-tuple
access that hides which slot is which and can silently swap on refactor.

`limit` typed `int | float` covers both wall-clock caps (seconds, typically float) and
event-count caps (integer count of an event kind). msgspec preserves the input type
on the wire.

### `find_active_runtime(record_root: 'str | Path') -> "'Runtime | None'"`

Return the live Runtime for `record_root`, or `None` when no run is
active at that path in this process. Reads are lock-free (Python's GIL
covers the dict access); callers cross-thread should NOT cache the
reference — a run that has just finalised will be unregistered from
the map even if the caller still holds the object.

## Records & encoding

### `read_record(root: 'Path | str', *, resolve_blobs: 'bool' = False) -> 'Iterator[dict[str, Any]]'`

Every recoverable envelope in seq order, exactly as stored. With `resolve_blobs=True`,
a blob-stub payload is replaced by the payload it stands for (`resolve_blob_payload`):
readers that consume payload CONTENTS pass True; integrity readers (replay, conformance,
byte comparisons) keep the default and see the record as written.

### `read_first_envelope(root: 'Path | str') -> 'dict[str, Any] | None'`

The record's first envelope (seq 0, normally `substrate.RunStarted`), reading and CRC-checking
only its first line. None when the record has no complete first frame. For catalog-style
readers that need one fact per record across thousands of records; `read_record` loads and
verifies whole segments (UI sprint 097: list_records took 7.8 s over 4,394 sessions).

### `read_last_envelope(root: 'Path | str') -> 'dict[str, Any] | None'`

The record's last complete envelope, reading backwards from the end of its newest segment
and CRC-checking only that frame. A cut final frame (a writer died mid-append) is skipped, as
`read_record` skips it. None when no segment holds a complete frame, or when the last complete
frame fails its CRC; a caller that needs certainty then reads the whole record.

Seqs are dense and append-only, so this frame's seq is the record's highest. The one
disagreement with `read_record`: when the hot segment holds a corrupt frame BEFORE its last,
`read_record` stops at the corruption and this still returns the last frame. For per-request
tail cursors over long records (lens audit F310: the console read every session's whole record
twice per turn to find this one number).

### `has_torn_tail(root: 'Path | str') -> 'bool'`

True when the hot segment ends inside a frame: a writer died mid-append. Every frame ends in
a newline, so a non-empty hot segment whose last byte is not one holds a cut frame. Read-only
(unlike `recover_open_segment`, which truncates the tail); `read_record` skips that frame.

### `resolve_blob_payload(payload: 'Any', root: 'Path | str') -> 'Any'`

Redeem a blob Claim Check (technical §3.7). A payload over BLOB_THRESHOLD_BYTES is stored
in the record as `{"$blob": "sha256:<hex>", "bytes": n}`; this returns the payload it stands
for, read from the run's blob store with its hash verified. Any other payload is returned
unchanged.

The ONE place a stub is redeemed (Hohpe & Woolf, Claim Check + Content Enricher). Every
reader that consumes payload contents goes through it — live views get the inline payload
from the sequencer, resumed views, replayed views, followers and record tools get it here —
so the same event carries the same payload for every reader (Sprint 095). A missing or
corrupt blob raises: it is data loss, as a seq gap is.

### `recover_open_segment(root: 'Path | str') -> 'int'`

Writer-side recovery (run at restart/attach, §3.3): truncate the hot segment to
the last complete, crc-valid frame. Returns the number of frames kept. Sealed
segments are never touched.

### `Interval(milliseconds: int = 100)`

fsync at most every `milliseconds` (default 100); amortized throughput.

### `Always()`

fsync after every frame; zero complete frames lost, capped at device fsync rate.

### `NoFsync()`

OS page cache only; the disk never bottlenecks (loss = whatever the OS last flushed).

### `canonical_bytes(obj: 'Any') -> 'bytes'`

The canonical RFC-8785 bytes for a value (= B_hash for a crc-less object).
Deterministic: the same logical value yields identical bytes everywhere.

### `content_hash(obj: 'Any') -> 'str'`

The `sha256:<hex>` content hash over a value's canonical bytes — the identity
used for blob ids, input_sha256, message_sha256, and D-8 comparison (§3.3).

## Live attach (technical §13)

### `attach(root: 'Path | str', *, poll_ms: 'int' = 100, resolve_blobs: 'bool' = False) -> 'LiveRecord'`

Open a read-only follower over a run record that may still be growing (technical
§13, F-PERS-4). Read-only, lock-free, signal-free by construction. `resolve_blobs=True`
redeems blob Claim Checks for readers that consume payload contents (Sprint 095).

### `LiveRecord(root: 'Path | str', *, poll_ms: 'int' = 100, resolve_blobs: 'bool' = False) -> 'None'`

A read-only follower over a (possibly still-growing) run record (technical §13).

Hold one per reader. `read_new()` returns every complete, CRC-valid frame appended
since the last call (sealed segments first, then the recoverable prefix of the hot
segment); the trailing partial line is ignored until it completes. `follow()` is a
blocking generator that polls for growth. The follower opens files read-only, takes
no lock, and never writes — F-PERS-4 by construction.

- `follow(self, *, until_finalised: 'bool' = True) -> 'Iterator[dict[str, Any]]'` — Blocking generator: yield frames as they appear, polling for growth.
- `read_new(self) -> 'list[dict[str, Any]]'` — Every complete frame appended since the last call, in seq order: all sealed segments (newly-appearing ones are picked up), then the recoverable prefix of the hot segment.

## Off-bus sidecars (technical §3.8 / §6.4)

### `read_sidecar(path: 'Path | str') -> 'list[dict[str, Any]]'`

Read an off-bus sidecar JSONL file into a list of records (read-only). Used by
`substrate stats` and dashboards; returns [] if the file does not exist.

## Composition (technical §20)

### `embedded_substrate(topology: 'Callable[[TopologyBuilder], None]', *, exports: 'dict[str, type | ExportRule] | None' = None, default_export: 'type | ExportRule | None' = None, inner_poll_ms: 'int' = 5) -> 'Callable[[Any], AsyncIterator[Any]]'`

Build a Producer (the `start` callable) that runs `topology` as an INNER substrate and
exports the mapped inner kinds onto the outer bus (technical §20).

`exports` maps an inner event kind to either an outer Struct TYPE (default transform =
splat the inner payload) or an `(outer_type, transform)` pair. Inner `substrate.*` kinds
NEVER cross unless explicitly mapped; unmapped application kinds never cross.

DEFAULT EXPORT (F-COMP-1 / §20: "default export = inner RunFinalised only"): the inner
`substrate.RunFinalised` is exported by default. Because an OUTER Producer kind may not
emit a `substrate.*` kind (reserved namespace, F-OBS-5), the default export needs an
author-named OUTER carrier Struct — pass it as `default_export` (a type, or an
(outer_type, transform) pair; the transform receives the inner RunFinalised payload,
which carries the inner root / finalisation_payload). When `default_export` is given and
`exports` does not already map RunFinalised, a RunFinalised→default_export rule is
installed. If NEITHER is given, the inner RunFinalised does not cross as a frame — the
inner root is still recorded in the outer TriggerFired resolved input (the §20 provenance
link) and the inner record is complete at its own root. (The "default export = RunFinalised"
wording assumes an outer carrier; that the carrier must be author-named is a tech-spec §20
flow-back — see BLACKBOARD.)

The returned callable is the Producer `start`: the outer runtime calls it with the sealed
resolved input (which carries the inner record root under input["inner_root"]) and
consumes the translated outer events under outer admission.

CONTRACT — every embedded-substrate topology MUST thread `inner_root` in the embedded
Producer's resolved input (e.g. `b.initial("embedded", input={"inner_root": str(path)})`,
or a trigger input_builder that supplies it). This is a deliberately STRICTER contract
than an optional fallback: it is the correct trade for run-granularity provenance — the
inner root is then unconditionally recorded in the outer TriggerFired.resolved_input, so
the inner run is always citable from the outer record (§20). Omitting it raises
InnerRootRequired, which surfaces as a recorded outer substrate.ProducerFailed (not a
fabricated, un-citable fallback root).

### `EmbeddedRunFailed(message: 'str', *, inner_run_id: 'str', inner_root: 'str') -> 'None'`

An embedded substrate's inner run did not finalise normally. Raised by the embedded
Producer so the OUTER runtime records ONE substrate.ProducerFailed carrying the inner
run_id (technical §20). The inner record stays complete at its own root.

## Lifecycle kinds and vocabulary (technical §3.4)

### `RUN_STARTED`

str(object='') -> str
str(bytes_or_buffer[, encoding[, errors]]) -> str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to 'utf-8'.
errors defaults to 'strict'.

### `RUN_FINALISED`

str(object='') -> str
str(bytes_or_buffer[, encoding[, errors]]) -> str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to 'utf-8'.
errors defaults to 'strict'.

### `TRIGGER_FIRED`

str(object='') -> str
str(bytes_or_buffer[, encoding[, errors]]) -> str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to 'utf-8'.
errors defaults to 'strict'.

### `PRODUCER_STARTED`

str(object='') -> str
str(bytes_or_buffer[, encoding[, errors]]) -> str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to 'utf-8'.
errors defaults to 'strict'.

### `PRODUCER_COMPLETED`

str(object='') -> str
str(bytes_or_buffer[, encoding[, errors]]) -> str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to 'utf-8'.
errors defaults to 'strict'.

### `PRODUCER_FAILED`

str(object='') -> str
str(bytes_or_buffer[, encoding[, errors]]) -> str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to 'utf-8'.
errors defaults to 'strict'.

### `PRODUCER_CANCELLED`

str(object='') -> str
str(bytes_or_buffer[, encoding[, errors]]) -> str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to 'utf-8'.
errors defaults to 'strict'.

### `PRODUCER_EMITTED_INVALID`

str(object='') -> str
str(bytes_or_buffer[, encoding[, errors]]) -> str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to 'utf-8'.
errors defaults to 'strict'.

### `TERMINATION_MATCHED`

str(object='') -> str
str(bytes_or_buffer[, encoding[, errors]]) -> str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to 'utf-8'.
errors defaults to 'strict'.

### `INPUT_BUILD_FAILED`

str(object='') -> str
str(bytes_or_buffer[, encoding[, errors]]) -> str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to 'utf-8'.
errors defaults to 'strict'.

### `INJECTION_APPLIED`

str(object='') -> str
str(bytes_or_buffer[, encoding[, errors]]) -> str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to 'utf-8'.
errors defaults to 'strict'.

### `PREDICATE_QUARANTINED`

str(object='') -> str
str(bytes_or_buffer[, encoding[, errors]]) -> str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to 'utf-8'.
errors defaults to 'strict'.

### `LIFECYCLE_KINDS`

Built-in immutable sequence.

If no argument is given, the constructor returns an empty tuple.
If iterable is specified the tuple is initialized from iterable's items.

If the argument is a tuple, the return value is the same object.

### `FAILURE_KINDS`

Build an immutable unordered collection of unique elements.

### `INITIAL_TRIGGER_ID`

str(object='') -> str
str(bytes_or_buffer[, encoding[, errors]]) -> str

Create a new string object from the given object. If encoding or
errors is specified, then the object must expose a data buffer
that will be decoded using the given encoding and error handler.
Otherwise, returns the result of object.__str__() (if defined)
or repr(object).
encoding defaults to 'utf-8'.
errors defaults to 'strict'.

## Bundles and the state root

### `list_bundles(bundles_root: 'Path | None' = None) -> 'list[Bundle]'`

Enumerate every shipped and user bundle. Returns Bundles sorted by name.

Sources, in name-shadowing order (later wins if a name collides):
  1. Shipped defaults under `topologies/session/bundle/` (name "session")
     and `topologies/applications/<app>.bundle/` (name "<app>").
  2. User bundles under `_bundles_root(bundles_root)` — every direct
     subdirectory that contains a `bundle.toml` file is loaded via
     `load_bundle(name)`; per `load_bundle`, a user bundle of the same
     name shadows the shipped default.

A missing bundles root yields the shipped list only. A subdirectory
without a `bundle.toml` is skipped silently (matches `load_bundle`'s
"no manifest → BundleNotFoundError" contract only when the caller
asks for that specific name; enumeration does not raise).

Sprint 238: added as the substrate-side prerequisite for substrate-ui
sprint 034a's `GET /api/bundles` endpoint. The daemon calls this and
surfaces `[{name, description, slot_count}]` to the UI's bundle picker.

### `load_bundle(name: 'str', *, bundles_root: 'Path | None' = None) -> 'Bundle'`

Load one bundle from `<bundles_root>/<name>/`. Reads
`bundle.toml` plus the three prose slots plus the corpus/retrieval/
tools blocks. Raises `BundleNotFoundError` if the directory is
absent; `BundleShapeError` on a duplicate slot; propagates
`tomllib.TOMLDecodeError` on a malformed `bundle.toml`.

### `BundleError`

Base class for bundle loading failures. Carries the bundle name
and the failing path for the operator to debug.

### `BundleNotFoundError`

No `<bundles_root>/<name>/` directory exists on disk.

### `substrate_home() -> 'Path'`

The root of substrate's per-user state tree.

Returns ``Path(os.environ["SUBSTRATE_HOME"])`` when set,
else ``Path.home() / ".substrate"``.

## Replay (technical §12)

### `replay(record: 'Any', level: 'ReplayLevel' = '1') -> 'ReplayResult'`

Replay a record at the given honesty tier (technical §12).

Level 1: stream + counts. Level 2: + verify every TriggerFired input hash (D-5).
Level 3a: + the native-re-execution PRECONDITION gate (all kinds deterministic AND
replay_ceiling=="3a"); this returns the gate result (preconditions_ok / refusal_reason)
rather than re-running — re-execution is the Runtime's job. Level 3b: DEFERRED, raises
NotImplementedError (needs a t-replay decision; not faked).

SIZE NOTE: this MATERIALIZES the whole record into memory (unlike `read_record`, which
streams). Fine for normal records (a few-thousand-frame record replays in tens of ms); for a
very large (multi-GB) record, stream over `read_record` / `LiveRecord.follow` instead, or
treat the record size as bounded for the analysis tools.

### `assert_replayable(record: 'Any', level: 'ReplayLevel') -> 'ReplayResult'`

Run the replay and raise if it is not honestly supported at `level`: a Level-2
hash mismatch or a failed Level-3(a) precondition raises ReplayError (honest refusal,
F-RPLY-1). Returns the ReplayResult on success.

### `ReplayResult(level: str, frame_count: int, counts: dict[str, int], complete: bool, decisions_verified: int = 0, mismatches: tuple[substrate.projections.replay.HashMismatch, ...] = (), preconditions_ok: bool | None = None, refusal_reason: str | None = None)`

The typed outcome of a replay (technical §12). `level` is the tier actually run.
`counts` is the per-kind frame count (Level 1+). `decisions_verified` is the number of
TriggerFired input hashes checked (Level 2). `mismatches` is empty on success.
`preconditions_ok` / `refusal_reason` carry the Level-3(a) gate result.

### `HashMismatch(seq: int, trigger_id: str | None, recorded: str, recomputed: str)`

A Level-2 verification failure: a TriggerFired's recorded input hash does not match
the recomputed canonical hash of its recorded resolved input (D-5 broken).

## Inspection / provenance / divergence (technical §14)

### `explain_producer(record: 'Any', producer: 'str') -> 'Explanation'`

The typed cause of `producer`'s existence: the TriggerFired that scheduled it
(or the run open, for an initial Producer), with its resolved-input hash. O(record)
once. Raises ProducerNotFound if the instance has no firing on the record.

### `trace_ancestry(record: 'Any', producer: 'str') -> 'tuple[Explanation, ...]'`

The spawn chain from `producer` up to the root, root-LAST: index 0 is `producer`
itself, each subsequent entry its parent, ending at the initial Producer (cause
RunStarted). Acyclic by construction; a missing link raises ProducerNotFound. The
chain is the provenance-closure witness (conformance check 11).

### `view_at(record: 'Any', seq: 'int', view: 'View') -> 'Any'`

Reconstruct a View's state as observed at sequence `seq` (Level-1 replay truncated
at seq): fold every matching event with seq <= `seq` into the provided View instance
and return its value() (technical §14, conformance check 12 — view-at fidelity).

Takes a View INSTANCE, not a name: a record stores event payloads, not View code, so
the caller supplies the View whose update()/subscription define the fold. (Spec §16
signature is `view_at(record, seq, view: str)` assuming the topology's View code is
available by name; the instance form is the honest dependency — flagged as a spec
flow-back in BLACKBOARD.) The View should be fresh; folding is not idempotent.

Blob Claim Checks are redeemed before folding (Sprint 095), so view_at at a seq equals the
live View value at that seq. An already-loaded envelope iterable is folded as given.

### `decisions_between(record: 'Any', a: 'int', b: 'int') -> 'tuple[Any, ...]'`

Every runtime decision (substrate.* frame) with a <= seq <= b, in seq order, as
reconstructed Event objects (technical §14). The kernel's decision record over a
sequence window — Level-2 reads, no re-execution.

### `first_divergence(rec_a: 'Any', rec_b: 'Any') -> 'Divergence | None'`

The first index where two records' D-8 comparison sequences differ, or None if
they are equivalent (technical §14, conformance check 13). The comparison sequence is
(kind, canonical payload hash) per frame in seq order; supplementary metadata (t,
host, config) is excluded by construction (it is never hashed here).

### `Explanation(kind: str, instance: str, parent: str | None, cause: str, trigger_id: str | None, firing_key: str | None, input_sha256: str | None, at_seq: int)`

The typed cause of one Producer's existence (technical §14: explain_producer).

`cause` is one of "TriggerFired" | "RunStarted" (an initial Producer's firing
attributes to the run open). `at_seq` is the seq of the firing frame. `input_sha256`
is the resolved-input content hash recorded at the firing — the citable identity of
what the Producer ran with.

### `Divergence(index: int, seq: int, kind_a: str | None, kind_b: str | None, hash_a: str | None, hash_b: str | None)`

The first point two records of the same topology diverge (technical §14 / D-8).

`index` is the position in the seq-ordered comparison sequence; `seq` is the bus
seq of the diverging frame in record A (or the shorter record's end). `kind_a` /
`kind_b` and `hash_a` / `hash_b` are the (kind, canonical payload hash) pair that
differs. When one record is a strict prefix of the other, the longer record's extra
frame is the divergence and the shorter side's fields are None.

## Narration — the legible prose projection (Wave 14)

### `narrate(record: 'Any', *, lifecycle: 'bool' = False) -> 'Iterator[NarrationLine]'`

Narrate a run record beat by beat. By default suppresses the lifecycle bracketing
(ProducerStarted / ProducerCompleted / InjectionApplied); `lifecycle=True` includes it.
Yields a NarrationLine per narrated event, in seq order (the log's total order).

### `narration_summary(record: 'Any') -> 'NarrationSummary'`

A one-glance digest of a run record: did it finalise, how many producers ran, how many
failed, and what application events it produced. A finalised run with a nonzero failure
tally is a finalised-but-broken run — the count makes that legible.

### `NarrationLine(seq: int, kind: str, text: str)`

One narrated beat. `seq` cites the event, `kind` is its raw event kind (so a consumer
can filter or style by kind), `text` is the rendered prose.

### `NarrationSummary(finalised: bool, final_reason: str | None, total_events: int, producers_started: int, producers_completed: int, producers_cancelled: int, producers_failed: int, input_build_failures: int, predicate_quarantines: int, invalid_emissions: int, application_events: dict[str, int])`

A one-glance digest of a run record. `finalised` is whether the run reached a terminal
substrate.RunFinalised; `final_reason` is its reason (None for an ordinary finalise, e.g.
"view_failure" for a failed one). The failure counts are the authoring-failure tally a
finalised-but-broken run hides behind a clean status line. `application_events` maps each
non-substrate.* kind to its count — the work the topology actually produced.

## Graph projections — structure + run-as-graph (Wave 12 prep)

### `topology_graph(record: 'Any') -> 'TopologyGraph'`

The STATIC topology structure, from the RunStarted manifest (the only place a run records
its topology). Producer kinds are nodes (with what they emit and whether any Trigger starts
them — `is_initial`); Triggers and Routes are the edges. Raises ValueError if the record has no
RunStarted manifest (an empty or truncated record has no topology to project).

### `run_graph(record: 'Any') -> 'RunGraph'`

The DYNAMIC run-as-graph: every Producer instance with its spawn link, lifecycle span,
status, and emitted events — the concurrent, causal shape of how the run grew. Built from the
TriggerFired / ProducerStarted-Completed-Failed-Cancelled lifecycle events (the same instance/
parent links the inspect provenance surface uses). Instances are returned in spawn order
(by started_seq).

### `TopologyGraph(producers: tuple[substrate.projections.graph.ProducerNode, ...], triggers: tuple[substrate.projections.graph.TriggerEdge, ...], routes: tuple[substrate.projections.graph.RouteEdge, ...], views: tuple[str, ...], termination: tuple[str, ...])`

The static structure of a run's topology, read from its RunStarted manifest: Producer-kind
nodes, Trigger spawn-edges, Route staging-edges, the View names, and the TerminationPolicy
descriptor(s).

### `ProducerNode(kind: str, emits: tuple[str, ...], deterministic: bool, is_initial: bool)`

A Producer KIND in the topology. `emits` are the event kinds it may emit (its declared
schemas); `is_initial` is True when the run starts this kind at open (an entry point).

`is_initial` is NOT "no Trigger starts it": in a cyclic topology (e.g. a round-robin where
`after-N` wraps to start speaker-1), an entry Producer is also a Trigger's target, so the
only reliable signal is whether it actually fired at run open — recorded as a TriggerFired
with trigger_id `__initial__`. The manifest does not record initials; this is read from
those firings.

### `TriggerEdge(id: str, policy: str, on: tuple[str, ...], starts: str)`

A Trigger: when an event matching `on` (its subscription) lands and its predicate holds,
start the `starts` Producer. `policy` is the firing policy (Once / PerEvent / PerKey /
WhileTrue). The predicate itself is code, not recorded — only its effect (a firing) is.

### `RouteEdge(id: str, slot: str)`

A Route: stages data forward into `slot` for a later Trigger's input. The manifest records
the route's id and target slot (the citable identity); the source subscription and transform
are code, surfaced at runtime as the InjectionApplied events in the run-as-graph.

### `RunGraph(instances: tuple[substrate.projections.graph.ProducerInstance, ...], status: substrate.constants.RunStatus, final_reason: str | None, paused_on: str | None)`

The dynamic run-as-graph: every Producer instance (the spawn forest, in spawn-seq order)
with its span and emitted events, plus the run-level outcome the handoff's outcome surface
needs. `status` is "incomplete" | "paused" | "finalised" | "failed" (the last three match
RunResult.status). **"failed"** is a RUN-level failure with a terminal RunFinalised (the run
died: view_failure / kernel_error / stuck_quiescent) — distinct from a clean "finalised" run
that had Producer-level failures inside it (that finished-!=-worked case is the per-instance
statuses, not the run status). **"incomplete"** is no terminal RunFinalised: either still
being written (if live-followed) OR torn/medium-failed (the fsync-gate path fails WITHOUT a
terminal — absence-of-terminal encodes medium failure); a static "incomplete" read is NOT a
clean "running", so a torn record never reads as fine (§7.2). "paused" awaits external input.
`final_reason` is the RunFinalised reason (None for an ordinary finalise; the failure reason
for a "failed" run). `paused_on` is the resume_condition when status is PAUSED.

### `ProducerInstance(kind: str, instance: str, parent: str | None, trigger_id: str | None, firing_key: str | None, input_sha256: str | None, fired_seq: int | None, started_seq: int | None, ended_seq: int | None, status: substrate.projections.graph.ProducerStatus, emitted: tuple[str, ...])`

One Producer INSTANCE in a run: its kind, its spawn link (`parent` instance + the
`trigger_id` that started it — `__initial__` for an initial Producer), its lifecycle SPAN
(`fired_seq` when its Trigger SCHEDULED it; `started_seq` .. `ended_seq` when it actually ran,
`ended_seq` None while still running) and end `status` (completed / failed / cancelled /
running / interrupted), the resolved-input hash it ran on, and the application event kinds it
`emitted` (in seq order). **"interrupted"** = started, no end-record, AND the run is over
(terminal or paused) — it will never complete (e.g. a Producer cut off by a pause); "running"
is reserved for an un-ended instance in a still-INCOMPLETE run (genuinely live).

RENDERING CONCURRENCY — read this before drawing a run-as-graph. The seq-span faithfully
encodes bus-timeline concurrency (a Producer is running at seq N iff started_seq <= N <
ended_seq), BUT in fast or deterministic runs the single writer serializes near-instant
Producers, so the spans can look SEQUENTIAL even for genuinely concurrent Producers (in the
CI demo fixtures, the fast reviewers have disjoint spans). Derive "ran concurrently" from the
SPAWN STRUCTURE — Producers spawned by one firing / at adjacent seqs (e.g. all sharing a
trigger_id and spawning at adjacent `fired_seq`) are concurrent siblings — NOT from
span-overlap alone, or a fast run will flatten the parallelism the UI must show. Anchor each
lifespan at `fired_seq` (when it was scheduled), the t-free firing anchor the design uses.

### `ProducerStatus(*values)`

A Producer instance's status in `run_graph` (lens audit F034: a five-value string set).

## Test helpers (technical §15)

### `assert_event(rec: 'Any', kind: 'str', **partial: 'Any') -> 'dict[str, Any]'`

Assert at least one event of `kind` with the given partial payload exists;
return the first match. Raises AssertionError citing what was searched.

### `assert_no_event(rec: 'Any', kind: 'str', **partial: 'Any') -> 'None'`

Assert NO event of `kind` with the given partial payload exists; raises AssertionError
citing the offending seq if one does.

### `assert_sequence(rec: 'Any', kinds: 'Sequence[str]') -> 'list[dict[str, Any]]'`

Assert the record's event-kind sequence equals `kinds` exactly.

## Exceptions (design §6.3)

### `SubstrateError`

Base for all substrate-raised exceptions.

### `BusLockedError(message: 'str', advisory: 'dict[str, object] | None' = None) -> 'None'`

A persistent-bus root is already locked by another runtime (technical §11).
Carries the advisory lock contents (pid, hostname, start time).

### `RegistrationError`

A topology is malformed (design §6.1). Raised at build time, before any run.

### `UnsupportedPlatformError`

A correctness primitive is unavailable on this platform — e.g. persistent
buses on Windows (technical §11; N-PORT-1). Raised at configuration time.

### `FsyncError`

fsync failed; the medium is untrustworthy. The writer must NOT write
RunFinalised on it — close, crash, let recovery report the truncated tail
(technical §5.2, the fsyncgate lesson).

### `ProducerNotFound`

A provenance/inspection query named a Producer instance not in the record.

### `SequenceOutOfRange`

A view_at / inspection query named a sequence number outside the record.

### `InputTypeError`

A resolved Producer input contains a non-immutable / non-whitelisted type;
immutability is enforced by construction (technical §8.3 / F-PROD-3).

### `ReplayError`

A replay precondition failed or the requested level is unsupported for this
record (technical §12). Carries a typed reason; the run record path is the evidence.

### `RecordIncompleteError`

A record has no terminal substrate.RunFinalised (e.g. torn at seq N, §5.2).

### `RecordGapError`

The read path found a hole in the seq sequence — a sealed segment lost (deleted, truncated
mid-frame, or corrupted) so the yielded stream is non-contiguous. Per technical §3.5/§3.6 a gap
proves data loss and the reader MUST report it rather than silently fold it away.

