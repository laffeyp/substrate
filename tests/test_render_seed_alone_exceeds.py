# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 208 — seed-alone-exceeds guard fires exactly one SessionWarning at open.

Since K263 the `session_prompt` producer writes the warning. On a session with no prompt
source, the producer and its `initial` are registered only when
`_est_tokens(seed) + _est_tokens(per_turn) > driver_context_tokens * 0.6`. The producer
emits one `SessionWarning{kind:"seed_alone_exceeds"}` and completes, so the vocabulary-lock
§F #6 cadence "at most once per (session_id, condition_kind)" holds by construction — no
trigger re-fires it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.testing import assert_event
from substrate.topologies.session import SessionWarning, session_topology
from substrate.topologies.session.vocabulary import PRODUCER_KIND_SESSION_PROMPT

# A short scripted run inside one K-window: the documented exception to session_topology's
# record_root warning (UI sprint 107 states it here instead of letting it print on every run).
pytestmark = pytest.mark.filterwarnings(r"ignore:session_topology\(record_root=None\)")


def _open(
    *,
    seed: str,
    driver_context_tokens: int,
    per_turn: str = "",
    session_id: str = "sess-1",
) -> api.Registration:
    b = api.TopologyBuilder()
    factory = session_topology(
        driver=DeterministicResponder("x"),
        driver_name="deterministic",
        driver_context_tokens=driver_context_tokens,
        seed=seed,
        per_turn=per_turn,
        tools={},
        session_id=session_id,
        workspace_path="/tmp/x",
    )
    factory(b)
    return b.build()


def test_small_seed_does_not_arm_the_initial() -> None:
    reg = _open(seed="you are a companion", driver_context_tokens=32768)
    kinds = {i.kind for i in reg.initials}
    assert PRODUCER_KIND_SESSION_PROMPT not in kinds


def test_seed_exceeding_headroom_arms_the_initial() -> None:
    # driver_context_tokens=4096 → headroom 2457 tokens; seed of 20 000 chars ≈ 5000 tokens.
    reg = _open(seed="X" * 20000, driver_context_tokens=4096)
    kinds = {i.kind for i in reg.initials}
    assert PRODUCER_KIND_SESSION_PROMPT in kinds


def test_seed_plus_per_turn_crossing_boundary_arms_the_initial() -> None:
    # 12 000-char seed alone (~3000 tokens) fits under headroom (12288 * 0.6 = 7372).
    # Add a 20 000-char per_turn (~5000 tokens) → total 8000 tokens, exceeds headroom.
    reg = _open(seed="X" * 12000, per_turn="Y" * 20000, driver_context_tokens=12288)
    kinds = {i.kind for i in reg.initials}
    assert PRODUCER_KIND_SESSION_PROMPT in kinds


@pytest.mark.asyncio
async def test_session_prompt_emits_exactly_one_warning_and_completes(tmp_path: Path) -> None:
    """The registered `session_prompt` producer emits one `SessionWarning` and
    completes. Cadence "at most once per (session_id, condition_kind)" holds
    structurally — no trigger re-fires it. Test fires the producer inside a
    minimal topology built directly from `session_topology`'s registration.
    """
    reg = _open(
        seed="X" * 20000,
        driver_context_tokens=4096,
        session_id="sess-warn",
    )
    warning_reg = reg.producer_kinds[PRODUCER_KIND_SESSION_PROMPT]

    def solo_topo(b: api.TopologyBuilder) -> None:
        # Register with `[SessionWarning]` directly rather than destructuring
        # `warning_reg.schemas.values()` — reaching into ProducerKindReg's tuple shape
        # would rot if the substrate ever grew the tuple. With no prompt source, SessionWarning
        # is the one Struct the session_prompt producer emits.
        b.producer_kind(
            PRODUCER_KIND_SESSION_PROMPT,
            schemas=[SessionWarning],
            schema_version=1,
            factory=warning_reg.factory,
            deterministic=True,
        )
        b.initial(PRODUCER_KIND_SESSION_PROMPT, input={})
        b.termination(api.threshold_count("SessionWarning", 1))

    record_root = tmp_path / "sess-warn"
    await api.Runtime(record_root).run(solo_topo)
    # Exactly-one contract via assert_sequence over the payload-carrying kinds.
    payload_kinds = [
        e["kind"] for e in api.read_record(record_root) if not e["kind"].startswith("substrate.")
    ]
    assert payload_kinds == ["SessionWarning"]
    # Payload assertions via the F-API-4 primitive. `SessionWarning.kind` collides
    # with `assert_event`'s positional `kind` parameter, so filter on the fields
    # the primitive can address and verify `payload["kind"]` on the returned
    # envelope directly.
    warning = assert_event(
        record_root,
        "SessionWarning",
        session_id="sess-warn",
        driver_context_tokens=4096,
    )
    assert warning["payload"]["kind"] == "seed_alone_exceeds"
    assert warning["payload"]["seed_tokens"] > warning["payload"]["driver_context_tokens"] * 0.6
    # The session_prompt producer is declared deterministic; the record must replay byte-identical.
    api.assert_replayable(record_root, "3a")
