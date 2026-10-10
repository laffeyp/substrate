# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 052 — live-model tool-comprehension suite.

The bar: for every tool the substrate ships in the session's tool suite,
prove with a REAL small model that

  (a) the model picks the correct tool from the suite when asked to,
  (b) the tool's ToolResult carries the shape the docs promise, and
  (c) the model's reply reflects reading the result — not just
      that the ToolCall event landed.

Driver: qwen2.5:7b-instruct (see probe in the sprint-052 notes). It is
4.4 GB, ~0.7 s per turn, native tool_calls with correct argument keys.
Fallback probe path (JSON-in-content) is exercised by qwen2.5-coder:7b
in a separate parametrisation where relevant.

Sandboxing:
  - Every test's workspace + record lands in pytest's `tmp_path`. No
    write ever touches `~/.substrate/`.
  - Each test gets ONLY the tools it exercises (constrained suite),
    keeping the model's decision space small and every assertion pointed.
  - `bash` and `web_fetch` are opt-in (separate files if we add them).

Gated by `@pytest.mark.realmodel` — skipped when Ollama or the model
is absent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from substrate.topologies.session.vocabulary import turn_replies
from substrate import api
from substrate.adapters import OllamaResponder
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.tool_loop.tools import Tool

pytestmark = pytest.mark.realmodel

_DRIVER = "qwen2.5:7b-instruct"
_OLLAMA_V1 = "http://localhost:11434/v1"


def _require_model() -> None:
    try:
        ids = {m["id"] for m in httpx.get(_OLLAMA_V1 + "/models", timeout=4).json().get("data", [])}
    except Exception as exc:  # noqa: BLE001 — any unreachability is a SKIP
        pytest.skip(f"tool-comprehension skipped — Ollama not reachable ({type(exc).__name__})")
    if _DRIVER not in ids:
        pytest.skip(f"tool-comprehension skipped — model absent: {_DRIVER}")


def _open_session(
    *,
    tmp_path: Path,
    tools: dict[str, Tool],
    first_text: str,
    system: str = "You have access to tools. Call the RIGHT one when the user asks.",
) -> tuple[Path, Path, Any]:
    """Build a session pointed at `tmp_path`, constrained to `tools`, opened
    with `first_text`. Returns (record_root, workspace, factory) so the
    caller drives via `api.Runtime(record_root, ...).run(factory)`."""
    record_root = tmp_path / "record"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    factory = session_topology(
        driver=OllamaResponder(_DRIVER, max_tokens=200, temperature=0, system=system),
        driver_name=_DRIVER,
        driver_context_tokens=8192,
        seed="",
        tools=tools,
        per_turn="",
        max_turns=10,
        turn_max_steps=6,
        session_id="s_test_comprehension",
        workspace_path=str(workspace),
        script=None,
        first_turn_user_message=UserMessage(
            text=first_text,
            turn_index=0,
            assembled_prompt=first_text,
            slash_source="test",
        ),
    )
    return record_root, workspace, factory


def _events(root: Path) -> list[dict[str, Any]]:
    return list(api.read_record(root))


