# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""CLI tests (design §5; F-CLI-1..6, F-API-6).

Two jobs: (1) ENFORCE F-API-6 — `substrate.cli` may import only `substrate.api` among
substrate modules (the CLI is the standing existence proof that the public API suffices;
this is the import-lint rule PHASE1_PLAN S-0.INT calls for, run here under pytest with no
extra dependency). (2) Smoke-test the commands end-to-end over a real run record via Click's
CliRunner, asserting the documented output shapes + exit codes (§5.1)."""

import ast
from pathlib import Path

from click.testing import CliRunner
from msgspec import Struct

from substrate.api import Runtime, register_topology, threshold_count
from substrate.cli import (
    EXIT_CONFIG,
    EXIT_FAILED,
    EXIT_OK,
    EXIT_PAUSED,
    main,
)

# A pause/resume topology written to a temp module so the CLI resolves it (and the resume
# event factory) via `path/to/module.py:func` — the documented resume invocation (F-CLI).
_PAUSE_RESUME_MODULE = """
from msgspec import Struct
from substrate.api import (
    PerEvent, Subscription, any_of, pause_await_input, quiescence,
)


class S1(Struct, frozen=True):
    pass


class S2(Struct, frozen=True):
    pass


class Approve(Struct, frozen=True):
    ok: bool


async def s1(_i):
    yield S1()


async def s2(_i):
    yield S2()


def _pause_when(ctx):
    return ctx.counts("S1") >= 1 and ctx.counts("Approve") == 0


def topo(b):
    b.producer_kind("s1", schemas=[S1], schema_version=1, factory=lambda: s1)
    b.producer_kind("s2", schemas=[S2], schema_version=1, factory=lambda: s2)
    b.initial("s1", input=None)
    b.trigger(
        "on-approve",
        subscription=Subscription(kinds=frozenset({"Approve"})),
        predicate=lambda ctx: bool(ctx.event.payload.get("ok")),
        starts="s2",
        input_builder=lambda ctx: None,
        policy=PerEvent(),
    )
    b.termination(
        any_of(
            pause_await_input(_pause_when, resume_condition="Approve"),
            quiescence(),
        )
    )


def approve():
    return Approve(ok=True)
