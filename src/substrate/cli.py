# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The `substrate` CLI (design §5; F-CLI-1..6, F-API-6).

The CLI is the standing existence proof that the public API is sufficient to build a
reader/runner on public surfaces alone (principle 8). It therefore imports ONLY
`substrate.api` (F-API-6) — never a private module. (Enforced by import-linter in CI; the
single allowed non-api imports are stdlib + click + rich, none of which are substrate
internals.) Output is structured: typed fields, sequence numbers everywhere identification
happens, the eight-word vocabulary, no anthropomorphic synonyms, no emoji. stdout carries
data (the record root, JSONL); stderr carries narration. Exit codes are a contract (§5.1).
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import uuid
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable

import click
from rich.console import Console


from substrate import api


class ListTarget(StrEnum):
    """CLI `/list <target>` — the four valid target values. Sprint 073:
    argv validates via `ListTarget(raw)` at the top of the /list handler
    and dispatches on enum members downstream. `ListTarget(bad)` raises
    `ValueError` naming the offending string; the /list handler catches
    and prints the CLI-facing error."""

    SESSIONS = "sessions"
    TOPOLOGIES = "topologies"
    RECORDS = "records"
    APPLICATIONS = "applications"


class SlashCommand(StrEnum):
    """The nine slash names the REPL router accepts. Drift-grooming
    2026-09-02: each `if slash == "/..."` comparison in `_slash_route`
    now references a member instead of a raw string literal, matching
    the closed-set-of-strings pattern sprints 070–073 established for
    session vocabulary, workspace shape, and driver family. `/exit` is
    the only slash the router does NOT swallow — it returns False so the
    REPL sends the literal `"/exit"` string as a UserMessage; the
    daemon's end-on-exit trigger routes it to SessionEnded{user_exit}."""

    # `/exit` matches session/vocabulary.py::END_ON_EXIT_SENTINEL — the
    # trigger predicate the session topology fires on. F-API-6 keeps
    # substrate.cli off substrate.topologies, so the literal lives in
    # both places; test_cli_slash_221.py pins the pair equal at CI so a
    # rename on one side trips the gate.
    EXIT = "/exit"
    HELP = "/help"
    MODEL = "/model"
    TOOLS = "/tools"
    CONTEXT = "/context"
    INSPECT = "/inspect"
    LIST = "/list"
    REPLAY = "/replay"
    RUN = "/run"


# ── exit codes (design §5.1) ───────────────────────────────────────────────────
EXIT_OK = 0  # run finalised normally
EXIT_FAILED = 1  # run failed (view raised, writer crashed)
EXIT_PAUSED = 2  # run paused awaiting input (pause-await-input)
EXIT_CONFIG = 64  # configuration error (CLI args, topology import, registration)
EXIT_LOCKED = 65  # persistent-bus lock contention
EXIT_SIGINT = 130  # user interrupted

# Narration only; data goes to stdout via click.echo (unwrapped). markup=False is load-bearing:
# the narration lines start with literal tags like [config]/[lock]/[deferred]/[FAIL], which rich
# would otherwise parse as console-markup style tags and SILENTLY EAT (e.g. "[config] ..." would
# print as " ..."). This channel never uses markup, so disable it.
_err = Console(stderr=True, markup=False)


# ── topology loading (a CLI concern; uses only public Runtime/TopologyBuilder) ──
def _load_topology(spec: str) -> Callable[[Any], None]:
    """Resolve a topology factory. `spec` is either a bundled-registry name or a
    `path/to/module.py:func` reference. The module path is executed with the user's
    privileges — no sandbox (technical §17); this is documented, not silent."""
    if ":" in spec and spec.split(":", 1)[0].endswith(".py"):
        return _load_attr(spec)
    # bundled registry name. Populate the bundled registry on demand via a DYNAMIC import, so the
    # CLI's STATIC import surface stays substrate.api-only (F-API-6; import-linter checks static
    # imports, not a runtime importlib call). If the bundled package is unavailable, fall through
    # to whatever is already registered.
    try:
        importlib.import_module("substrate.topologies.bundled").register_all()
    except Exception:  # noqa: BLE001 - bundled topologies are optional; never block a real run
        pass
    try:
        return api.get_topology(spec)
    except KeyError as exc:
        raise click.ClickException(str(exc)) from exc


