# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Bundled topology registry — makes `substrate run --topology <name>` work (review #16).

The CLI advertises `--topology <name>` and an error that names a registry, but the registry
ships empty, so a newcomer hits a dead end. This module populates it with CI-default (no-network,
deterministic) configs of the bundled topologies; `cli._load_topology` imports this module
DYNAMICALLY on a `--topology` lookup, so the CLI's static import surface stays substrate.api-only
(F-API-6 — import-linter checks static imports, not a runtime importlib call).

CI defaults run anywhere with no Ollama and produce a replayable record (tail / replay / inspect
all work). The richer real-LLM walkthrough is a separate path (the demo's `walkthrough=True`).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .. import api
from ..adapters import DeterministicResponder
from .adversarial_pair import adversarial_pair_topology
from .applications.best_of_n_verified import best_of_n_verified_topology
from .applications.fanout_review import fanout_review_topology
from .applications.research_sweep import research_sweep_topology
from .code_review import DEFAULT_ROLES, code_review_topology
from .debate import debate_topology
from .game_of_life import game_of_life_topology, glider
from .intel_asymmetry import intel_asymmetry_topology
from .natural_conversation import natural_conversation_topology
from .pair_coding import pair_coding_topology
from .prisoners_dilemma import prisoners_dilemma_topology
from .recursive_decomposition import recursive_decomposition_topology
from .session.ci import ci_session_topology
from .swebench_solver.bundled import swebench_repair_ci
from .tool_loop import tool_loop_topology

_Topo = Callable[[api.TopologyBuilder], None]


def _code_review() -> _Topo:
    # slow_roles + linger so the demo (and the committed record, now generated from THIS factory)
    # actually demonstrates cancel-all-others: the lingering reviewers are cancelled when the judge
    # fires (review #25 finding A — `demo run` must show what `demo replay` shows).
    return code_review_topology(
        "def f(x):\n    return x / 0\n",
        responders={r: DeterministicResponder(seed=i) for i, r in enumerate(DEFAULT_ROLES)},
        judge=DeterministicResponder(seed=99),
        quorum=3,
        slow_roles=frozenset({"correctness", "clarity"}),
        linger_seconds=0.5,
    )


def _pair_coding() -> _Topo:
    return pair_coding_topology(
        "write solve()",
        driver_model=DeterministicResponder(seed=1),
        navigator_model=DeterministicResponder(seed=2),
        chunks=["def solve(x):\n", "    y = x + 1\n", "    return y\n"],
    )


def _recursive() -> _Topo:
    return recursive_decomposition_topology(
        "build a feature", solver_model=DeterministicResponder(seed=3), max_depth=2, fanout=2
    )


# ── sprint 224b: CI-mode factories for the four shipped applications ────


def _fanout_review_ci() -> _Topo:
    """`fanout_review_topology` needs a git repo at `HEAD~1`. Use a
    per-import temp repo under `~/.substrate/ci-fixtures/fanout_review/`
    seeded with one file + two commits (initial + a diff)."""
    import subprocess

    from substrate.api import substrate_home

    fixture = substrate_home() / "ci-fixtures" / "fanout_review_repo"
    if not (fixture / ".git").is_dir():
        fixture.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", str(fixture)], check=True)
        subprocess.run(
            ["git", "-C", str(fixture), "config", "user.email", "ci@substrate"], check=True
        )
        subprocess.run(["git", "-C", str(fixture), "config", "user.name", "ci"], check=True)
        (fixture / "app.py").write_text("def f(x):\n    return x\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(fixture), "add", "app.py"], check=True)
        subprocess.run(["git", "-C", str(fixture), "commit", "-qm", "initial"], check=True)
        (fixture / "app.py").write_text("def f(x):\n    return x / 0\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(fixture), "add", "app.py"], check=True)
        subprocess.run(["git", "-C", str(fixture), "commit", "-qm", "divide-by-zero"], check=True)
    return fanout_review_topology(
        repo=str(fixture),
        ref="HEAD~1",
        responders={role: DeterministicResponder(seed=i) for i, role in enumerate(DEFAULT_ROLES)},
        judge=DeterministicResponder(seed=99),
        quorum=3,
    )


def _has_answer_six(response: str) -> tuple[bool, str]:
    """Deterministic Check for best_of_n_verified: passes iff the
    response contains a `6`. Trivial; the point of the CI factory is
    that the loop runs end-to-end on the record, not that the check
    is realistic."""
    if "6" in response:
        return True, "found 6"
    return False, "did not find 6"


def _best_of_n_verified_ci() -> _Topo:
    return best_of_n_verified_topology(
        task="double 3 to produce 6",
        drafter=DeterministicResponder(seed=11),
        verify=_has_answer_six,
        n=2,
        max_rounds=1,
        deterministic=True,
    )


def _research_sweep_ci() -> _Topo:
    documents = [
        ("doc_a", "The answer to 40 plus 2 is 42, per the arithmetic table."),
        ("doc_b", "42 is the sum of 40 and 2."),
        ("doc_c", "See doc_a for the sum of 40 and 2."),
    ]
    return research_sweep_topology(
        question="what is 40 plus 2?",
        documents=documents,
        reader=DeterministicResponder(seed=21),
        critic=DeterministicResponder(seed=22),
        synthesizer=DeterministicResponder(seed=23),
        deterministic=True,
    )


def _daily_ci() -> _Topo:
    """`daily` wraps session_topology. The CI variant reuses the
    scripted opener sprint 209 shipped for `session` — a three-turn
    walk ending in /exit that finalises the record cleanly."""
    return ci_session_topology()


# name -> a zero-arg factory returning the CI-default configured topology.
BUNDLED: dict[str, Callable[[], _Topo]] = {
    "code_review": _code_review,
    "pair_coding": _pair_coding,
    "recursive_decomposition": _recursive,
    "debate": debate_topology,
    "prisoners_dilemma": prisoners_dilemma_topology,
    "intel_asymmetry": intel_asymmetry_topology,
    "natural_conversation": lambda: natural_conversation_topology(instruments=True),
    # the WITHOUT arm, so the ablation is a runnable WITH-vs-WITHOUT contrast (review #17):
    # run both and diff the records to SEE what the instruments buy.
    "natural_conversation_bare": lambda: natural_conversation_topology(instruments=False),
    "adversarial_pair": adversarial_pair_topology,
    "tool_loop": tool_loop_topology,
    "game_of_life": game_of_life_topology,
    # an asymmetric, MOVING glider (vs the symmetric blinker) — the fixture that lets the pixel-decode
    # harness catch a pure mirror render bug the mirror-symmetric blinker cannot show.
    "game_of_life_glider": lambda: game_of_life_topology(initial=glider(), generations=4),
    # Sprint 188 (roadmap v2 S2 part 2 of 2): swebench_repair joins the bundled registry.
    # Uses a deterministic on-disk fixture repo under ~/.substrate/ci-fixtures/swebench_repair/
    # (override via SUBSTRATE_CI_FIXTURE_ROOT) so the record is byte-stable across regenerations.
    "swebench_repair": swebench_repair_ci,
    # Sprint 209b: the daily-driver session topology. `session_topology` itself terminates on
    # `pause_await_input(Park)` — the correct shape for a driver conversation — but does not
    # finalise in one `.run()`, so `gen_topology_records.py` cannot record it directly. The
    # `ci_session_topology` wrapper adds an opener producer that walks a three-turn script
    # ending in `/exit`, and overrides the termination to `threshold_count(SessionEnded, 1)`
    # so the CI record finalises cleanly. Everything else — Structs, triggers, Views — comes
    # from `session_topology` unchanged.
    "session": ci_session_topology,
    # Sprint 224b: CI-mode factories for the four shipped applications.
    # Every entry runs deterministic (no network), finalises cleanly, and
    # `substrate demo replay <name>` walks the committed record.
    "fanout_review": _fanout_review_ci,
    "best_of_n_verified": _best_of_n_verified_ci,
    "research_sweep": _research_sweep_ci,
    "daily": _daily_ci,
}

# Sprint 224: `pair_coding` name collision. Sprint 225 adds
# `applications/pair_coding_composite.py` — a session-composite that owns
# the name unambiguously in the application catalog. The existing
# BUNDLED entry (the chunked-writer demo topology) renames to
# `pair_coding_chunked` here. The Python function name at
# `topologies/pair_coding/__init__.py:87` stays the same for source
# compatibility; only the BUNDLED key changes. The module directory
# at `topologies/pair_coding/` also stays (renaming a Python package
# for a naming decision would ripple through imports everywhere and
# is not what the collision-fix asked for).
_KEY_RENAMES: dict[str, str] = {"pair_coding": "pair_coding_chunked"}
BUNDLED = {_KEY_RENAMES.get(k, k): v for k, v in BUNDLED.items()}

# Map a BUNDLED key back to the directory where its committed CI record
# lives. Populated only for renamed keys; the default is `key == dirname`.
_KEY_TO_RECORD_DIR: dict[str, str] = {"pair_coding_chunked": "pair_coding"}

_registered = False


def register_all() -> None:
    """Register every bundled topology under its name (idempotent). Called on demand by the CLI."""
    global _registered
    if _registered:
        return
    for name, factory in BUNDLED.items():
        api.register_topology(name, factory())
    _registered = True


def names() -> list[str]:
    """The bundled topology names (for `topology list` / discovery)."""
    return sorted(BUNDLED)


def record_path(name: str) -> Path:
    """The committed CI-mode record path for a bundled topology (for `demo replay <name>`).

    A renamed BUNDLED key (e.g. `pair_coding_chunked`) maps back to its
    original module directory via `_KEY_TO_RECORD_DIR`. Old callers
    passing the pre-rename key still resolve via the same lookup — the
    old name is a valid alias for record lookup purposes only.
    """
    directory = _KEY_TO_RECORD_DIR.get(name, name)
    # Backwards-compat: a caller passing the pre-rename key (e.g.
    # `pair_coding`) resolves to the same directory the new key does.
    for renamed_from, renamed_to in _KEY_RENAMES.items():
        if name == renamed_from:
            directory = _KEY_TO_RECORD_DIR.get(renamed_to, renamed_to)
    return Path(__file__).resolve().parent / directory / "records" / "ci_mode.record"
