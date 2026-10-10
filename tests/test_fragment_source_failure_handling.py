# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""A failed session-open prompt source (sprint 068; one producer since K263).

Two invariants:
 - A source that raises lands on the record as SessionWarning(kind=fragment_source_failed,
   source_name=<the source>, detail=<the error>), and the other sources' fragments still land.
 - The session never breaks: the model builds its prompt from the fragments that landed and
   the session runs to completion.

Failures are induced by monkey-patching a source function of `session_prompt_producer`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from substrate import api
from substrate.topologies.session import SessionWarning
from substrate.topologies.session import session_prompt_producer as sp
from substrate.topologies.session.ci import ci_session_topology


def _read_kinds(record_root: Path) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for env in api.read_record(record_root):
        out.setdefault(env["kind"], []).append(env)
    return out


def _raise_in(monkeypatch: Any, name: str) -> None:
    def _raising(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError(f"simulated {name} failure")

    monkeypatch.setattr(sp, name, _raising)


def test_fragment_failure_surfaces_as_session_warning(tmp_path: Path, monkeypatch: Any) -> None:
    """The tools_suite source raises: one warning names it with the error, the session_prompt
    producer itself completes, and the model still records a prompt."""
    _raise_in(monkeypatch, "tools_suite_fragments")

    async def _run() -> None:
        topology = ci_session_topology(turns=("hi", "/exit"), session_id="s_frag_fail_tools")
        await api.Runtime(tmp_path / "ci").run(topology)

    asyncio.run(_run())
    kinds = _read_kinds(tmp_path / "ci")
    assert not kinds.get("substrate.ProducerFailed"), kinds.get("substrate.ProducerFailed")
    warnings = [
        e["payload"]
        for e in kinds.get("SessionWarning", [])
        if e["payload"].get("kind") == "fragment_source_failed"
    ]
    assert len(warnings) == 1, warnings
    assert warnings[0]["source_name"] == "tools_suite"
    assert "simulated tools_suite_fragments failure" in warnings[0]["detail"]
    assert not any(e["payload"]["source"] == "tools_suite" for e in kinds.get("PromptFragment", []))
    assert kinds.get("PromptComposed"), "the model never recorded a prompt after the failure"


def test_one_failed_source_keeps_the_others(tmp_path: Path, monkeypatch: Any) -> None:
    """Before K263 each source was its own producer, so one failure stopped only that source.
    The merged producer keeps that: the role fails, the bundle and tool fragments still land,
    and the first prompt carries them."""
    _raise_in(monkeypatch, "role_fragments")

    async def _run() -> None:
        topology = ci_session_topology(
            turns=("hi", "/exit"), session_id="s_frag_fail_role", role="reviewer", bundle="session"
        )
        await api.Runtime(tmp_path / "ci").run(topology)

    asyncio.run(_run())
    kinds = _read_kinds(tmp_path / "ci")
    sources = [e["payload"]["source"] for e in kinds.get("PromptFragment", [])]
    assert sources == ["bundle_methodology", "tools_suite"], sources
    warnings = [e["payload"] for e in kinds.get("SessionWarning", [])]
    assert [w["source_name"] for w in warnings] == ["role"]
    first_prompt = kinds["PromptComposed"][0]["payload"]
    tool_frag_seq = next(
        e["seq"] for e in kinds["PromptFragment"] if e["payload"]["source"] == "tools_suite"
    )
    assert tool_frag_seq in first_prompt["fragment_seqs"]


def test_session_runs_to_completion_despite_fragment_failure(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A source failure does not hang the session. SessionEnded lands and the run finalises."""
    _raise_in(monkeypatch, "tools_suite_fragments")

    async def _run() -> None:
        topology = ci_session_topology(turns=("hi", "/exit"), session_id="s_frag_fail_completes")
        result = await api.Runtime(tmp_path / "ci").run(topology)
        assert result.status == "finalised"

    asyncio.run(_run())
    assert _read_kinds(tmp_path / "ci").get("SessionEnded"), "SessionEnded never fired"


def test_session_warning_struct_carries_source_name_and_detail() -> None:
    """`source_name` (v0.2.1) and `detail` (v0.3.3) default to None, so a record written with
    only the four v0.1 fields still decodes."""
    old_shape = SessionWarning(
        session_id="s_x",
        kind="seed_alone_exceeds",
        seed_tokens=100,
        driver_context_tokens=1000,
    )
    assert old_shape.source_name is None and old_shape.detail is None

    new_shape = SessionWarning(
        session_id="s_y",
        kind="fragment_source_failed",
        seed_tokens=0,
        driver_context_tokens=0,
        source_name="role",
        detail="FileNotFoundError('reviewer.md')",
    )
    assert new_shape.source_name == "role"
    assert new_shape.detail == "FileNotFoundError('reviewer.md')"