def _load_attr(spec: str) -> Callable[..., Any]:
    """Resolve a `path/to/module.py:attr` reference to the named attribute (a callable).
    The module path is executed with the user's privileges — no sandbox (technical §17);
    documented, not silent. Shared by topology loading and resume-event loading."""
    path_str, attr_name = spec.split(":", 1)
    path = Path(path_str)
    if not path.exists():
        raise click.ClickException(f"module not found: {path}")
    mod_spec = importlib.util.spec_from_file_location(f"_substrate_mod_{uuid.uuid4().hex}", path)
    if mod_spec is None or mod_spec.loader is None:
        raise click.ClickException(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(mod_spec)
    # Register in sys.modules BEFORE exec (the standard importlib pattern). Without this, a user module
    # combining `from __future__ import annotations` with a `@dataclass` dies at import: dataclass reads
    # the module's globals via `sys.modules[cls.__module__].__dict__`, which is None when the module was
    # loaded from a file spec and never registered (review C-16). Cleaned up on failure so a bad module
    # doesn't leak a half-initialised entry.
    sys.modules[mod_spec.name] = module
    try:
        mod_spec.loader.exec_module(module)
    except Exception as exc:
        # Importing/executing the user module failed (ImportError, SyntaxError, a raise at module
        # scope, ...). Surface it as a clean config error (-> EXIT_CONFIG) naming the cause, not a
        # raw traceback escaping the CLI.
        sys.modules.pop(mod_spec.name, None)  # don't leak a half-initialised module
        raise click.ClickException(f"failed to import {path}: {type(exc).__name__}: {exc}") from exc
    if not hasattr(module, attr_name):
        raise click.ClickException(f"module {path} has no attribute {attr_name!r}")
    return getattr(module, attr_name)  # type: ignore[no-any-return]


_FAILURE_KINDS = (
    api.PRODUCER_FAILED,
    api.INPUT_BUILD_FAILED,
    api.PREDICATE_QUARANTINED,
    api.PRODUCER_EMITTED_INVALID,
)


def _failure_summary(root: Path) -> tuple[dict[str, int], int]:
    """Count the authoring-failure events on a record, so a run that finalised but silently did
    nothing is surfaced to the AUTHOR (not merely honest on the record). Returns (counts, total)."""
    counts: dict[str, int] = {}
    for env in api.read_record(root):
        kind = str(env.get("kind", ""))
        if kind in _FAILURE_KINDS:
            short = kind.removeprefix("substrate.")
            counts[short] = counts.get(short, 0) + 1
    return counts, sum(counts.values())


def _producer_label(ref: dict[str, Any] | None) -> str:
    if not isinstance(ref, dict):
        return ""
    kind = ref.get("kind", "?")
    inst = ref.get("instance")
    return f"{kind}[{inst}]" if inst else str(kind)


def _format_event_line(env: dict[str, Any]) -> str:
    """One aligned human-readable line for `tail` (design §5.2 default format)."""
    seq = env.get("seq")
    kind = str(env.get("kind", ""))
    payload = env.get("payload") or {}
    ref = env.get("producer")
    bits: list[str] = []
    if ref:
        bits.append(f"producer={_producer_label(ref)}")
    if isinstance(payload, dict):
        for k, v in payload.items():
            if k in ("topology", "schemas", "baseline"):  # large; elide in the aligned view
                continue
            bits.append(f"{k}={v}")
    return f"seq={seq:<5} {kind:<34} {'  '.join(bits)}"


async def _run_maybe_tailing(
    rt: Any, topology: Any, record_root: Path, tail_live: bool, verbose: bool
) -> Any:
    return await _drive_maybe_tailing(rt.run(topology), record_root, tail_live, verbose)


async def _resume_maybe_tailing(
    rt: Any, topology: Any, resume_event: Any, record_root: Path, tail_live: bool, verbose: bool
) -> Any:
    return await _drive_maybe_tailing(
        rt.resume(topology, resume_event=resume_event), record_root, tail_live, verbose
    )


async def _drive_maybe_tailing(coro: Any, record_root: Path, tail_live: bool, verbose: bool) -> Any:
    """Drive a run/resume coroutine; when `tail_live`, concurrently stream its events to
    stderr over a read-only follower as it progresses (design §5.1 `--tail`/`--verbose`).
    The follower is the same F-PERS-4 read-only attach path — it observes the record, never
    the runtime's internals. The follower task is cancelled once the drive task completes
    (and one final drain catches the tail)."""
    if not tail_live:
        return await coro

    run_task = asyncio.ensure_future(coro)
    live = api.attach(record_root, poll_ms=20)  # one follower, cursor shared across drains

    def _drain() -> None:
        for env in live.read_new():
            if not verbose and str(env.get("kind", "")).startswith("substrate."):
                continue
            _err.print(_format_event_line(env))

    async def _stream() -> None:
        while True:
            _drain()
            await asyncio.sleep(0.02)

    stream_task = asyncio.ensure_future(_stream())
    try:
        result = await run_task
    finally:
        stream_task.cancel()
        try:
            await stream_task
        except asyncio.CancelledError:
            pass
        _drain()  # final drain: emit anything written between the last poll and run end
    return result


# ── the command group ──────────────────────────────────────────────────────────
def _resolve_version() -> str:
    # resolved locally (not imported from the package top level) to keep the F-API-6 boundary — cli
    # imports only substrate.api. click's default --version lookup infers the dist from the import name
    # ("substrate"), but the dist is "substrate-kernel", so the default raised a traceback (review C-4).
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _dist_version

    try:
        return _dist_version("substrate-kernel")
    except PackageNotFoundError:  # pragma: no cover — bare source tree, no installed metadata
        return "0.0.0"


@click.group(invoke_without_command=True)
@click.pass_context
@click.version_option(version=_resolve_version(), message="substrate %(version)s")
def main(ctx: click.Context) -> None:
    """Substrate — a concurrent streaming dataflow runtime. Read the run record; never the
    runtime's mind. Every command cites sequence numbers.

    Bare `substrate` (no subcommand) dispatches to `chat` with defaults from
    `~/.substrate/config.toml [defaults]` — piece D sprint 218."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(chat)


@main.command()
@click.option("--topology", "topology_name", help="bundled topology name")
@click.option(
    "--topology-module",
    "topology_module",
    help="path/to/module.py:func — EXECUTES that module as code with your privileges "
    "(no sandbox); only point it at code you trust",
)
@click.option("--root", "root", default=None, help="record root (default: ./runs/<run-id>)")
@click.option("--persistent", is_flag=True, help="persistent-bus mode (exclusive lock)")
@click.option("--writer-stats", is_flag=True, help="emit the off-bus writer_stats sidecar")
@click.option("--diagnostics", is_flag=True, help="emit the off-bus diagnostics sidecar")
@click.option(
    "--tail", "tail_live", is_flag=True, help="stream events to stderr while the run progresses"
)
@click.option(
    "--verbose", is_flag=True, help="with --tail, also stream substrate.* lifecycle events"
)
@click.option(
    "--strict", is_flag=True, help="exit nonzero if any Producer/input/predicate failure occurred"
)
def run(
    topology_name: str | None,
    topology_module: str | None,
    root: str | None,
    persistent: bool,
    writer_stats: bool,
    diagnostics: bool,
    tail_live: bool,
    verbose: bool,
    strict: bool,
) -> None:
    """Run a topology to a run record (F-CLI-1). Prints the record root to stdout on every
    exit. Exit: 0 finalised, 1 failed, 2 paused, 64 config, 65 lock contention, 130 SIGINT.

    --tail streams events to stderr as the run progresses (default: application events
    only; add --verbose for substrate.* lifecycle events too) over the read-only attach
    follower (F-PERS-4) — the run record is the source of truth, never the runtime's
    internals."""
    spec = topology_module or topology_name
    if not spec:
        # an arg error before any run is contemplated — no record root exists to print.
        _err.print("[config] one of --topology or --topology-module is required")
        sys.exit(EXIT_CONFIG)
    # Compute the record root up front so it can be printed on EVERY exit that contemplates
    # a run (design §5.1: "the record root path is printed to stdout on every exit"), incl.
    # the topology-load / registration / lock failure paths below.
    record_root = Path(root) if root else Path("runs") / str(uuid.uuid4())
    try:
        topology = _load_topology(spec)
    except click.ClickException as exc:
        _err.print(f"[config] {exc.message}")
        click.echo(str(record_root))
        sys.exit(EXIT_CONFIG)

    rt = api.Runtime(
        record_root, persistent=persistent, writer_stats=writer_stats, diagnostics=diagnostics
    )
    try:
        result = asyncio.run(_run_maybe_tailing(rt, topology, record_root, tail_live, verbose))
    except KeyboardInterrupt:
        click.echo(str(record_root))
        sys.exit(EXIT_SIGINT)
    except api.BusLockedError as exc:  # by TYPE via the public api surface, not string-match
        _err.print(f"[lock] {exc}")
        click.echo(str(record_root))
        sys.exit(EXIT_LOCKED)
    except (api.RegistrationError, api.UnsupportedPlatformError) as exc:
        _err.print(f"[config] {type(exc).__name__}: {exc}")
        click.echo(str(record_root))
        sys.exit(EXIT_CONFIG)
    # the record root is the load-bearing stdout line (shell-pipeable)
    click.echo(result.record_root)
    code = {"finalised": EXIT_OK, "failed": EXIT_FAILED, "paused": EXIT_PAUSED}[result.status]
    # Surface authoring failures: a run can finalise while Producers/inputs/predicates FAILED (the
    # failures are honestly on the record, but a newcomer's eye is on this status line — make a
    # broken run LOOK broken). --strict turns any such failure into a nonzero exit.
    fail_counts, fail_total = _failure_summary(record_root)
    if fail_total:
        summary = ", ".join(f"{n} {k}" for k, n in sorted(fail_counts.items()))
        _err.print(f"[{result.status}] {result.record_root}  WARNING: {summary} (read the record)")
        if strict and code == EXIT_OK:
            code = EXIT_FAILED
    else:
        _err.print(f"[{result.status}] {result.record_root}")
    sys.exit(code)


@main.command()
@click.argument("root", type=click.Path(exists=True))
@click.option("--kind", "kinds", default=None, help="comma-separated kinds (AND with others)")
@click.option("--producer", "producer", default=None, help="producer kind prefix or full ref")
@click.option("--since", "since", type=int, default=None, help="only seq >= this")
@click.option("--format", "fmt", type=click.Choice(["aligned", "jsonl"]), default="aligned")
@click.option("--follow/--no-follow", default=False, help="stay attached past current end")
def tail(
    root: str,
    kinds: str | None,
    producer: str | None,
    since: int | None,
    fmt: str,
    follow: bool,
) -> None:
    """Stream events from a live or closed record (F-CLI-5). Filters compose with AND."""
    import json as _json

    kind_set = set(kinds.split(",")) if kinds else None

    def _passes(env: dict[str, Any]) -> bool:
        if kind_set is not None and str(env.get("kind")) not in kind_set:
            return False
        if since is not None and int(env.get("seq", -1)) < since:
            return False
        if producer is not None:
            ref = env.get("producer")
            if not isinstance(ref, dict):
                return False
            label = _producer_label(ref)  # "kind[instance]"
            kind = str(ref.get("kind", ""))
            # design §5.2 / F-CLI-5: `--producer` accepts a KIND PREFIX (matches all
            # instances) OR a full producer ref. A full ref matches exactly; otherwise the
            # arg is a prefix of the kind.
            if not (label == producer or kind == producer or kind.startswith(producer)):
                return False
        return True

    def _emit(env: dict[str, Any]) -> None:
        if not _passes(env):
            return
        if fmt == "jsonl":
            click.echo(_json.dumps(env, sort_keys=True, separators=(",", ":")))
        else:
            click.echo(_format_event_line(env))

    if follow:
        live = api.attach(root)
        try:
            for env in live.follow(until_finalised=True):
                _emit(env)
        except KeyboardInterrupt:
            sys.exit(EXIT_SIGINT)
    else:
        for env in api.read_record(root):
            _emit(env)


@main.command()
@click.argument("root", type=click.Path(exists=True))
@click.option("--producer", "producer", default=None, help="a producer ref kind[instance]")
@click.option("--why", is_flag=True, help="proximate cause (one firing / RunStarted)")
@click.option("--ancestry", is_flag=True, help="full causal chain to RunStarted")
@click.option("--seq", "seq", type=int, default=None, help="the event at seq N")
@click.option("--between", "between", nargs=2, type=int, default=None, help="substrate.* in [A,B]")
@click.option("--diff", "diff_root", type=click.Path(exists=True), default=None)
def inspect(
    root: str,
    producer: str | None,
    why: bool,
    ancestry: bool,
    seq: int | None,
    between: tuple[int, int] | None,
    diff_root: str | None,
) -> None:
    """Deterministic queries over a record (design §5.3). Every output cites seq numbers."""
    if diff_root is not None:
        div = api.first_divergence(root, diff_root)
        if div is None:
            click.echo("equivalent under D-8 (no divergence)")
        else:
            click.echo(f"first divergence at index {div.index} (seq={div.seq}):")
            click.echo(f"  a: kind={div.kind_a} hash={div.hash_a}")
            click.echo(f"  b: kind={div.kind_b} hash={div.hash_b}")
        return
    if producer is not None and ancestry:
        try:
            chain = list(api.trace_ancestry(root, producer))
        except (api.ProducerNotFound, api.SequenceOutOfRange) as exc:
            _err.print(f"[config] {exc}")  # a bad producer ref is a config error, not a traceback
            sys.exit(EXIT_CONFIG)
        for exp in chain:
            click.echo(
                f"{exp.kind}[{exp.instance}]  caused_by {exp.cause} at seq={exp.at_seq}"
                + (f" (trigger={exp.trigger_id})" if exp.trigger_id else "")
            )
        return
    if producer is not None and why:
        try:
            exp = api.explain_producer(root, producer)
        except (api.ProducerNotFound, api.SequenceOutOfRange) as exc:
            _err.print(f"[config] {exc}")  # clean error, consistent with run's [config] shape
            sys.exit(EXIT_CONFIG)
        click.echo(f"producer={exp.kind}[{exp.instance}]")
        click.echo(f"parent={exp.parent}")
        click.echo("caused_by:")
        click.echo(f"  seq={exp.at_seq}  {exp.cause}")
        click.echo(f"    trigger={exp.trigger_id}")
        click.echo(f"    firing_key={exp.firing_key}")
        click.echo(f"    input_sha256={exp.input_sha256}")
        return
    if between is not None:
        for ev in api.decisions_between(root, between[0], between[1]):
            click.echo(f"seq={ev.seq:<5} {ev.kind}")
        return
    if seq is not None:
        for env in api.read_record(root):
            if int(env.get("seq", -1)) == seq:
                click.echo(_format_event_line(env))
                return
        raise click.ClickException(f"no event at seq {seq}")
    raise click.ClickException("inspect needs one of --why/--ancestry/--seq/--between/--diff")


@main.command()
@click.argument("root", type=click.Path(exists=True))
@click.option(
    "--lifecycle",
    is_flag=True,
    help="include the producer-lifecycle bracketing (Started/Completed/Injection) beats",
)
@click.option(
    "--summary",
    is_flag=True,
    help="emit a one-paragraph digest (counts + finalisation) instead of per-event prose",
)
def narrate(root: str, lifecycle: bool, summary: bool) -> None:
    """Narrate a record as a legible prose account — the plot of the run (Wave 14).

    A read-only projection over the log (no run, no network): the substrate.* causal beats
    in prose (a TriggerFired as "starts X", terminations, finalisation, and every authoring
    failure) interleaved with the application events (the work). Lifecycle bracketing is
    suppressed by default; --lifecycle restores the every-frame account. Every line cites a
    seq. --summary prints a digest instead."""
    if summary:
        s = api.narration_summary(api.read_record(root))
        fails = (
            s.producers_failed
            + s.input_build_failures
            + s.predicate_quarantines
            + s.invalid_emissions
        )
        # The HEADER must answer "did my run work?" at a glance (review #26): a finalised run
        # with failures is NOT a green run — say so on line 1, not line 3 ("finalised" alone
        # reads green and buries the alarm). This closes the #19 "finalised != worked" thread
        # in the layer best positioned to answer it.
        if not s.finalised:
            head = "Run NOT finalised (incomplete record)"
        elif fails:
            head = f"Run finalised WITH {fails} FAILURE{'S' if fails != 1 else ''}"
        elif s.final_reason:
            head = f"Run finalised ({s.final_reason})"
        else:
            head = "Run finalised"
        click.echo(f"{head}: {s.total_events} events.")
        click.echo(
            f"  producers: {s.producers_started} started, {s.producers_completed} completed, "
            f"{s.producers_cancelled} cancelled, {s.producers_failed} failed"
        )
        if fails:
            click.echo(
                f"  failures: {s.producers_failed} ProducerFailed, "
                f"{s.input_build_failures} InputBuildFailed, "
                f"{s.predicate_quarantines} PredicateQuarantined, "
                f"{s.invalid_emissions} ProducerEmittedInvalidEvent (read the record)"
            )
        if s.application_events:
            work = ", ".join(f"{k}={n}" for k, n in sorted(s.application_events.items()))
            click.echo(f"  work: {work}")
        return
    # Default mode: stream the plot, tallying authoring-failure beats so a long run's failures
    # (which can scroll past inline) get a footer pointing at the digest (review #26, optional).
    fail_lines = 0
    for line in api.narrate(api.read_record(root), lifecycle=lifecycle):
        click.echo(f"seq {line.seq:>5}  {line.text}")
        if line.kind in _FAILURE_KINDS:
            fail_lines += 1
    if fail_lines:
        _err.print(
            f"[warning] {fail_lines} authoring failure(s) above "
            f"-- run `substrate narrate {root} --summary` for the tally"
        )


@main.command()
@click.argument("root", type=click.Path(exists=True))
@click.option("--level", type=click.Choice(["1", "2", "3a", "3b"]), default="1")
@click.option("--diff", "diff_root", type=click.Path(exists=True), default=None)
def replay(root: str, level: str, diff_root: str | None) -> None:
    """Replay a record at an honesty tier (F-CLI-2). Exit 0 on success, non-zero on failure
    or on a refused/deferred tier."""
    if diff_root is not None:
        div = api.first_divergence(root, diff_root)
        if div is None:
            click.echo("equivalent under D-8 (no divergence)")
        else:
            click.echo(f"first divergence at index {div.index} (seq={div.seq})")
        return
    try:
        result = api.replay(root, level=level)  # type: ignore[arg-type]
    except NotImplementedError as exc:
        # Level 3(b) is a documented deferral (spec amendment A1.1), surfaced as a distinct
        # message, NOT a silent pass and NOT an opaque crash.
        _err.print(f"[deferred] {exc}")
        sys.exit(EXIT_FAILED)
    if result.mismatches:
        _err.print(f"[FAIL] level {level}: {len(result.mismatches)} input-hash mismatch(es)")
        for m in result.mismatches:
            _err.print(f"  seq={m.seq} trigger={m.trigger_id} recorded={m.recorded}")
        sys.exit(EXIT_FAILED)
    if level == "3a" and result.preconditions_ok is False:
        _err.print(f"[FAIL] Level 3(a) refused: {result.refusal_reason}")
        sys.exit(EXIT_FAILED)
    if level == "3a":
        # Level 3(a) gate-checks the re-execution PRECONDITIONS (replay ceiling 3a + every
        # Producer kind author-deterministic) and re-verifies the Level-2 input hashes; it does
        # NOT itself re-execute the Producers (re-execution is the Runtime's job, against the
        # same record). Say so plainly rather than implying a re-run happened.
        click.echo("[OK] Level 3(a) preconditions verified (re-execution NOT performed).")
    else:
        click.echo(f"[OK] Level {level} replay successful.")
    click.echo(f"Frames replayed: {result.frame_count}")
    if level in ("2", "3a"):
        click.echo(f"Decisions verified: {result.decisions_verified} (all inputs verified by hash)")


@main.command()
@click.option("--topology-module", "topology_module", required=True, help="path/to/module.py:func")
def validate(topology_module: str) -> None:
    """Static topology lint (F-CLI-3): registration, plus undeclared event-kind references, a
    missing TerminationPolicy, wall-clock cooldown flags, and a counts summary. Runs nothing.
    Exit 0 (clean) / 64 (registration error or a lint failure)."""
    try:
        topology = _load_topology(topology_module)
        builder = api.TopologyBuilder()
        topology(builder)
        reg = builder.build()
    except click.ClickException as exc:
        _err.print(f"[FAIL] {exc.message}")
        sys.exit(EXIT_CONFIG)
    except Exception as exc:
        _err.print(f"[FAIL] {type(exc).__name__}: {exc}")
        sys.exit(EXIT_CONFIG)

    # the set of every event kind some Producer can emit; a Predicate/Route subscribing to a kind
    # outside this set (and outside the reserved substrate.* lifecycle namespace) is a dead reference.
    declared = {kind for pk in reg.producer_kinds.values() for kind in pk.schemas}
    failures: list[str] = []
    for t in reg.triggers:
        for kind in sorted(t.subscription.kinds):
            if not kind.startswith("substrate.") and kind not in declared:
                failures.append(
                    f"trigger {t.id!r} subscribes to kind {kind!r}, which no Producer declares"
                )
    for r in reg.routes:
        for kind in sorted(r.subscription.kinds):
            if not kind.startswith("substrate.") and kind not in declared:
                failures.append(
                    f"route {r.id!r} subscribes to kind {kind!r}, which no Producer declares"
                )

    click.echo(
        f"{len(reg.producer_kinds)} Producer kinds, {len(reg.triggers)} Triggers, "
        f"{len(reg.routes)} Routes, {len(reg.views)} Views, "
        f"{1 if reg.termination is not None else 0} TerminationPolicy."
    )
    if reg.has_wall_clock_cooldown:
        click.echo('1+ WallClock cooldown registered -> replay ceiling = "3b".')
    if reg.termination is None:
        click.echo(
            "note: no TerminationPolicy registered -> the run defaults to quiescence-with-watchdog."
        )

    if failures:
        _err.print(f"[FAIL] {len(failures)} issue(s):")
        for f in failures:
            _err.print(f"  - {f}")
        sys.exit(EXIT_CONFIG)
    click.echo("[OK] Topology validates.")


@main.command()
@click.argument("root", type=click.Path(exists=True))
@click.option(
    "--sidecar", type=click.Choice(["writer_stats", "diagnostics"]), default="writer_stats"
)
def stats(root: str, sidecar: str) -> None:
    """Read an off-bus sidecar (writer_stats / diagnostics) from a record (§6.4 / §3.8)."""
    path = Path(root) / "sidecar" / f"{sidecar}.jsonl"
    records = api.read_sidecar(path)
    if not records:
        _err.print(f"[empty] no {sidecar} sidecar at {path}")
        return
    click.echo(f"{sidecar}: {len(records)} record(s)")
    for r in records[-10:]:
        click.echo("  " + "  ".join(f"{k}={v}" for k, v in sorted(r.items())))


@main.command()
@click.option("--no-perf", is_flag=True, help="skip the perf-floor probe (check 15)")
def conformance(no_perf: bool) -> None:
    """Run the 17-check conformance suite — the v1.0 release gate (F-CLI-4, product §7).

    Each check prints PASS / FAIL / DEFERRED / SKIPPED, four DISTINCT states. DEFERRED
    (check 6, Level-3b byte-identity — spec amendment A1.1) is a ruled "not shippable in
    v1.0"; SKIPPED is a run-time skip (e.g. check 15 under --no-perf) and is NOT spec-amended.
    Neither prints green; neither is a pass. Exit: 0 iff no check FAILED, 1 if any FAILED.
    Run WITHOUT --no-perf in CI so the N-PERF-1 floor miss cannot be masked."""
    report = asyncio.run(api.run_conformance(include_perf=not no_perf))
    n = len(report.results)
    _err.print(f"Running {n} conformance checks (product §7)...")
    tags = {
        "PASS": "PASS",
        "FAIL": "FAIL",
        "DEFERRED": "DEFERRED (spec-amended A1.1)",
        "SKIPPED": "SKIPPED (--no-perf; not spec-amended)",
    }
    for r in report.results:
        click.echo(f"  [{r.number:02d}/17] {r.name:<32} ... {tags[r.status.value]}")
        # show the detail for any non-PASS, AND always for the perf check (operators want the
        # measured appends/sec number even when it PASSES the floor).
        if r.status.value != "PASS" or r.number == 15:
            _err.print(f"         {r.detail}")
    summary = (
        f"{report.passed} passed, {report.failed} failed, "
        f"{report.deferred} deferred, {report.skipped} skipped"
    )
    if report.all_non_failing:
        click.echo(f"\n{summary}. No check FAILED.")
        if report.deferred:
            _err.print(
                f"NOTE: {report.deferred} check(s) DEFERRED (spec-amended, A1.1) — distinct "
                f"from pass; v1.0 ships with these deferred. NOT a green pass."
            )
        if report.skipped:
            _err.print(
                f"NOTE: {report.skipped} check(s) SKIPPED on this invocation (e.g. --no-perf) "
                f"— run the default `substrate conformance` (no flags) to exercise them."
            )
        sys.exit(EXIT_OK)
    click.echo(f"\n{summary}. {report.failed} FAILED — release gate not met.")
    sys.exit(EXIT_FAILED)


@main.command()
@click.argument("root", type=click.Path(exists=True))
@click.option("--topology", "topology_name", help="bundled topology name")
@click.option(
    "--topology-module",
    "topology_module",
    help="path/to/module.py:func — EXECUTES that module as code with your privileges "
    "(no sandbox); only point it at code you trust",
)
@click.option(
    "--input",
    "input_spec",
    required=True,
    help="resume event factory: path/to/module.py:func (zero-arg callable -> the external "
    "resume event Struct a resume Trigger subscribes to)",
)
@click.option(
    "--tail", "tail_live", is_flag=True, help="stream events to stderr while the run progresses"
)
@click.option(
    "--verbose", is_flag=True, help="with --tail, also stream substrate.* lifecycle events"
)
def resume(
    root: str,
    topology_name: str | None,
    topology_module: str | None,
    input_spec: str,
    tail_live: bool,
    verbose: bool,
) -> None:
    """Resume a paused persistent-bus run (F-TERM-3 / F-CLI; design §6).

    Reattaches to the EXISTING record at <root> (re-acquires the exclusive lock, restores
    next_seq from the log tail, refolds the registered Views over the record), appends the
    external resume event so the resume Trigger fires the continuation Producer, and drives
    to the next terminal — appending on the SAME seq sequence as the paused run.

    The topology is re-resolved fresh (same factory the paused run used). Exit: 0 finalised,
    1 failed, 2 paused (paused again), 64 config, 65 lock contention, 130 SIGINT."""
    record_root = Path(root)
    spec = topology_module or topology_name
    if not spec:
        _err.print("[config] one of --topology or --topology-module is required")
        click.echo(str(record_root))
        sys.exit(EXIT_CONFIG)
    try:
        topology = _load_topology(spec)
        event_factory = _load_attr(input_spec) if ":" in input_spec else None
        if event_factory is None:
            raise click.ClickException(
                f"--input must be a path/to/module.py:func reference, got {input_spec!r}"
            )
        resume_event = event_factory()
    except click.ClickException as exc:
        _err.print(f"[config] {exc.message}")
        click.echo(str(record_root))
        sys.exit(EXIT_CONFIG)

    # resume is a persistent-bus operation by construction (it reattaches to an existing,
    # lock-guarded record) — the runtime enforces persistent=True for resume().
    rt = api.Runtime(record_root, persistent=True)
    try:
        result = asyncio.run(
            _resume_maybe_tailing(rt, topology, resume_event, record_root, tail_live, verbose)
        )
    except KeyboardInterrupt:
        click.echo(str(record_root))
        sys.exit(EXIT_SIGINT)
    except api.BusLockedError as exc:
        _err.print(f"[lock] {exc}")
        click.echo(str(record_root))
        sys.exit(EXIT_LOCKED)
    except (api.RegistrationError, api.UnsupportedPlatformError) as exc:
        _err.print(f"[config] {type(exc).__name__}: {exc}")
        click.echo(str(record_root))
        sys.exit(EXIT_CONFIG)
    click.echo(result.record_root)
    code = {"finalised": EXIT_OK, "failed": EXIT_FAILED, "paused": EXIT_PAUSED}[result.status]
    _err.print(f"[{result.status}] {result.record_root}")
    sys.exit(code)


@main.group()
def topology() -> None:
    """The bundled topology registry (runnable via `substrate run --topology <name>`)."""


@topology.command("list")
def topology_list() -> None:
    """List bundled topology names, one per line. Discoverability for the --topology flag."""
    names: list[str]
    try:
        # dynamic import keeps the CLI's static surface substrate.api-only (F-API-6).
        names = importlib.import_module("substrate.topologies.bundled").names()
    except Exception:  # noqa: BLE001 - bundled topologies are optional
        names = []
    for name in names:
        click.echo(name)


@main.group()
def demo() -> None:
    """Run or replay a bundled demonstration topology (the one-command on-ramp)."""


@demo.command("replay")
@click.argument("name")
@click.pass_context
def demo_replay(ctx: click.Context, name: str) -> None:
    """Replay a bundled topology's committed CI record — tail it (no run, no network)."""
    record = importlib.import_module("substrate.topologies.bundled").record_path(name)
    if not record.exists():
        _err.print(
            f"[config] no committed record for {name!r}. Try `substrate topology list`, "
            f"or `substrate demo run {name}` to run it live."
        )
        sys.exit(EXIT_CONFIG)
    ctx.invoke(
        tail, root=str(record), kinds=None, producer=None, since=None, fmt="aligned", follow=False
    )


@demo.command("run")
@click.argument("name")
@click.option("--root", "root", default=None, help="record root (default: ./runs/<run-id>)")
@click.pass_context
def demo_run(ctx: click.Context, name: str, root: str | None) -> None:
    """Run a bundled topology live (CI-default, deterministic) and stream it to stderr."""
    ctx.invoke(
        run,
        topology_name=name,
        topology_module=None,
        root=root,
        persistent=False,
        writer_stats=False,
        diagnostics=False,
        tail_live=True,
        verbose=False,
        strict=False,
    )


@main.command()
@click.argument("root", type=click.Path(exists=True))
@click.option("--rule", "rule_name", default="brier", help="brier | log_loss | spherical")
def score(root: str, rule_name: str) -> None:
    """Score a record's Grade events under a proper rule — the calibration PAYOFF (lower is
    better). Turns 'calibration pays, confident-sounding doesn't' from raw Grade rows into a
    per-speaker result. Closes the cheap-talk loop the grader instrument opens."""
    grades = [e["payload"] for e in api.read_record(Path(root)) if e.get("kind") == "Grade"]
    if not grades:
        _err.print("[config] no Grade events here; run a topology with scoring on first")
        sys.exit(EXIT_CONFIG)
    # dynamic import keeps the CLI's static surface substrate.api-only (F-API-6).
    scoring = importlib.import_module("substrate.topologies.instruments.scoring")
    grader = importlib.import_module("substrate.topologies.instruments.grader")
    try:
        rule = scoring.select_scoring_rule(rule_name)
    except Exception as exc:  # noqa: BLE001 - unknown rule -> clean config error
        _err.print(f"[config] {exc}")
        sys.exit(EXIT_CONFIG)
    try:
        # record payload fields are attacker-controllable; a malformed Grade (non-numeric /
        # out-of-range confidence) is a clean config error, not an uncaught traceback (review #20).
        losses = grader.score_grades(grades, rule)
    except Exception as exc:  # noqa: BLE001 - any malformed Grade payload -> clean [config]
        _err.print(f"[config] malformed Grade payload in record: {exc}")
        sys.exit(EXIT_CONFIG)
    by_speaker: dict[str, list[float]] = {}
    for claim, loss in losses.items():
        by_speaker.setdefault(str(claim).split("-", 1)[0], []).append(float(loss))
    click.echo(f"calibration loss ({rule_name}, lower is better):")
    for spk in sorted(by_speaker):
        vals = by_speaker[spk]
        click.echo(f"  {spk}: mean={sum(vals) / len(vals):.4f}  n={len(vals)}")


# ── piece D (sprint 218): chat + daemon verbs; config loader ────────────────────


def _config_path_default() -> Path:
    from substrate.api import substrate_home

    return substrate_home() / "config.toml"


def _load_config(path: Path | None = None) -> dict[str, Any]:
    """Read `~/.substrate/config.toml`. Missing file → empty dict; malformed
    TOML → empty dict with a stderr warning. The CLI applies section-specific
    defaults on top of whatever this returns."""
    import tomllib

    p = path if path is not None else _config_path_default()
    if not p.exists():
        return {}
    try:
        with p.open("rb") as fp:
            return tomllib.load(fp)
    except tomllib.TOMLDecodeError as exc:
        _err.print(f"[config] {p}: {type(exc).__name__}: {exc}; using defaults")
        return {}


def _defaults() -> dict[str, Any]:
    """`[defaults]` block from the config, with baked-in fallbacks matching
    templates/config.toml."""
    section = _load_config().get("defaults", {})
    if not isinstance(section, dict):
        section = {}
    return {
        "driver": str(section.get("driver", "deterministic")),
        "role": str(section.get("role", "default")),
        "bundle": section.get("bundle") or None,
        "workspace": str(section.get("workspace", ".")),
        "isolate": bool(section.get("isolate", False)),
    }


def _daemon_server_path() -> str | None:
    """`[daemon] server_path` — the absolute path to `substrate-ui/server.py`
    the CLI auto-launches. Returns None if unset."""
    section = _load_config().get("daemon", {})
    if not isinstance(section, dict):
        return None
    path = section.get("server_path")
    if not path or not isinstance(path, str):
        return None
    return path


def _double_fork_daemon(server_path: str) -> None:
    """POSIX daemonize: fork, setsid, fork, exec `python server_path`. The
    grandchild inherits stdin/stdout/stderr redirected to /dev/null so the
    parent shell is not held open."""
    import os as _os

    pid = _os.fork()
    if pid != 0:
        _os.waitpid(pid, 0)
        return
    _os.setsid()
    pid2 = _os.fork()
    if pid2 != 0:
        _os._exit(0)
    devnull = _os.open(_os.devnull, _os.O_RDWR)
    _os.dup2(devnull, 0)
    _os.dup2(devnull, 1)
    _os.dup2(devnull, 2)
    _os.execv(sys.executable, [sys.executable, server_path])


def _ensure_daemon_running() -> None:
    """Try to connect to the daemon; if neither UDS nor TCP is up, auto-launch
    per `[daemon] server_path` and wait up to 3 s. Exit 64 on any failure to
    reach a running daemon after the launch attempt."""
    from substrate import _daemon

    if _daemon.is_running(timeout=1.0):
        return
    server_path = _daemon_server_path()
    if not server_path:
        _err.print(
            "[config] daemon not running and [daemon] server_path is empty in "
            f"{_config_path_default()} — set it to the absolute path of "
            "substrate-ui/server.py, or start the daemon manually."
        )
        raise SystemExit(EXIT_CONFIG)
    if not Path(server_path).exists():
        _err.print(f"[config] [daemon] server_path {server_path!r} does not exist")
        raise SystemExit(EXIT_CONFIG)
    _double_fork_daemon(server_path)
    import time as _time

    for _ in range(30):
        if _daemon.is_running(timeout=0.5):
            return
        _time.sleep(0.1)
    _err.print("[config] daemon failed to start; try `substrate daemon --foreground`")
    raise SystemExit(EXIT_CONFIG)


# ── piece D sprint 219: REPL loop + SSE streaming during a blocked turn ─────


def _readline_with_interrupt(prompt: str = "> ") -> str:
    """Cooked-mode readline. Raises `EOFError` on Ctrl+D and lets
    `KeyboardInterrupt` propagate on Ctrl+C. Python's built-in `input()`
    already delivers both signals; wrapped here so the REPL loop reads as
    "readline that surfaces the two exits."
    """
    return input(prompt)


def _render_stream_line(env: dict[str, Any], *, verbose: bool = False) -> None:
    """Format one record envelope for the REPL's stderr stream.

    ModelReply text prints to stdout as it lands (the assistant's voice).
    ToolCall renders as `→ tool(args)`; ToolResult as `← ok (N bytes)` or
    `← FAIL: <error>`. `substrate.*` events are suppressed unless `verbose`
    is set. FinalAnswer is skipped — its text has already streamed as
    ModelReply, and re-emitting it would duplicate.
    """
    import json as _json

    kind = str(env.get("kind", ""))
    payload = env.get("payload") or {}
    if not isinstance(payload, dict):
        return
    if kind == api.MODEL_REPLY:
        text = str(payload.get("text", ""))
        if text:
            click.echo(text)
    elif kind == api.FINAL_ANSWER:
        return  # already streamed via ModelReply
    elif kind == api.TOOL_CALL:
        tool_name = str(payload.get("tool", "?"))
        args = payload.get("args", [])
        args_str = ", ".join(repr(a) for a in args) if isinstance(args, list) else str(args)
        _err.print(f"→ {tool_name}({args_str})")
    elif kind == api.TOOL_RESULT:
        ok = bool(payload.get("ok", True))
        if ok:
            output = payload.get("output", "")
            try:
                size = len(_json.dumps(output))
            except (TypeError, ValueError):
                size = len(str(output))
            _err.print(f"← ok ({size} bytes)")
        else:
            _err.print(f"← FAIL: {payload.get('error', 'unknown')}")
    elif kind.startswith("substrate.") and verbose:
        _err.print(f"[substrate] {kind}")


def _sse_stream(session_id: str, stop_event: Any, *, verbose: bool = False) -> None:
    """Background thread body: open `GET /api/session/<id>/events?since_seq=-1`
    against the daemon and format each frame via `_render_stream_line`. The
    thread exits when `stop_event` is set, when the daemon writes
    `substrate.RunFinalised`, or on any transport error. Uses `read1(N)` so
    a partial SSE frame does not block past its bytes."""
    import json as _json

    from substrate import _daemon

    try:
        conn = _daemon._connect(timeout=None)
        conn.request("GET", f"/api/session/{session_id}/events?since_seq=-1")
        resp = conn.getresponse()
    except Exception:  # noqa: BLE001 — daemon dropped; end the stream quietly
        return
    buf = b""
    try:
        while not stop_event.is_set():
            try:
                chunk = resp.read1(65536)
            except Exception:  # noqa: BLE001 — connection dropped mid-read
                break
            if not chunk:
                break
            buf += chunk
            while b"\n\n" in buf:
                block, buf = buf.split(b"\n\n", 1)
                for line in block.splitlines():
                    if not line.startswith(b"data: "):
                        continue
                    raw = line[len(b"data: ") :]
                    try:
                        env = _json.loads(raw)
                    except ValueError:
                        continue
                    _render_stream_line(env, verbose=verbose)
                    if str(env.get("kind", "")) == api.RUN_FINALISED:
                        stop_event.set()
                        return
    finally:
        # Connection already torn by the daemon or by network — the close is
        # a cleanup, not a state-changing operation. Swallow OSError only so
        # a secondary failure never masks whatever raised in the try body.
        try:
            resp.close()
            conn.close()
        except OSError:
            pass


# ── piece D sprint 221: slash-command router (nine slashes per §6 table) ────

_SLASH_HELP = """slashes (piece D sprint 221):
  /exit                       end the session (fires SessionEnded{user_exit})
  /model <name>               PATCH the session's driver; persists across parks
  /tools <a,b,c>              PATCH the session's tool allow-list; persists
  /context <lo-hi> [--kind K] attach a parent-record slice to the next turn
  /inspect <record> [--filter K]  narrate a record locally (api.narrate)
  /list [records|topologies|sessions|applications]  list resources
  /replay <record>            replay a record locally (api.assert_replayable)
  /run <app> [args]           run an application topology as a sibling
  /help                       print this list
"""


def _slash_route(
    line: str,
    session: dict[str, Any],
    pending_context: dict[str, Any],
) -> bool:
    """Route one input line. Returns True if the line was a slash the router
    handled (and the REPL should skip the daemon.turn call); False if not a
    slash or an unknown slash (the REPL treats it as user text). `/exit` is
    the ONLY slash the router does NOT swallow — it returns False so the REPL
    sends the literal `"/exit"` string as a UserMessage; the daemon's
    end-on-exit trigger fires the SessionEnded{user_exit}.

    `pending_context` is the mutable dict the REPL keeps across turns; a
    `/context` slash stores here and the next `/turn` call reads + clears it.
    """
    from substrate import _daemon

    stripped = line.strip()
    if not stripped.startswith("/"):
        return False

    parts = stripped.split()
    slash = parts[0]
    args = parts[1:]
    sid = str(session["session_id"])

    if slash == SlashCommand.EXIT:
        # Only slash the model observes: return False so the REPL sends it
        # as a UserMessage. The daemon's `end-on-exit` trigger routes it
        # to SessionEnded{user_exit}.
        return False

    if slash == SlashCommand.HELP:
        _err.print(_SLASH_HELP)
        return True

    if slash == SlashCommand.MODEL:
        if len(args) != 1:
            _err.print("[repl] /model requires exactly one driver name")
            return True
        try:
            _daemon.patch_session(sid, driver=args[0])
            _err.print(f"[repl] driver → {args[0]} (next turn)")
        except _daemon.DaemonError as exc:
            _err.print(f"[repl] /model failed: HTTP {exc.status}: {exc.body}")
        return True

    if slash == SlashCommand.TOOLS:
        if len(args) != 1:
            _err.print(
                "[repl] /tools requires a comma-separated list, e.g. `/tools read_file,grep`"
            )
            return True
        tool_list = [t.strip() for t in args[0].split(",") if t.strip()]
        try:
            _daemon.patch_session(sid, tools=tool_list)
            _err.print(f"[repl] tools → {tool_list} (next turn)")
        except _daemon.DaemonError as exc:
            _err.print(f"[repl] /tools failed: HTTP {exc.status}: {exc.body}")
        return True

    if slash == SlashCommand.CONTEXT:
        if not args:
            _err.print("[repl] /context <lo-hi> [--kind K]")
            return True
        try:
            lo_hi = args[0]
            if "-" not in lo_hi:
                raise ValueError("range must be <lo>-<hi>")
            lo_s, hi_s = lo_hi.split("-", 1)
            lo, hi = int(lo_s), int(hi_s)
        except ValueError as exc:
            _err.print(f"[repl] /context range parse failed: {exc}")
            return True
        kinds: list[str] = []
        if "--kind" in args:
            i = args.index("--kind")
            if i + 1 < len(args):
                kinds = [args[i + 1]]
        pending_context.clear()
        pending_context["parent_seq_range"] = [lo, hi]
        pending_context["kinds"] = kinds
        _err.print(f"[repl] context pending: seq {lo}..{hi}" + (f" kinds={kinds}" if kinds else ""))
        return True

    if slash == SlashCommand.INSPECT:
        if not args:
            _err.print("[repl] /inspect <record-path>")
            return True
        try:
            record_path = Path(args[0])
            for line_out in api.narrate(api.read_record(record_path)):
                _err.print(str(line_out))
        except Exception as exc:  # noqa: BLE001 — surface as a repl message
            _err.print(f"[repl] /inspect failed: {type(exc).__name__}: {exc}")
        return True

    if slash == SlashCommand.LIST:
        raw_target = args[0] if args else ListTarget.SESSIONS.value
        try:
            target = ListTarget(raw_target)
        except ValueError:
            _err.print(
                f"[repl] /list {raw_target}: unknown target; "
                f"valid targets: {[t.value for t in ListTarget]}"
            )
            return True
        if target is ListTarget.SESSIONS:
            try:
                data = _daemon.list_sessions()
                for bucket, entries in data.items():
                    for entry in entries:
                        _err.print(
                            f"[{bucket}] {entry.get('name') or entry['session_id']} "
                            f"({entry['driver']})"
                        )
            except _daemon.DaemonError as exc:
                _err.print(f"[repl] /list failed: HTTP {exc.status}")
        elif target is ListTarget.TOPOLOGIES:
            # Dynamic import: F-API-6 checks STATIC substrate imports, so a
            # runtime `importlib.import_module` call is not a violation. The
            # bundled registry is optional; if it fails, list what is
            # already registered via `api.get_topology`'s registry side.
            try:
                bundled_mod = importlib.import_module("substrate.topologies.bundled")
                names = getattr(bundled_mod, "names", None)
                if callable(names):
                    for n in names():
                        _err.print(n)
                else:
                    _err.print("[repl] /list topologies: bundled registry has no names()")
            except Exception as exc:  # noqa: BLE001 — importlib on a caller-supplied bundle path can raise anything the bundle's __init__ does; the router's job is to surface, not classify.
                _err.print(f"[repl] /list topologies failed: {type(exc).__name__}: {exc}")
        elif target is ListTarget.RECORDS:
            _err.print("[repl] /list records — reads the record dir; not implemented yet")
        elif target is ListTarget.APPLICATIONS:
            _err.print(
                "[repl] /list applications — GET /api/applications is a piece-E endpoint; "
                "not yet shipped"
            )
        # No else — ListTarget's four members exhaust the space; validator
        # above rejects any other argv value at the boundary.
        return True

    if slash == SlashCommand.REPLAY:
        if not args:
            _err.print("[repl] /replay <record-path>")
            return True
        try:
            api.assert_replayable(Path(args[0]), "3a")
            _err.print(f"[repl] {args[0]}: byte-identical replay at Level-3(a)")
        except Exception as exc:  # noqa: BLE001 — api.assert_replayable raises AssertionError, RecordGapError, CRCMismatchError, or any I/O error; the router surfaces the class name to the REPL.
            _err.print(f"[repl] /replay failed: {type(exc).__name__}: {exc}")
        return True

    if slash == SlashCommand.RUN:
        # Drift-grooming 2026-09-02: the earlier "typed marker" pattern set
        # pending_context["_deferred"] = "run"; no downstream reader consumed
        # it, but the next real turn's context body carried the marker into
        # `_daemon.turn(..., context={"_deferred": "run"})`, which
        # substrate-ui's `_session_turn` refused with 400 for the missing
        # parent_seq_range. The marker + refusal reached the user as a
        # cryptic HTTP 400 on the next unrelated message. The stderr hint
        # is the whole feature until piece E's POST /api/topology/<name>/run
        # ships a real endpoint.
        _err.print(
            "[repl] /run — POST /api/topology/<name>/run is a piece-E endpoint; not yet shipped."
        )
        return True

    _err.print(f"[repl] unknown slash: {slash}. Try /help.")
    return True


def _repl(session: dict[str, Any], *, verbose: bool = False) -> None:
    """The chat REPL. Main thread blocks on stdin; SSE thread streams events
    to stderr as they land.

    Sprint 220 wires:
      - SIGINT during a turn → POST /interrupt. SIGINT idle → hint + continue.
      - Ctrl+D (EOF) → POST /end{source=user_end}; session ends; REPL exits.
      - SIGHUP → exit clean; session stays parked (POSTs nothing).
      - `SUBSTRATE_SESSION` env var set before every /turn so the daemon's
        bash-tool subprocesses inherit the session identity.
    """
    import os as _os
    import signal as _signal
    import threading as _threading

    from substrate import _daemon

    sid = str(session["session_id"])
    label = str(session.get("name") or sid)
    stop_event = _threading.Event()
    stream_thread = _threading.Thread(
        target=_sse_stream, args=(sid, stop_event), kwargs={"verbose": verbose}, daemon=True
    )
    stream_thread.start()

    # Sprint 220: SIGINT dispatch depends on whether a turn is in flight.
    turn_in_flight = _threading.Event()

    def _sigint_handler(_signum: int, _frame: Any) -> None:
        if turn_in_flight.is_set():
            try:
                _daemon.interrupt(sid, max_wait_ms=3000)
            except _daemon.DaemonError as exc:
                _err.print(f"[repl] interrupt failed: HTTP {exc.status}: {exc.body}")
            except _daemon.DaemonNotRunning as exc:
                _err.print(f"[repl] daemon unreachable: {exc}")
        else:
            _err.print("(no turn in flight; type /exit or press Ctrl+D to end)")

    def _sighup_handler(_signum: int, _frame: Any) -> None:
        # SIGHUP: exit cleanly. Session stays parked; the daemon keeps holding
        # its manifest at "parked" and every follow-up `substrate resume <name>`
        # continues where the REPL left off.
        stop_event.set()
        _err.print(f"[repl] SIGHUP; {label} stays parked")
        raise SystemExit(EXIT_OK)

    _signal.signal(_signal.SIGINT, _sigint_handler)
    if hasattr(_signal, "SIGHUP"):
        _signal.signal(_signal.SIGHUP, _sighup_handler)

    # Sprint 220: expose the session identity to child subprocesses (bash tool,
    # etc.). The daemon's bash tool inherits the parent env by subprocess.run
    # default; setting the var here is enough.
    _os.environ["SUBSTRATE_SESSION"] = label

    # Sprint 221: `/context` stores a slice request here; the next /turn
    # reads + clears it. Kept across turns so a client can queue several
    # context slices, one per turn, without re-typing.
    pending_context: dict[str, Any] = {}

    try:
        while True:
            try:
                line = _readline_with_interrupt("> ")
            except EOFError:
                # Ctrl+D → end the session cleanly.
                try:
                    _daemon.end_session(sid, source="user_end")
                except _daemon.DaemonError as exc:
                    _err.print(f"[repl] end failed: HTTP {exc.status}: {exc.body}")
                except _daemon.DaemonNotRunning as exc:
                    _err.print(f"[repl] daemon unreachable at end: {exc}")
                break
            except KeyboardInterrupt:
                # The signal handler already ran; loop and read the next line.
                continue
            if not line.strip():
                continue
            # Sprint 221: route slashes locally. True → the router handled it;
            # False → send the line as a UserMessage (also the /exit path,
            # so the daemon's end-on-exit trigger fires SessionEnded{user_exit}).
            if _slash_route(line, session, pending_context):
                continue
            turn_context = pending_context.copy() if pending_context else None
            pending_context.clear()
            turn_in_flight.set()
            try:
                result = _daemon.turn(sid, line, context=turn_context)
            except _daemon.DaemonError as exc:
                _err.print(f"[repl] turn failed: HTTP {exc.status}: {exc.body}")
                turn_in_flight.clear()
                continue
            except _daemon.DaemonNotRunning as exc:
                _err.print(f"[repl] daemon unreachable: {exc}")
                break
            finally:
                turn_in_flight.clear()
            status = result.get("status")
            if status == api.SessionStatus.ENDED:
                break
    finally:
        stop_event.set()


@main.command()
@click.argument("driver", required=False)
@click.option("--name", default=None, help="name for the standing session (optional)")
@click.option("--workspace", default=None, help="workspace path (overrides config default)")
@click.option("--seed", default=None, help="seed_text for the first turn (optional)")
@click.option(
    "--verbose",
    is_flag=True,
    help="stream substrate.* lifecycle events too (default: application events only)",
)
def chat(
    driver: str | None,
    name: str | None,
    workspace: str | None,
    seed: str | None,
    verbose: bool = False,
) -> None:
    """Open a session against the daemon and drive it from a REPL. Reads
    defaults from `~/.substrate/config.toml [defaults]` for any option not
    passed. Piece D: sprint 218 shipped the create step; sprint 219 wires
    the REPL + SSE streaming."""
    from substrate import _daemon

    defaults = _defaults()
    driver = driver or defaults["driver"]
    workspace_val = workspace or defaults["workspace"]
    _ensure_daemon_running()
    try:
        session = _daemon.create_session(
            driver=driver,
            name=name,
            workspace=workspace_val,
            seed_text=seed,
        )
    except _daemon.DaemonError as exc:
        _err.print(f"[config] create session failed: HTTP {exc.status}: {exc.body}")
        raise SystemExit(EXIT_CONFIG) from exc
    except _daemon.DaemonNotRunning as exc:
        _err.print(f"[config] daemon unreachable after auto-launch: {exc}")
        raise SystemExit(EXIT_CONFIG) from exc
    click.echo(session["session_id"])
    label = session.get("name") or session["session_id"]
    _err.print(f"[session] {label} record={session['record']}")
    _repl(session, verbose=verbose)


@main.command()
@click.option("--foreground", is_flag=True, help="run the daemon in the foreground (blocks)")
def daemon(foreground: bool) -> None:
    """Start the substrate daemon. Reads `[daemon] server_path` from
    `~/.substrate/config.toml` for the executable path. `--foreground`
    execs into the daemon process; without it, the CLI double-forks and
    exits after the child is up.
    """
    server_path = _daemon_server_path()
    if not server_path:
        _err.print(
            f"[config] [daemon] server_path not set in {_config_path_default()}; "
            "set it to the absolute path of substrate-ui/server.py"
        )
        raise SystemExit(EXIT_CONFIG)
    if not Path(server_path).exists():
        _err.print(f"[config] [daemon] server_path {server_path!r} does not exist")
        raise SystemExit(EXIT_CONFIG)
    if foreground:
        import os as _os

        _os.execv(sys.executable, [sys.executable, server_path])
    _double_fork_daemon(server_path)
    _err.print(f"[daemon] launched {server_path}")


# ── piece D sprint 222: session / bundle / builder subverbs ─────────────


_RECENT_ACTIVE_SECONDS = 24 * 60 * 60  # `session rm` --force threshold


def _resolve_session(name_or_id: str) -> dict[str, Any]:
    """Resolve a `<name>` or `<session_id>` to a session dict from the daemon.

    Session ids start with `s_`; anything else routes through the by-name
    index. Raises SystemExit(EXIT_CONFIG) with a message if the name misses
    or the daemon is unreachable.
    """
    from substrate import _daemon

    try:
        if name_or_id.startswith("s_"):
            return {"session_id": name_or_id}
        record = _daemon.by_name(name_or_id)
        if record is None:
            _err.print(f"[config] no session named {name_or_id!r}")
            raise SystemExit(EXIT_CONFIG)
        return record
    except _daemon.DaemonNotRunning as exc:
        _err.print(f"[config] daemon unreachable: {exc}")
        raise SystemExit(EXIT_CONFIG) from exc


@main.group("session")
def session_group() -> None:
    """Session-scoped subverbs: `ls`, `end`, `rm`, `set-name`."""


@session_group.command("ls")
def session_ls() -> None:
    """List every session bucketed by status. One row per session."""
    from substrate import _daemon

    try:
        buckets = _daemon.list_sessions()
    except _daemon.DaemonNotRunning as exc:
        _err.print(f"[config] daemon unreachable: {exc}")
        raise SystemExit(EXIT_CONFIG) from exc
    header = f"{'name':<24} {'session_id':<28} {'driver':<20} {'status':<12} {'shape':<10}"
    click.echo(header)
    click.echo("-" * len(header))
    import time as _time

    now = _time.time()
    for bucket_name in ("live", "parked", "interrupted", "ended"):
        for entry in buckets.get(bucket_name, []):
            elapsed = int(now - float(entry.get("created_at", now)))
            row = (
                f"{(entry.get('name') or '-')!s:<24} "
                f"{entry['session_id']:<28} "
                f"{entry.get('driver', '-'):<20} "
                f"{bucket_name:<12} "
                f"{entry.get('workspace_shape', '-'):<10} "
                f"{elapsed}s ago"
            )
            click.echo(row)


@session_group.command("end")
@click.argument("name_or_id")
def session_end(name_or_id: str) -> None:
    """End a session — inject SessionEndRequested{user_end} via POST /end."""
    from substrate import _daemon

    resolved = _resolve_session(name_or_id)
    sid = resolved["session_id"]
    try:
        _daemon.end_session(sid, source="user_end")
        _err.print(f"[session] {name_or_id} ended")
    except _daemon.DaemonError as exc:
        _err.print(f"[session] end failed: HTTP {exc.status}: {exc.body}")
        raise SystemExit(EXIT_FAILED) from exc


@session_group.command("rm")
@click.argument("name_or_id")
@click.option("--force", is_flag=True, help="Delete even if session was active in the last 24h.")
def session_rm(name_or_id: str, force: bool) -> None:
    """Delete a session (`DELETE /api/session/<id>`).

    Refuses if the session's `created_at` is within the last 24 hours
    without `--force`. Rule 12 preserves the record dir on disk; only
    the manifest + by-name entry are dropped.
    """
    import time as _time

    from substrate import _daemon

    resolved = _resolve_session(name_or_id)
    sid = resolved["session_id"]
    if not force:
        try:
            buckets = _daemon.list_sessions()
        except _daemon.DaemonNotRunning as exc:
            _err.print(f"[config] daemon unreachable: {exc}")
            raise SystemExit(EXIT_CONFIG) from exc
        created_at: float | None = None
        for entries in buckets.values():
            for entry in entries:
                if entry["session_id"] == sid:
                    created_at = float(entry.get("created_at", 0.0))
                    break
            if created_at is not None:
                break
        if created_at is not None and _time.time() - created_at < _RECENT_ACTIVE_SECONDS:
            hours = int((_time.time() - created_at) / 3600)
            _err.print(
                f"[session] {name_or_id} was active {hours}h ago (< 24h). "
                f"Pass --force to delete anyway."
            )
            raise SystemExit(EXIT_CONFIG)
    try:
        _daemon.delete_session(sid)
        _err.print(f"[session] {name_or_id} removed (record dir preserved on disk)")
    except _daemon.DaemonError as exc:
        _err.print(f"[session] rm failed: HTTP {exc.status}: {exc.body}")
        raise SystemExit(EXIT_FAILED) from exc


@session_group.command("set-name")
@click.argument("session_id")
@click.argument("new_name")
def session_set_name(session_id: str, new_name: str) -> None:
    """Rename a session in the by-name.json index (PATCH /api/session/<id>)."""
    from substrate import _daemon

    try:
        _daemon.patch_session(session_id, name=new_name)
        _err.print(f"[session] {session_id} renamed to {new_name}")
    except _daemon.DaemonError as exc:
        _err.print(f"[session] rename failed: HTTP {exc.status}: {exc.body}")
        raise SystemExit(EXIT_FAILED) from exc


# ── bundle subverbs (CLI-side filesystem only; piece H owns the loader) ──


def _bundles_root_cli() -> Path:
    from substrate.api import substrate_home

    return substrate_home() / "bundles"


_BUNDLE_TEMPLATE_TOML = """# bundle.toml — see the tech spec for slot semantics.

name = "{name}"
description = ""
schema_version = 1
extends = []

[tools]
enabled = []
"""

_BUNDLE_SLOTS = ("methodology.md", "personality.md", "per-turn.md")


@main.group("bundle")
def bundle_group() -> None:
    """Bundle scaffolding subverbs: `create`, `ls`, `show`, `edit`.

    Piece H (sprint 229) ships `bundles.py` with the real loader; these
    subverbs are CLI-side filesystem operations only. `create` writes a
    valid directory skeleton the piece-H loader will accept.
    """


@bundle_group.command("create")
@click.argument("name")
@click.option(
    "--wizard",
    "template",
    default=None,
    is_flag=False,
    flag_value="default",
    help="Fill the bundle by walking a template. Bare --wizard uses `default`; "
    "--wizard=<name> picks a specific template under substrate/templates/bundles/.",
)
def bundle_create(name: str, template: str | None) -> None:
    """Scaffold `~/.substrate/bundles/<name>/`.

    Bare: writes empty slot files (methodology.md, personality.md,
    per-turn.md) + bundle.toml + corpus/.
    --wizard[=<template>]: walks the named template's slots via
    click.prompt, interpolates the answers, writes the rendered
    bundle.toml + prose files (sprint 232).
    """
    target = _bundles_root_cli() / name
    if target.exists():
        _err.print(f"[bundle] {target} already exists")
        raise SystemExit(EXIT_CONFIG)
    target.mkdir(parents=True)
    (target / "corpus").mkdir()
    if template is None:
        for slot in _BUNDLE_SLOTS:
            (target / slot).write_text("", encoding="utf-8")
        (target / "bundle.toml").write_text(
            _BUNDLE_TEMPLATE_TOML.format(name=name), encoding="utf-8"
        )
        _err.print(f"[bundle] scaffolded {target}")
        return
    _run_bundle_wizard(name, target, template)


def _run_bundle_wizard(name: str, target: Path, template_name: str) -> None:
    """Sprint 232 — walk a template's slots via click.prompt, interpolate
    the answers, write the rendered file sections out of the template
    body. The template body uses `== <filename> ==` headers to demarcate
    which slice writes to which slot file — one template renders four
    files."""
    # Dynamic import: F-API-6 checks STATIC substrate imports; the
    # importlib.import_module call is a runtime lookup and passes the
    # cli-imports-only-api contract (same pattern as _load_topology's
    # bundled-registry hook).
    interpolate_mod = importlib.import_module("substrate.templates.interpolate")
    parse_template_header = interpolate_mod.parse_template_header
    render = interpolate_mod.render

    template_path = Path(__file__).parent / "templates" / "bundles" / f"{template_name}.tmpl.md"
    if not template_path.is_file():
        _err.print(f"[bundle] no template at {template_path}")
        raise SystemExit(EXIT_CONFIG)
    source = template_path.read_text(encoding="utf-8")
    header, body = parse_template_header(source)

    values: dict[str, str | bool] = {"name": name}
    for slot in header["slots"]:
        slot_name = str(slot["name"])
        kind = str(slot.get("kind", "text_line"))
        prompt = str(slot.get("prompt", slot_name))
        if kind == "bool":
            values[slot_name] = click.confirm(prompt, default=False)
        elif kind == "pick":
            choices = list(slot.get("choices") or [])
            answer = click.prompt(
                prompt,
                type=click.Choice(choices) if choices else str,
                default=choices[0] if choices else "",
            )
            values[slot_name] = str(answer)
        else:
            values[slot_name] = click.prompt(prompt, default="", show_default=False)

    rendered = render(body, values)
    _write_rendered_bundle(target, rendered)
    _err.print(f"[bundle] wizard wrote {target} from template {template_name!r}")


def _write_rendered_bundle(target: Path, rendered: str) -> None:
    """Parse `== <filename> ==` headers in the rendered body; write each
    slice to the named file under `target`. Any content before the
    first header is discarded (it lives before any file's home)."""
    file_map = {
        "bundle.toml": "bundle.toml",
        "methodology.md": "methodology.md",
        "personality.md": "personality.md",
        "per-turn.md": "per-turn.md",
    }
    current: str | None = None
    buffers: dict[str, list[str]] = {name: [] for name in file_map}
    for line in rendered.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("== ") and stripped.endswith(" =="):
            header_name = stripped[3:-3].strip()
            current = file_map.get(header_name)
            continue
        if current is not None:
            buffers[current].append(line)
    for filename, lines in buffers.items():
        text = "".join(lines).strip("\n") + "\n" if lines else ""
        (target / filename).write_text(text, encoding="utf-8")


@bundle_group.command("ls")
def bundle_ls() -> None:
    """List directories under `~/.substrate/bundles/`."""
    if not _bundles_root_cli().exists():
        return
    for entry in sorted(_bundles_root_cli().iterdir()):
        if entry.is_dir():
            click.echo(entry.name)


@bundle_group.command("show")
@click.argument("name")
def bundle_show(name: str) -> None:
    """Print bundle.toml + methodology + corpus tree for a bundle."""
    target = _bundles_root_cli() / name
    if not target.exists():
        _err.print(f"[bundle] no bundle named {name!r} at {target}")
        raise SystemExit(EXIT_CONFIG)
    click.echo(f"# {target}")
    click.echo()
    for slot in ("bundle.toml", *_BUNDLE_SLOTS):
        path = target / slot
        if path.is_file():
            click.echo(f"── {slot} ──")
            click.echo(path.read_text(encoding="utf-8").rstrip())
            click.echo()
    corpus = target / "corpus"
    if corpus.is_dir():
        click.echo("── corpus ──")
        for path in sorted(corpus.rglob("*")):
            if path.is_file():
                click.echo(f"  {path.relative_to(target)}")


@bundle_group.command("edit")
@click.argument("name")
def bundle_edit(name: str) -> None:
    """Open the bundle dir in $EDITOR."""
    import os as _os
    import subprocess

    target = _bundles_root_cli() / name
    if not target.exists():
        _err.print(f"[bundle] no bundle named {name!r} at {target}")
        raise SystemExit(EXIT_CONFIG)
    editor = _os.environ.get("EDITOR", "vi")
    subprocess.run([editor, str(target)], check=False)


# ── builder verb: open the studio in a browser ──────────────────────────


@main.command("builder")
def builder() -> None:
    """Open the substrate studio in the default browser.

    Looks for `~/.substrate/studio.html` first; if absent, prints the URL
    the running daemon serves at `/studio.html` (piece G ships the file).
    """
    import subprocess
    import sys as _sys

    from substrate.api import substrate_home

    studio = substrate_home() / "studio.html"
    if studio.exists():
        opener = "open" if _sys.platform == "darwin" else "xdg-open"
        subprocess.run([opener, str(studio)], check=False)
        _err.print(f"[builder] opened {studio}")
        return
    from substrate import _daemon

    try:
        _host, _port = _daemon._tcp_host_port()
        _err.print(
            f"[builder] no {studio} on disk; if the daemon is running, "
            f"open http://{_host}:{_port}/studio.html in your browser"
        )
    except Exception:  # noqa: BLE001 — env-var read for daemon TCP tuple; any failure means no daemon config.
        _err.print(f"[builder] no {studio} on disk; start the daemon and open /studio.html")


if __name__ == "__main__":
    main()

# spec-audit: 2026-09-01
