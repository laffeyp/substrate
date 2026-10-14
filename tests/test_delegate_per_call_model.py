# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 213a — path 2: `delegate(task, model=...)` spawns a child on the
resolved driver, not the parent's default.

`model_resolver` is a caller-injectable `Callable[[str], Responder]`. The daemon
(substrate-ui/server.py::_agent_models) supplies a richer one that knows the CLI
shells + rate-limited wrappers; substrate ships the small `_default_model_resolver`
fallback (deterministic → DeterministicResponder; every other name → OllamaResponder).
This file exercises both.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate.adapters import DeterministicResponder, OllamaResponder, Responder
from substrate.topologies.tool_loop.delegate import (
    _default_model_resolver,
    make_delegate,
)


def test_default_resolver_maps_deterministic_to_stub(tmp_path: Path) -> None:
    r = _default_model_resolver("deterministic")
    assert isinstance(r, DeterministicResponder)


def test_default_resolver_maps_any_other_name_to_ollama(tmp_path: Path) -> None:
    r = _default_model_resolver("llama3.2:1b")
    assert isinstance(r, OllamaResponder)


def test_per_call_model_swaps_the_child_driver(tmp_path: Path) -> None:
    """The parent's `responder=` fixes one driver at construction time; a
    per-call `model` argument rebinds a fresh child_factory around the resolved
    Responder, so the child runs on the caller's chosen driver."""
    seen: list[str] = []

    def resolver(name: str) -> Responder:
        seen.append(name)
        return DeterministicResponder(seed=42)

    d = make_delegate(
        responder=DeterministicResponder(seed=0),
        root=tmp_path,
        model_resolver=resolver,
    )
    result = d.run([{"task": "hi", "model": "deterministic"}])
    assert result["answer"] is not None
    assert result["via"] == "different_driver:deterministic"
    assert seen == ["deterministic"]


def test_per_call_model_unknown_returns_typed_failure(tmp_path: Path) -> None:
    """A resolver that raises on unknown model surfaces as a typed ValueError.
    The tool_loop factory turns the raise into `ToolResult(ok=False, error=...)`.
    """

    def strict_resolver(name: str) -> Responder:
        raise KeyError(f"no such model: {name}")

    d = make_delegate(
        responder=DeterministicResponder(seed=0),
        root=tmp_path,
        model_resolver=strict_resolver,
    )
    with pytest.raises(ValueError, match="unknown model"):
        d.run([{"task": "hi", "model": "nonexistent-model"}])


def test_per_call_model_fallback_uses_default_resolver(tmp_path: Path) -> None:
    """A `make_delegate(...)` without a `model_resolver=` kwarg falls back to
    `_default_model_resolver`. Any name not `deterministic` is treated as an
    Ollama tag — the child is CONSTRUCTED against that Responder even if the
    Ollama daemon is unreachable (the daemon call fires later on the child's
    first turn; construction is cheap).
    """
    d = make_delegate(
        responder=DeterministicResponder(seed=0),
        root=tmp_path,
    )
    # `deterministic` → DeterministicResponder — child actually runs.
    result = d.run([{"task": "hi", "model": "deterministic"}])
    assert result["via"] == "different_driver:deterministic"
    assert result["answer"] is not None


def test_bare_string_task_still_omits_via(tmp_path: Path) -> None:
    """The via field lands only on paths 1/2/3. Path 4 (bare task, no per-call
    args) keeps the pre-213 shape `{answer, child_root, steps}` — the sprint-212
    backwards-compat contract holds.
    """
    d = make_delegate(responder=DeterministicResponder(seed=0), root=tmp_path)
    result = d.run(["hello"])
    assert "via" not in result
    assert set(result.keys()) == {"answer", "child_root", "steps"}