"""


def test_cli_resume_continues_paused_run(tmp_path):
    # Pause via the CLI, then resume via the CLI in a fresh process-like invocation.
    mod = tmp_path / "pr.py"
    mod.write_text(_PAUSE_RESUME_MODULE)
    root = tmp_path / "run"
    runner = CliRunner()

    paused = runner.invoke(
        main, ["run", "--topology-module", f"{mod}:topo", "--root", str(root), "--persistent"]
    )
    assert paused.exit_code == EXIT_PAUSED, paused.output

    resumed = runner.invoke(
        main,
        [
            "resume",
            str(root),
            "--topology-module",
            f"{mod}:topo",
            "--input",
            f"{mod}:approve",
        ],
    )
    assert resumed.exit_code == EXIT_OK, resumed.output
    assert str(root) in resumed.stdout

    from substrate.api import read_record

    kinds = [e["kind"] for e in read_record(root)]
    assert "Approve" in kinds and "S2" in kinds and "substrate.RunFinalised" in kinds
    seqs = [e["seq"] for e in read_record(root)]
    assert seqs == list(range(len(seqs)))  # continuous seq across the pause boundary


def test_cli_resume_requires_input(tmp_path):
    mod = tmp_path / "pr.py"
    mod.write_text(_PAUSE_RESUME_MODULE)
    root = tmp_path / "run"
    runner = CliRunner()
    runner.invoke(
        main, ["run", "--topology-module", f"{mod}:topo", "--root", str(root), "--persistent"]
    )
    # --input is required (the external resume event); omitting it is a usage error.
    res = runner.invoke(main, ["resume", str(root), "--topology-module", f"{mod}:topo"])
    assert res.exit_code != EXIT_OK


def test_api_exposes_exception_hierarchy_by_type():
    # F-API-6 completeness: an api-only consumer (the CLI is the standing proof) must handle
    # errors BY TYPE, not by string-matching class names. The public exception hierarchy is
    # re-exported and rooted at SubstrateError.
    import substrate.api as api

    for name in (
        "SubstrateError",
        "BusLockedError",
        "RegistrationError",
        "UnsupportedPlatformError",
        "FsyncError",
        "ProducerNotFound",
        "SequenceOutOfRange",
        "InputTypeError",
        # handshake #4 FIX 5: the replay catch-surface (replay/assert_replayable raise these)
        "ReplayError",
        "RecordIncompleteError",
    ):
        assert name in api.__all__, f"{name} missing from api.__all__"
        cls = getattr(api, name)
        assert isinstance(cls, type)
        if name != "SubstrateError":
            assert issubclass(cls, api.SubstrateError), f"{name} not under SubstrateError"


# ── F-API-6: the CLI imports only substrate.api among substrate modules ────────
# Piece D sprint 218 added `substrate._daemon` — a thin HTTP client for the
# substrate-ui daemon. F-API-6's intent is that the CLI cannot reach kernel /
# record / projections internals; `_daemon` touches none of those (it uses
# stdlib http.client + socket only). The exception is explicit and audited:
# any addition here needs its own rationale.
_CLI_ALLOWED_SUBSTRATE_IMPORTS: frozenset[str] = frozenset(
    {
        "api",  # the kernel's facade
        "app",  # the application facade: sessions, the daemon client, bundled topologies
    }
)


def test_cli_imports_only_substrate_api():
    cli_path = Path(__file__).parent.parent / "src" / "substrate" / "cli.py"
    tree = ast.parse(cli_path.read_text())
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "substrate":
                # `from substrate import api` — or one of the audited allowances
                names = {a.name for a in node.names}
                bad = names - _CLI_ALLOWED_SUBSTRATE_IMPORTS
                if bad:
                    offenders.append(f"from substrate import {sorted(bad)}")
            elif mod.startswith("substrate."):
                # `from substrate.<sub> import ...` — only substrate.api or an
                # audited sub-module is allowed.
                sub = mod.split(".", 1)[1].split(".", 1)[0]
                if sub not in _CLI_ALLOWED_SUBSTRATE_IMPORTS:
                    offenders.append(f"from {mod} import ...")
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("substrate."):
                    sub = a.name.split(".", 1)[1].split(".", 1)[0]
                    if sub not in _CLI_ALLOWED_SUBSTRATE_IMPORTS:
                        offenders.append(f"import {a.name}")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and str(node.args[0].value).startswith("substrate")
        ):
            # A string import is an import (lens audit F061: the CLI reached topologies through
            # importlib.import_module, with a comment saying it did so to pass this contract).
            offenders.append(f"importlib.import_module({node.args[0].value!r})")
    assert not offenders, f"cli.py imports non-api substrate modules (F-API-6): {offenders}"


# ── end-to-end smoke over a real record ────────────────────────────────────────
class CountReached(Struct, frozen=True):
    n: int


async def counter(_input):
    for n in range(1, 4):
        yield CountReached(n=n)


def _topo(b):
    b.producer_kind("counter", schemas=[CountReached], schema_version=1, factory=lambda: counter)
    b.initial("counter", input=None)
    b.termination(threshold_count("substrate.ProducerCompleted", 1))


def _run_record(tmp_path):
    import asyncio

    root = tmp_path / "run"
    asyncio.run(Runtime(root).run(_topo))
    return root


def test_run_via_registry_prints_root_and_exits_zero(tmp_path):
    register_topology("cli_count", _topo)
    runner = CliRunner()
    root = tmp_path / "out"
    res = runner.invoke(main, ["run", "--topology", "cli_count", "--root", str(root)])
    assert res.exit_code == EXIT_OK
    assert str(root) in res.stdout  # the record root is the load-bearing stdout line


def test_run_missing_topology_is_config_error(tmp_path):
    runner = CliRunner()
    res = runner.invoke(main, ["run", "--root", str(tmp_path / "x")])
    assert res.exit_code == EXIT_CONFIG


def test_run_prints_root_on_config_error_when_root_known(tmp_path):
    # design §5.1: the record root is printed on every exit that contemplates a run — incl.
    # a topology-load failure (a known root, no record created).
    runner = CliRunner()
    root = tmp_path / "out"
    res = runner.invoke(
        main, ["run", "--topology-module", str(tmp_path / "nope.py") + ":x", "--root", str(root)]
    )
    assert res.exit_code == EXIT_CONFIG
    assert str(root) in res.stdout


def test_run_topology_module_import_failure_is_clean_config_error(tmp_path):
    # A --topology-module whose import RAISES (here a NameError at module scope) must surface as
    # EXIT_CONFIG with a clean message, NOT a raw traceback escaping the CLI.
    bad = tmp_path / "bad.py"
    bad.write_text("this_name_is_not_defined\n")  # NameError on import
    runner = CliRunner()
    root = tmp_path / "out"
    res = runner.invoke(main, ["run", "--topology-module", f"{bad}:topo", "--root", str(root)])
    assert res.exit_code == EXIT_CONFIG
    assert "failed to import" in res.stderr
    assert "NameError" in res.stderr
    assert "Traceback" not in res.stderr  # the raw traceback did not escape


def test_run_topology_module_with_future_annotations_and_dataclass(tmp_path):
    # C-16: a user module combining `from __future__ import annotations` with a @dataclass used to die
    # on import — dataclass reads the module's globals via sys.modules[cls.__module__], which was None
    # because the file-loaded module was never registered. The loader now registers it before exec.
    mod = tmp_path / "user_topo.py"
    mod.write_text(
        "from __future__ import annotations\n"
        "from dataclasses import dataclass\n"
        "from msgspec import Struct\n"
        "from substrate.api import TopologyBuilder, threshold_count\n"
        "class Ping(Struct, frozen=True):\n    n: int\n"
        "@dataclass\nclass Config:\n    reps: int = 3\n"
        "async def pinger(_i):\n    yield Ping(n=1)\n"
        "def topo(b: TopologyBuilder) -> None:\n"
        "    b.producer_kind('pinger', schemas=[Ping], schema_version=1, factory=lambda: pinger)\n"
        "    b.initial('pinger', input=None)\n"
        "    b.termination(threshold_count('substrate.ProducerCompleted', 1))\n"
    )
    root = tmp_path / "out"
    res = CliRunner().invoke(main, ["run", "--topology-module", f"{mod}:topo", "--root", str(root)])
    assert res.exit_code == EXIT_OK, res.stderr
    assert root.exists()


def test_run_tail_streams_events(tmp_path):
    register_topology("cli_count_tail", _topo)
    runner = CliRunner()
    root = tmp_path / "out"
    res = runner.invoke(
        main, ["run", "--topology", "cli_count_tail", "--root", str(root), "--tail"]
    )
    assert res.exit_code == EXIT_OK
    assert str(root) in res.stdout  # data on stdout
    # --tail streams application events to stderr (default: no substrate.* without --verbose)
    assert "CountReached" in res.stderr


def test_run_tail_verbose_includes_lifecycle(tmp_path):
    register_topology("cli_count_tailv", _topo)
    runner = CliRunner()
    root = tmp_path / "out"
    res = runner.invoke(
        main,
        ["run", "--topology", "cli_count_tailv", "--root", str(root), "--tail", "--verbose"],
    )
    assert res.exit_code == EXIT_OK
    assert "substrate.RunFinalised" in res.stderr  # lifecycle streamed with --verbose


def test_tail_aligned_and_jsonl(tmp_path):
    root = _run_record(tmp_path)
    runner = CliRunner()
    aligned = runner.invoke(main, ["tail", str(root)])
    assert aligned.exit_code == 0
    assert "seq=0" in aligned.stdout and "substrate.RunStarted" in aligned.stdout
    assert "CountReached" in aligned.stdout
    jsonl = runner.invoke(main, ["tail", str(root), "--format", "jsonl"])
    assert '"kind":"substrate.RunStarted"' in jsonl.stdout.replace(" ", "")


def test_tail_filters_compose(tmp_path):
    root = _run_record(tmp_path)
    runner = CliRunner()
    res = runner.invoke(main, ["tail", str(root), "--kind", "CountReached"])
    assert res.exit_code == 0
    lines = [ln for ln in res.stdout.splitlines() if ln.strip()]
    assert lines and all("CountReached" in ln for ln in lines)


def test_inspect_why_cites_seq(tmp_path):
    root = _run_record(tmp_path)
    # find the counter instance
    from substrate.api import read_record

    started = next(e for e in read_record(root) if e["kind"] == "substrate.ProducerStarted")
    inst = started["payload"]["producer"]["instance"]
    runner = CliRunner()
    res = runner.invoke(main, ["inspect", str(root), "--producer", f"counter[{inst}]", "--why"])
    assert res.exit_code == 0
    assert "caused_by:" in res.stdout
    assert "RunStarted" in res.stdout  # initial producer attributes to the run open


def test_replay_level2_ok(tmp_path):
    root = _run_record(tmp_path)
    runner = CliRunner()
    res = runner.invoke(main, ["replay", str(root), "--level", "2"])
    assert res.exit_code == 0
    assert "[OK] Level 2 replay successful." in res.stdout


def test_replay_level3b_is_deferred_not_silent(tmp_path):
    root = _run_record(tmp_path)
    runner = CliRunner()
    res = runner.invoke(main, ["replay", str(root), "--level", "3b"])
    # deferred surfaces as a non-zero exit with a [deferred] message, never a false green
    assert res.exit_code != 0
    assert "deferred" in (res.stdout + res.stderr).lower()


def test_validate_module(tmp_path):
    # write a tiny topology module and validate it via the path:func form
    mod = tmp_path / "topo.py"
    mod.write_text(
        "from msgspec import Struct\n"
        "from substrate.api import threshold_count\n"
        "class E(Struct, frozen=True):\n    n: int\n"
        "async def p(_):\n    yield E(n=1)\n"
        "def topo(b):\n"
        "    b.producer_kind('p', schemas=[E], schema_version=1, factory=lambda: p)\n"
        "    b.initial('p', input=None)\n"
        "    b.termination(threshold_count('substrate.ProducerCompleted', 1))\n"
    )
    runner = CliRunner()
    res = runner.invoke(main, ["validate", "--topology-module", f"{mod}:topo"])
    assert res.exit_code == 0
    assert "[OK] Topology validates." in res.stdout


def test_conformance_runs_the_suite_and_surfaces_deferred_distinctly(tmp_path):
    # the harness is wired (Wave 9). Run with --no-perf (the perf floor is its own benchmark
    # + an honest open finding) so the gate has zero FAILs; assert it does NOT print a false
    # green for the deferred check.
    runner = CliRunner()
    res = runner.invoke(main, ["conformance", "--no-perf"])
    assert res.exit_code == EXIT_OK  # no check FAILED
    out = res.stdout + res.stderr
    # check 6 (Level-3b) is shown as a GENUINE third state, never a green PASS
    assert "DEFERRED (spec-amended A1.1)" in out
    assert "[06/17] Replay round-trip" in out
    # check 15 under --no-perf is SKIPPED — a DISTINCT label from DEFERRED (review #5 FIX B)
    assert "SKIPPED" in out
    assert "[15/17] Performance floor" in out
    # the summary names deferred AND skipped counts explicitly (not folded into "passed")
    assert "deferred" in out.lower() and "skipped" in out.lower()


def test_conformance_with_perf_fails_honestly_if_floor_unmet(tmp_path):
    # with perf ON, if the N-PERF-1 floor is not met on this hardware the gate FAILs with the
    # real measured number — never a fudged green. (On hardware that meets the floor, exit 0.)
    runner = CliRunner()
    res = runner.invoke(main, ["conformance"])
    out = res.stdout + res.stderr
    assert "appends/sec" in out  # a real measurement is reported either way
    # exit reflects the measured reality: 0 if the floor is met, 1 if not — not fudged
    assert res.exit_code in (EXIT_OK, EXIT_FAILED)


def test_stats_reads_writer_stats_sidecar(tmp_path):
    import asyncio

    root = tmp_path / "run"
    asyncio.run(Runtime(root, writer_stats=True).run(_topo))
    runner = CliRunner()
    res = runner.invoke(main, ["stats", str(root), "--sidecar", "writer_stats"])
    assert res.exit_code == 0
    assert "writer_stats:" in res.stdout


_VALIDATE_MODULE = """
from msgspec import Struct
from substrate import api
class Note(Struct, frozen=True):
    text: str
