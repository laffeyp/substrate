# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 206 — session_topology refuses all_completed at build time.

`all_completed` compares started vs ended Producer counts. A pausable topology on
`all_completed` hangs on resume: the paused Producer's ProducerStarted has no
durable end across the pause, so `completed >= started` cannot hold on resume
(kernel/policies.py:90-97). The refusal must catch direct use and every depth
of composition (`any_of(all_completed(), ...)`, `any_of(any_of(all_completed()))`).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.session import _refuse_all_completed, session_topology

# A short scripted run inside one K-window: the documented exception to session_topology's
# record_root warning (UI sprint 107 states it here instead of letting it print on every run).
pytestmark = pytest.mark.filterwarnings(r"ignore:session_topology\(record_root=None\)")


def _open_scaffold() -> tuple[api.TopologyBuilder, "api.TerminationPolicy | None"]:
    """Build the session topology and return the composed termination policy.

    The scaffold's `_refuse_all_completed` is called against a policy that this
    test constructs; the topology's own good termination is used to prove the
    refusal fires only on `all_completed` and lets the built-in composition pass.
    """
    b = api.TopologyBuilder()
    factory = session_topology(
        driver=DeterministicResponder("x"),
        driver_name="deterministic",
        driver_context_tokens=4096,
        seed="hi",
        tools={},
        session_id="sess-1",
        workspace_path="/tmp/x",
    )
    factory(b)
    reg = b.build()
    return b, reg.termination


def test_scaffold_termination_passes_refusal() -> None:
    _, termination = _open_scaffold()
    assert termination is not None
    _refuse_all_completed(termination)


def test_direct_all_completed_is_refused() -> None:
    policy = api.all_completed()
    with pytest.raises(api.RegistrationError) as info:
        _refuse_all_completed(policy)
    assert "all_completed" in str(info.value)
    assert "policies.py::all_completed" in str(info.value)


def test_all_completed_inside_any_of_is_refused() -> None:
    policy = api.any_of(api.all_completed(), api.threshold_count("SessionEnded", 1))
    with pytest.raises(api.RegistrationError):
        _refuse_all_completed(policy)


def test_all_completed_inside_nested_any_of_is_refused() -> None:
    policy = api.any_of(
        api.any_of(api.all_completed(), api.quiescence_with_watchdog(1.0)),
        api.threshold_count("SessionEnded", 1),
    )
    with pytest.raises(api.RegistrationError):
        _refuse_all_completed(policy)


def test_all_completed_inside_all_of_is_refused() -> None:
    policy = api.all_of(api.all_completed(), api.threshold_count("SessionEnded", 1))
    with pytest.raises(api.RegistrationError):
        _refuse_all_completed(policy)


def test_session_topology_refuses_all_completed_when_wired_in_place() -> None:
    """A composer that reaches `session_topology`'s termination path with `all_completed`
    inside it raises at build time. The scaffolded topology composes its own good
    termination; simulate the failure by monkey-patching `api.any_of` on the module
    to return a policy whose name contains `all_completed`.
    """
    import substrate.topologies.session as session_mod

    poisoned = api.all_completed()

    with patch.object(session_mod.api, "any_of", lambda *args: poisoned):
        b = api.TopologyBuilder()
        factory = session_topology(
            driver=DeterministicResponder("x"),
            driver_name="deterministic",
            driver_context_tokens=4096,
            seed="hi",
            tools={},
            session_id="sess-1",
            workspace_path="/tmp/x",
        )
        with pytest.raises(api.RegistrationError) as info:
            factory(b)
        assert "all_completed" in str(info.value)


def test_similar_name_is_not_refused() -> None:
    """Word-boundary discipline: a name that merely contains the substring
    `all_completed` inside a larger word must pass. Regression on the simple
    `.contains` check the first draft used.
    """
    from substrate.kernel.policies import Decision, TerminationPolicy

    innocuous = TerminationPolicy(
        "all_completed_kids",
        lambda ctx: Decision.CONTINUE,
    )
    _refuse_all_completed(innocuous)


def test_termination_name_lists_all_ten_triggers_and_no_all_completed() -> None:
    """The scaffolded termination's name string documents the composition and
    proves the refusal did not fire on the good policy.
    """
    _, termination = _open_scaffold()
    assert termination is not None
    assert "pause_await_input" in termination.name
    assert "threshold_count(SessionEnded,1)" in termination.name
    assert "all_completed" not in termination.name
