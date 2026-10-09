# First topology: zero to a working two-Producer run

A counter Producer emits three numbers. A Trigger fires a doubler Producer for each. That is the whole tutorial. New to the eight words? The [README glossary](../README.md#the-pieces) names them.

Everything uses `substrate.api` only. Shape from design-spec §3.

## 0. Install

From the `substrate/` directory:

```
uv venv --python 3.12
uv pip install -e ".[dev]"
```

Save each snippet below to `first.py` and run `python first.py`.

## 1. A single Producer

A Producer is a callable. It takes typed input and yields typed Events — msgspec `Struct`s. The smallest topology is one Producer:

```python
import asyncio
from msgspec import Struct
from substrate.api import Runtime, TopologyBuilder, threshold_count


class CountReached(Struct, frozen=True):
    n: int


async def counter(_input):
    for n in range(1, 4):
        yield CountReached(n=n)


def topology(b: TopologyBuilder) -> None:
    b.producer_kind("counter", schemas=[CountReached], schema_version=1, factory=lambda: counter)
    b.initial("counter", input=None)                 # start one counter at run open
    b.termination(threshold_count("substrate.ProducerCompleted", 1))  # end after it completes


async def main():
    result = await Runtime("./runs/first").run(topology)
    print(result.status, result.record_root)


asyncio.run(main())
```

It prints `finalised ./runs/first`. That directory is a **run record** — the log on disk.

What you declared:

- `producer_kind` registers a Producer KIND. It takes a name, the event `schemas` it may emit, a `schema_version`, and a `factory` that returns the `start` callable.
- Every event schema is `frozen=True`. That is how the runtime keeps Producer inputs immutable by construction (F-PROD-3).
- `b.initial(kind, input=...)` schedules one Producer of that kind at run open.
- A `TerminationPolicy` decides when the run ends. `threshold_count(kind, n)` finalises after `n` events of `kind`; here, after the counter's one `substrate.ProducerCompleted`.

## 2. Add a Trigger and a second Producer

A Trigger creates new Producers when a Predicate over the bus holds. Fire a `doubler` on each `CountReached`:

```python
from substrate.api import PerEvent, Subscription, quiescence


class Doubled(Struct, frozen=True):
    original: int
    doubled: int


async def doubler(inp):
    yield Doubled(original=inp["n"], doubled=inp["n"] * 2)


def topology(b: TopologyBuilder) -> None:
    b.producer_kind("counter", schemas=[CountReached], schema_version=1, factory=lambda: counter)
    b.producer_kind("doubler", schemas=[Doubled], schema_version=1, factory=lambda: doubler)
    b.initial("counter", input=None)
    b.trigger(
        "double-each",
        subscription=Subscription(kinds=frozenset({"CountReached"})),   # what it watches
        predicate=lambda ctx: True,                                     # fire on every match
        starts="doubler",                                               # the kind it creates
        input_builder=lambda ctx: {"n": ctx.event.payload["n"]},        # the input
        policy=PerEvent(),                                              # once per matching event
    )
    b.termination(quiescence())                  # end when work settles
```

A Trigger takes five pieces: a `subscription` (which event kinds or producers it watches), a `predicate` (a cheap boolean over the context), an `input_builder` (builds the new Producer's input), the `starts` kind, and a firing `policy` — `PerEvent`, `Once`, `PerKey`, or `WhileTrue`. This run emits three `CountReached`, three `Doubled`, goes quiescent, and finalises.

Both callbacks take one argument, a `TriggerContext`, called `ctx` by convention:

- `ctx.event` — the event that matched the subscription.
- `ctx.views` — the named Views. Read `ctx.views["name"].value()`.
- `ctx.staged` — the Route slots staged for this firing. See §2.6.

> **`finalised` is not "it worked."** A run finalises whenever it reaches a terminal, even if a Producer raised, an `input_builder` raised, or a predicate quarantined. Failures are on the record as `substrate.ProducerFailed`, `InputBuildFailed`, or `PredicateQuarantined`, and the CLI prints `WARNING: N ProducerFailed` on `run`. `result.status` is still `finalised`. Inspect the record, or assert with `assert_event` / `assert_no_event`. `substrate run --strict` turns any such failure into a nonzero exit.

## 2.5 Gate on accumulated state (Views + Predicates)

A predicate that returns `True` fires on every event. Views gate on accumulated state — "fire once three are in":

```python
from substrate.api import KindCount


def topology(b: TopologyBuilder) -> None:
    b.producer_kind("counter", schemas=[CountReached], schema_version=1, factory=lambda: counter)
    b.producer_kind("doubler", schemas=[Doubled], schema_version=1, factory=lambda: doubler)
    b.initial("counter", input=None)
    b.view("seen", KindCount("CountReached"))                       # a deterministic projection
    b.trigger(
        "when-three",
        subscription=Subscription(kinds=frozenset({"CountReached"})),
        predicate=lambda ctx: ctx.views["seen"].value() >= 3,       # gate on the View
        starts="doubler",
        input_builder=lambda ctx: {"n": ctx.views["seen"].value()},
        policy=PerEvent(),
    )
    b.termination(quiescence())
```

A View is a deterministic incremental projection over the bus. The shipped ones are `KindCount`, `KindBuffer`, and `PerKindLatest`. The predicate reads `ctx.views[name].value()`. Forget the `.value()` and you read the View object itself — the predicate quarantines and the `WARNING` above surfaces.

## 2.6 Carry context forward (Route + `staged`)

A Route stages data from an event into a named slot. A later Trigger's `input_builder` reads it as `ctx.staged`. That is how context flows into a Producer's next instantiation. A Route's own `transform` takes the event directly, since it runs per event before any Trigger:

```python
b.route(
    "carry",
    subscription=Subscription(kinds=frozenset({"Doubled"})),
    slot="last_doubled",
    transform=lambda event: event.payload["doubled"],
)
# ... a later input_builder reads it:  ctx.staged.get("last_doubled")
```

The staging lands as `substrate.InjectionApplied` on the record. Context that reached a Producer is on the log. The bundled `pair_coding` topology is the worked example — a navigator's suggestion Routed into the driver's next chunk.

## 3. Read the record

The record is the product. Read it with the CLI or the API.

```
$ uv run substrate tail ./runs/first
seq=0   substrate.RunStarted        (topology=..., baseline=...)
seq=1   substrate.TriggerFired      trigger=__initial__  factory=counter
seq=2   substrate.ProducerStarted   producer=counter[01J...]
seq=3   CountReached                producer=counter[01J...]  n=1
...
seq=N   substrate.RunFinalised
```

`tail` accepts `--kind CountReached`, `--producer counter`, `--since 100`. Filters compose with AND. `--format jsonl` prints the raw on-disk bytes; pipe into `jq`.

`tail` is every frame. `narrate` is the plot:

```
$ uv run substrate narrate ./runs/first
seq     0  Run started (run_id=01J...).
seq     1  Initial trigger starts counter.
seq     3  counter -> CountReached (n=1)
seq     4  Trigger double-each fired -> starts doubler.
seq    14  doubler -> Doubled (original=2, doubled=4)
seq    20  Run finalised.
```

Application events show as work; substrate lifecycle events (`ProducerStarted`, `ProducerCompleted`) hide by default. `--lifecycle` restores them. `--summary` answers *did it work?*:

```
$ uv run substrate narrate ./runs/first --summary
Run finalised: 21 events.
  producers: 4 started, 4 completed, 0 cancelled, 0 failed
  work: CountReached=3, Doubled=3
```

Every authoring failure surfaces. A run that finalises with failures gets a `Run finalised WITH 2 FAILURES: ...` header on line one. Broken runs look broken.

Ask *why* a Producer existed:

```
$ uv run substrate inspect ./runs/first --producer "doubler[01J...]" --why
producer=doubler[01J...]
parent=counter[01J...]
caused_by:
  seq=12  TriggerFired   trigger=double-each   resolved_input={"n": 2}   input_sha256=sha256:...
```

From code:

```python
from substrate.api import read_record, explain_producer, narrate, view_at, KindCount

events = list(read_record("./runs/first"))                 # every envelope, in seq order
story = list(narrate("./runs/first"))                      # NarrationLine(seq, kind, text) per beat
exp = explain_producer("./runs/first", "doubler[01J...]")  # typed cause, cites the firing seq
count_at = view_at("./runs/first", 5, KindCount("CountReached"))  # a View's state as of seq 5
```

## 4. Replay and diff

```
$ uv run substrate replay ./runs/first --level 2
[OK] Level 2 replay successful.
Frames replayed: 21
Decisions verified: 4 (all inputs verified by hash)
```

Levels 1, 2, and 3(a) ship in v1.0, along with **D-8 log-equivalence** for diffing two records (`substrate inspect <a> --diff <b>`, or `first_divergence(a, b)`). D-8 compares runs modulo supplementary metadata: wall-clock `t`, run ids, per-run instance ids. **Level 3(b)** — byte-identical re-execution — is post-1.0 (see the README and product amendment A1.1). `--level 3b` reports the deferral rather than faking it.

## Next

- The eight primitives in depth: `docs/specs/kernel_spec/v15.md`.
- Worked reference topologies (ensemble + adjudicator, error cascade, composed code-synth) with real local-LLM runs: `docs/walkthroughs/README.md`.
- The full public API: `docs/api.md`.
- Evolving event schemas without breaking old records: `docs/schema-evolution.md`.
- A custom LLM backend: implement `Responder` (`from substrate.reference import Responder`).
