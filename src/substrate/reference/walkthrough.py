# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Walkthrough-mode runner for the reference topologies (product §8).

`python -m substrate.reference.walkthrough <r1|r2|r3> <root> [<inner_root>]` runs a reference
topology in WALKTHROUGH mode — with REAL local LLMs via the openai-compat adapter (Ollama at
http://localhost:11434/v1) — and prints what it demonstrated. This is the mode that proves
the CLAIM each topology exists for (real adjudication in R-1, a real model's structured-error
behavior in R-2, real code-synthesis with cross-chunk overlap in R-3), as opposed to CI mode
(deterministic stand-ins, proves only the wiring). The spec requires both; CI mode alone
"sanitizes away the thing each topology exists to demonstrate."

Models (LOCAL only; cloud models avoided): `llama3.2:1b` for the weak ensemble members and
the R-2 transform; `huihui_ai/qwen2.5-coder-abliterate:7b` as the R-1 adjudicator and the
R-3 writer. Inputs are kept SMALL — this is a demonstration on the operator's machine, not a
benchmark. Requires the `openai-compat` extra (httpx) and a running Ollama with those models.

Documented runs (record roots + what each demonstrated) live in docs/walkthroughs/.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from .. import api
from ._models import OllamaResponder
from .r1_ensemble import ensemble_topology
from .r2_pipeline import operator_override, pipeline_topology
from .r3_codesynth import _complete_defs, codesynth_composed_topology

_WEAK = "llama3.2:1b"
_STRONG = "huihui_ai/qwen2.5-coder-abliterate:7b"
# Token caps bound a demo's cost; the system prompts ask for the short answer. A reply that
# reaches its cap fails the producer (OllamaResponder raises on done_reason "length" since UI
# sprint 097), so each cap sits well above the answer asked for. The old 12/16/24-token caps
# left no room for a model that adds one word; 160 could cut R-3's code mid-function.
_SHORT_CAP = 64
_CODE_CAP = 1024


async def _run_r1(root: Path) -> None:
    # The R-1 demonstration needs the two things CI cannot fake: (1) weak models that genuinely
    # DISAGREE (an open, judgment question — not "2+2", where every model says "4" and the
    # ensemble is pointless), and (2) cancel-all-others firing on R-1's OWN record. For (2) we
    # add LINGERING members (`slowA`/`slowB`) that are still running when the quorum of fast
    # members fires the adjudicator; on the adjudicator's completion they are cancelled. A
    # non-zero temperature widens the disagreement across the weak members.
    fast = {
        f"m{i}": OllamaResponder(
            _WEAK,
            max_tokens=_SHORT_CAP,
            temperature=0.9,
            system="Answer with ONE short word. No explanation.",
        )
        for i in range(3)
    }
    slow = {
        name: OllamaResponder(
            _WEAK,
            max_tokens=_SHORT_CAP,
            temperature=0.9,
            system="Answer with ONE short word. No explanation.",
        )
        for name in ("slowA", "slowB")
    }
    adj = OllamaResponder(
        _STRONG,
        max_tokens=_SHORT_CAP,
        system="Given candidate answers labelled by member id, pick the single best one. "
        "Reply with JUST the member id (e.g. m0).",
    )
    topo = ensemble_topology(
        "In one word, what is the most important quality in a leader?",
        members={**fast, **slow},
        adjudicator=adj,
        quorum=3,
        slow_members=frozenset(slow),
        linger_seconds=8.0,  # still running when the 3 fast members fire the adjudicator
        deterministic=False,  # a real LLM is not author-deterministic
    )
    result = await api.Runtime(root).run(topo)
    envs = list(api.read_record(root))
    print(f"R-1 status: {result.status}")
    answers = [e["payload"]["answer"] for e in envs if e["kind"] == "Candidate"]
    for e in envs:
        if e["kind"] == "Candidate":
            print(f"  Candidate {e['payload']['member']}: {e['payload']['answer']!r}")
        elif e["kind"] == "Verdict":
            print(f"  VERDICT: {e['payload']['chosen']} -> {e['payload']['answer']!r}")
        elif e["kind"] == api.PRODUCER_CANCELLED:
            print(f"  CANCELLED (lingering loser): {e['payload']['producer']['kind']}")
    print(
        f"  distinct answers among candidates: {len(set(a.lower() for a in answers))} of {len(answers)}"
    )


async def _run_r2(root: Path) -> None:
    # R-2 runs on a PERSISTENT bus so the pause survives to a fresh Runtime — the walkthrough
    # demonstrates the full structured-error cascade AND halt-with-resume end to end: a real
    # model does the transform; seeded faults drive invalid-emission -> retry-with-enrichment,
    # an unrecoverable fault -> RetryExhausted -> pause; then a resume injects the operator
    # override and the run finalises.
    tx = OllamaResponder(
        _WEAK,
        max_tokens=_SHORT_CAP,
        system="Uppercase the input word. Reply with ONLY the uppercased word.",
    )
    topo = pipeline_topology(
        ["alpha", "beta", "gamma", "delta"],
        transform_model=tx,
        fault_row=1,  # recoverable: retry-with-enrichment succeeds
        hard_fault_row=2,  # unrecoverable: escalates to RetryExhausted -> pause
        malformed_row=3,  # input_builder raises -> InputBuildFailed
        deterministic=False,  # a real LLM is not author-deterministic
    )

    paused = await api.Runtime(root, persistent=True).run(topo)
    print(f"R-2 (run-to-pause) status: {paused.status}")
    for e in api.read_record(root):
        k = e["kind"]
        if k == "Transformed":
            print(
                f"  Transformed row={e['payload']['row']} attempt={e['payload']['attempt']}: {e['payload']['out']!r}"
            )
        elif k == api.PRODUCER_EMITTED_INVALID:
            print(
                f"  INVALID-EMISSION row={(e['payload'].get('raw_payload') or {}).get('row')} reason={e['payload']['reason']}"
            )
        elif k == api.INPUT_BUILD_FAILED:
            print(
                f"  INPUT-BUILD-FAILED trigger={e['payload'].get('trigger_id')}: {e['payload'].get('error')}"
            )
        elif k == "RetryExhausted":
            print(
                f"  RETRY-EXHAUSTED row={e['payload']['row']} after {e['payload']['attempts']} attempt(s)"
            )
        elif k == api.TERMINATION_MATCHED:
            print(
                f"  TERMINATION: {e['payload']['decision']} (resume_condition={e['payload'].get('resume_condition')})"
            )

    # Resume in a FRESH Runtime — the F-PERS-2 cross-process promise — injecting the operator
    # override; the recovery Producer runs and the run finalises on the SAME seq sequence.
    resumed = await api.Runtime(root, persistent=True).resume(
        topo, resume_event=operator_override(row=2)
    )
    print(
        f"R-2 (resume) status: {resumed.status} | run_id continuous: {paused.run_id == resumed.run_id}"
    )
    after = list(api.read_record(root))
    for e in after:
        if e["kind"] == "Recovered":
            print(f"  RECOVERED row={e['payload']['row']} by={e['payload']['by']}")
    seqs = [e["seq"] for e in after]
    print(f"  continuous seq across pause: {seqs == list(range(len(seqs)))} (len {len(seqs)})")


async def _run_r3(root: Path, inner_root: Path) -> None:
    writer = OllamaResponder(
        _STRONG,
        max_tokens=_CODE_CAP,
        system="Write ONLY Python code, no prose, no markdown fences.",
    )
    code = writer.respond(
        "Write two functions: add(a,b) returning a+b, and mul(a,b) returning a*b."
    )
    chunks = [code[i : i + 30] for i in range(0, len(code), 30)]  # ~30-char chunks => overlap
    topo = codesynth_composed_topology(chunks, str(inner_root), deterministic=False)
    result = await api.Runtime(root).run(topo)
    inner = list(api.read_record(inner_root))
    outer = list(api.read_record(root))
    print(
        f"R-3 status: {result.status} | chunks: {len(chunks)} | complete defs: {len(_complete_defs([{'text': code}]))}"
    )
    print(f"  inner Declarations: {sum(1 for e in inner if e['kind'] == 'Declaration')}")
    print(
        f"  crossed to outer (OuterArtifact): {sum(1 for e in outer if e['kind'] == 'OuterArtifact')}"
    )
    print(
        f"  inner kinds leaked to outer: {any(e['kind'] in ('CodeChunk', 'Declaration', 'TypecheckOk') for e in outer)}"
    )


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: python -m substrate.reference.walkthrough <r1|r2|r3> <root> [<inner_root>]")
        raise SystemExit(64)
    which = args[0]
    root = Path(args[1]) if len(args) > 1 else Path("walkthrough") / which
    if which == "r1":
        asyncio.run(_run_r1(root))
    elif which == "r2":
        asyncio.run(_run_r2(root))
    elif which == "r3":
        inner = Path(args[2]) if len(args) > 2 else root.parent / "r3-inner"
        asyncio.run(_run_r3(root, inner))
    else:
        print(f"unknown topology {which!r}; expected r1, r2, or r3")
        raise SystemExit(64)
    print(f"record root: {root}")


if __name__ == "__main__":
    main()
