# RESEARCH: what an error names

*2026-10-12. Asked by the Architect after a resumed session failed every turn with `model_error: FileNotFoundError(2, 'No such file or directory')`, a message that names no file: "the error must be better … take a look through all our errors like that … it should name the stuff that's wrong … appeal to a higher theory about what should be named."*

## The standard

Three sources agree, and the first is the project's own.

- **Substrate's design spec, §6** (`docs/specs/design_spec/draft1.md`). A registration error gives *where* (a path such as `producer_kind "writer".schemas[0].field "metadata"`), a one-line summary, what is wrong, the upstream constraint, and the fix when it is obvious (§6.1). A runtime error lands on the record as an event with typed fields, and its detail names the place, the value and the rule broken: `row at $.row.price: expected float, got str` (§6.2). The kernel's working agreement repeats §6.1 for registration errors.
- **Google's technical-writing course, "Writing helpful error messages"** (developers.google.com/tech-writing/error-messages, course summary). "Identify the cause of the error. If the user entered an invalid value, specify the invalid value. Specify requirements and constraints … Explain how to fix the problem." And: "don't be so concise that the resulting error message becomes cryptic."
- **Nielsen Norman Group, "Error-Message Guidelines"** (nngroup.com, 2023-05-14). "Concisely and precisely describe the issue"; "Offer constructive advice"; keep error codes for diagnosis, in human-readable language.

So an error message names, in order of how much the reader needs it:

1. **What failed**: the operation and its actor (the producer, the tool, the driver and its model).
2. **The offending value**: the path, the input, the command, the field.
3. **The rule it broke**: what was expected (must exist, must be absolute, expected float).
4. **The way out**, when the code knows it.

The first two are required; a message without the value is the "cryptic" case Google names. Substrate's record has two readers, the user and the model (a `ModelError` row and a tool result reach the model's next prompt), and both act on the value.

## How Python loses the value

`repr()` of an `OSError` keeps only `errno` and `strerror`: `FileNotFoundError(2, 'No such file or directory')`. `str()` keeps the path the call was given: `[Errno 2] No such file or directory: '~/.substrate/sandbox'` (checked on Python 3.14, 2026-10-12; the `filename` attribute holds the path, per the `OSError` reference). `repr()` also drops `__cause__`, the error that explains a wrapped one (the language reference on exception chaining).

## What the code does now

| Where | Form | Names the value? |
|---|---|---|
| Kernel runtime and sequencer: `ProducerFailed.error`, `InputBuildFailed.error`, `RunFinalised.kernel_error`, route and trigger failures, quarantine, finalisation drops (`kernel/runtime.py` ×8, `kernel/sequencer.py` ×5) | `repr(exc)` | No: the record says which class failed, not on what |
| Registration errors wrapping an exception (`kernel/runtime.py` ×2, `kernel/topology.py`) | `{exc!r}` inside a §6.1 message | No |
| Session prompt sources and skills (`session_prompt_producer.py`, `skills.py`) | `repr(exc)` into `SessionWarning.detail` | No |
| coding_flow candidate failure (`coding_flow/__init__.py`) | `{exc!r}` | No |
| Tool loop, delegate (`tool_loop/__init__.py`, `delegate.py`) | `TypeName: str(exc)` | Yes; the cause chain is dropped |
| CLI driver (`adapters/models.py` `CliResponder`) | the spawn's own `OSError` | When its program or its working folder is missing, the path is in `str()` but the record keeps `repr()`; and nothing says which of the two the path was |

`projections/inspect.py` normalizes the `error` field to its class name for cross-run comparison; it finds the class with a regex, so it reads `TypeName: message` as well as `TypeName(...)`.

## What follows

- One function, `describe_error(exc)`, in `substrate/errors.py`: `TypeName: str(exc)` (the class alone when `str` is empty), then `; caused by …` for an explicit `__cause__`, three levels deep at most. Every site above that writes `repr(exc)` or `{exc!r}` into a record or a message calls it.
- The CLI driver names the role of a path it cannot use before it spawns: the working folder ("the session's workspace") that does not exist, or the program that is not on `PATH`.
- Old records keep their `repr` strings; the record never changes.
