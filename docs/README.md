# Documentation

A reading order, not an alphabetical pile. If you're new, follow the **Learn** path top to bottom; reach for **Reference** when you need a specific answer; open **In depth** only when you want the contract behind a behaviour.

## Learn (in this order)

| Doc | For you if you want to… |
|---|---|
| [`tutorial.md`](tutorial.md) | **Start here.** Go from install to a running two-Producer topology, step by step. |
| [`demo.md`](demo.md) | See what the runtime does on real runs — the record *is* the run, read back. |
| [`adding-a-topology.md`](adding-a-topology.md) | Write your own topology against the public `substrate.api`, dual-mode (CI + walkthrough). |

## Reference (look it up)

| Doc | Answers |
|---|---|
| [`api.md`](api.md) | The public surface — every name in `substrate.api`. |
| [`replay.md`](replay.md) | What "replay" actually verifies at each tier (read this before relying on it). |
| [`schema-evolution.md`](schema-evolution.md) | How to evolve an event schema without breaking old records. |

## In depth

| Path | Contents |
|---|---|
| [`specs/`](specs/) | The binding specs — the eight primitives, the requirements, the conformance suite, and the amendments. The source of truth when prose and code disagree. |
| [`proof/`](proof/) | The correctness arguments behind the kernel invariants. |

## Background (the *why*, skip to *use*)

`application-catalogue.md` and `walkthroughs/` are development-record / planning material — read them for the reasoning, not to learn the system.