def _by_kind(envs: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [e for e in envs if e["kind"] == kind]


def _last_answer(envs: list[dict[str, Any]]) -> str:
    finals = turn_replies(envs)
    if not finals:
        return ""
    return finals[-1][1]


# ── list_topologies ────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_list_topologies_read_back_by_model(tmp_path: Path) -> None:
    """Model calls list_topologies; result carries the bundled registry;
    model's answer names at least one of the bundled topologies."""
    _require_model()
    from substrate.topologies.tool_loop.substrate_tools import make_list_topologies

    tools = {"list_topologies": make_list_topologies()}
    record_root, _ws, factory = _open_session(
        tmp_path=tmp_path,
        tools=tools,
        first_text="list the substrate topologies available on this box. Then tell me one of them.",
    )
    result = await api.Runtime(record_root, persistent=True).run(factory)
    assert result.status == "paused", f"expected paused, got {result.status}"

    envs = _events(record_root)
    calls = _by_kind(envs, "ToolCall")
    results = _by_kind(envs, "ToolResult")
    assert calls, "model made no ToolCall"
    assert any(c["payload"].get("tool") == "list_topologies" for c in calls), (
        f"expected list_topologies to be called; got tools={[c['payload'].get('tool') for c in calls]}"
    )
    assert results and results[0]["payload"].get("ok") is True, (
        f"list_topologies should return ok=True; got {results[0]['payload'] if results else None}"
    )
    output = results[0]["payload"].get("output") or {}
    topologies = output.get("topologies") or []
    assert isinstance(topologies, list) and topologies, (
        f"list_topologies output should carry a non-empty topologies list; got {output}"
    )
    # (c) comprehension — the model's final answer names at least one of the topologies.
    answer = _last_answer(envs).lower()
    assert any(t.lower() in answer for t in topologies), (
        f"final answer must name at least one topology from {topologies}; got {answer!r}"
    )


# ── list_applications ─────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_list_applications_read_back_by_model(tmp_path: Path) -> None:
    """Model calls list_applications; the result carries the app registry
    passed in; model's answer names at least one application."""
    _require_model()
    # `_make_list_applications_impl` reads `.name/.description/.runs/.
    # output_kind` off the values — msgspec Structs in production. A
    # lightweight namespace stand-in has the same duck type.
    from types import SimpleNamespace

    from substrate.topologies.tool_loop.substrate_tools import make_list_applications

    app_registry = {
        "code_review": SimpleNamespace(
            name="code_review",
            description="quorum review + adjudicator",
            runs="compose",
            output_kind="Verdict",
        ),
        "best_of_n_verified": SimpleNamespace(
            name="best_of_n_verified",
            description="generate N, verify each, select",
            runs="compose",
            output_kind="Solved",
        ),
    }
    tools = {"list_applications": make_list_applications(app_registry)}
    record_root, _ws, factory = _open_session(
        tmp_path=tmp_path,
        tools=tools,
        first_text="list the substrate applications available. Then tell me the name of one.",
    )
    result = await api.Runtime(record_root, persistent=True).run(factory)
    assert result.status == "paused", f"expected paused, got {result.status}"

    envs = _events(record_root)
    calls = _by_kind(envs, "ToolCall")
    results = _by_kind(envs, "ToolResult")
    assert any(c["payload"].get("tool") == "list_applications" for c in calls)
    assert results and results[0]["payload"].get("ok") is True
    output = results[0]["payload"].get("output") or {}
    apps = output.get("applications") or []
    assert isinstance(apps, list) and len(apps) == 2, (
        f"list_applications should return the two-entry registry; got {output}"
    )
    answer = _last_answer(envs).lower()
    assert any(a["name"].lower() in answer for a in apps if isinstance(a, dict) and "name" in a), (
        f"final answer must name one of {[a.get('name') for a in apps]}; got {answer!r}"
    )


# ── list_records ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_list_records_read_back_by_model(tmp_path: Path) -> None:
    """Seed a fake records directory with two entries, model calls
    list_records, result shape matches, model's answer references the
    count."""
    _require_model()
    import msgspec

    from substrate.topologies.tool_loop.substrate_tools import make_list_records

    # Two fake session records under `records_root/`. list_records walks
    # `<records_root>/<sid>/manifest.json` (server layout).
    records_root = tmp_path / "records"
    for sid in ("s_aaaa", "s_bbbb"):
        d = records_root / sid
        d.mkdir(parents=True)
        (d / "manifest.json").write_bytes(
            msgspec.json.encode(
                {
                    "session_id": sid,
                    "status": "ended",
                    "created_at": 1788000000.0,
                    "topology": "session",
                    "name": sid,
                }
            )
        )
    tools = {"list_records": make_list_records(records_root)}
    record_root, _ws, factory = _open_session(
        tmp_path=tmp_path,
        tools=tools,
        first_text="list all the records. How many are there?",
    )
    result = await api.Runtime(record_root, persistent=True).run(factory)
    assert result.status == "paused"

    envs = _events(record_root)
    calls = _by_kind(envs, "ToolCall")
    results = _by_kind(envs, "ToolResult")
    assert any(c["payload"].get("tool") == "list_records" for c in calls)
    # An invalid argument (a model sent limit=0 on 2026-10-01) is now an error observation the
    # model corrects (UI sprint 097); grade the first SUCCESSFUL list_records result.
    ok = [
        r
        for r in results
        if r["payload"].get("tool") == "list_records" and r["payload"].get("ok") is True
    ]
    assert ok, f"no successful list_records result: {[r['payload'] for r in results]}"
    output = ok[0]["payload"].get("output") or {}
    assert output.get("count") == 2, f"expected count=2, got {output.get('count')}: {output}"
    answer = _last_answer(envs)
    assert "2" in answer or "two" in answer.lower(), (
        f"final answer must reference the count (2); got {answer!r}"
    )


# ── list_sessions ────────────────────────────────────────────────────────


class _FakeRegistry:
    """Duck-type of substrate.topologies.session_registry.SessionRegistry.list_all,
    kept in-file so the test does not import the daemon."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def list_all(self) -> list[Any]:
        return list(self._rows)


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_list_sessions_read_back_by_model(tmp_path: Path) -> None:
    """Fake session-registry with two rows (one running, one parked),
    model calls list_sessions, result shape matches spec bucket
    layout, model's answer references both."""
    _require_model()
    from types import SimpleNamespace

    from substrate.topologies.tool_loop.substrate_tools import make_list_sessions

    # `_make_list_sessions_impl` reads `.session_id/.name/.driver/.
    # workspace/.status` off each manifest — msgspec Structs in
    # production. SimpleNamespace has the same duck type.
    registry = _FakeRegistry(
        [
            SimpleNamespace(
                session_id="s_aaaa",
                name="alpha",
                driver=_DRIVER,
                status="running",
                workspace=str(tmp_path / "ws1"),
            ),
            SimpleNamespace(
                session_id="s_bbbb",
                name="beta",
                driver=_DRIVER,
                status="parked",
                workspace=str(tmp_path / "ws2"),
            ),
        ]
    )
    tools = {"list_sessions": make_list_sessions(registry)}
    record_root, _ws, factory = _open_session(
        tmp_path=tmp_path,
        tools=tools,
        first_text=(
            "list the substrate sessions and tell me how many are LIVE and how many PARKED."
        ),
    )
    result = await api.Runtime(record_root, persistent=True).run(factory)
    assert result.status == "paused"

    envs = _events(record_root)
    calls = _by_kind(envs, "ToolCall")
    results = _by_kind(envs, "ToolResult")
    assert any(c["payload"].get("tool") == "list_sessions" for c in calls)
    assert results and results[0]["payload"].get("ok") is True
    output = results[0]["payload"].get("output") or {}
    # `_make_list_sessions_impl` returns {live: [...], parked: [...]}.
    live = output.get("live") or []
    parked = output.get("parked") or []
    assert len(live) == 1 and len(parked) == 1, (
        f"list_sessions should split one live + one parked; got live={live} parked={parked}"
    )
    answer = _last_answer(envs).lower()
    # Comprehension: mentions both buckets by count OR by name.
    assert "1 live" in answer or "one live" in answer or "alpha" in answer
    assert "1 park" in answer or "one park" in answer or "beta" in answer


# ── inspect_record ───────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.timeout(90)
async def test_inspect_record_summary_read_back_by_model(tmp_path: Path) -> None:
    """Seed a real substrate record (a tiny scripted session ends at
    /exit), then in a NEW session ask the model to inspect_record on it.
    The tool's summary output should carry `finalised: True` and
    `total_events` > 0; the model's final answer should reference the
    record's finalised state."""
    _require_model()
    from substrate.topologies.session.ci import ci_session_topology
    from substrate.topologies.tool_loop.substrate_tools import make_inspect_record

    # Seed record: two scripted turns + /exit, one clean SessionEnded.
    seeded_root = tmp_path / "seeded"
    await api.Runtime(seeded_root, persistent=True).run(
        ci_session_topology(turns=("hi", "/exit"), session_id="s_seed")
    )

    tools = {"inspect_record": make_inspect_record(driver_context_tokens=8192)}
    record_root, _ws, factory = _open_session(
        tmp_path=tmp_path,
        tools=tools,
        first_text=(
            f'Call inspect_record on the record at {seeded_root} with format="summary". '
            "Then tell me whether the record finalised."
        ),
    )
    result = await api.Runtime(record_root, persistent=True).run(factory)
    assert result.status == "paused"

    envs = _events(record_root)
    calls = _by_kind(envs, "ToolCall")
    results = _by_kind(envs, "ToolResult")
    inspect_calls = [c for c in calls if c["payload"].get("tool") == "inspect_record"]
    assert inspect_calls, (
        f"model did not call inspect_record; tools={[c['payload'].get('tool') for c in calls]}"
    )
    # A model can mistype the long tmp path; the tool now answers that with an error
    # (UI sprint 099) and the model retries. Judge the first successful read.
    ok_results = [
        r
        for r in results
        if r["payload"].get("tool") == "inspect_record" and r["payload"].get("ok") is True
    ]
    assert ok_results, (
        f"no inspect_record call returned ok=True; got {[r['payload'] for r in results]}"
    )
    output = ok_results[0]["payload"].get("output") or {}
    assert output.get("format") == "summary"
    assert output.get("finalised") is True, f"seeded record should be finalised; got {output}"
    assert output.get("total_events", 0) > 0
    # Comprehension: the model's answer must state that the record IS finalised.
    answer = _last_answer(envs).lower()
    finalised_words = ("finalised", "finalized", "final", "completed")
    assert any(w in answer for w in finalised_words), (
        f"final answer must state the record finalised; got {answer!r}"
    )
    # Bonus safety: the model must NOT claim the record did NOT finalise.
    negative = (
        "did not finalise",
        "did not finalize",
        "not finalised",
        "not finalized",
        "unfinalised",
    )
    assert not any(w in answer for w in negative), (
        f"final answer contradicts the tool result (says NOT finalised); got {answer!r}"
    )