async def _p(inp):
    yield Note(text="x")
def _common(b, kind):
    b.producer_kind("w", schemas=[Note], schema_version=1, factory=lambda: _p)
    b.initial("w", input=None)
    b.trigger("t", subscription=api.Subscription(kinds=frozenset({kind})),
              predicate=lambda ctx: True, starts="w", input_builder=lambda ctx: None, policy=api.Once())
    b.termination(api.all_completed())
def good(b): _common(b, "Note")
def bad(b): _common(b, "FailEvent")  # no Producer declares FailEvent
"""


def test_cli_validate_clean_topology_reports_counts(tmp_path):
    mod = tmp_path / "vt.py"
    mod.write_text(_VALIDATE_MODULE)
    res = CliRunner().invoke(main, ["validate", "--topology-module", f"{mod}:good"])
    assert res.exit_code == EXIT_OK, res.output
    assert "Producer kinds" in res.stdout and "[OK]" in res.stdout


def test_cli_validate_flags_undeclared_kind(tmp_path):
    # F-CLI-3: a Trigger subscribing to a kind no Producer declares is a dead reference -> FAIL.
    mod = tmp_path / "vt.py"
    mod.write_text(_VALIDATE_MODULE)
    res = CliRunner().invoke(main, ["validate", "--topology-module", f"{mod}:bad"])
    assert res.exit_code == EXIT_CONFIG, res.output
