# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""CI-mode wrapper for `session_topology` — sprint 209b.

`session_topology`'s production termination is `pause_await_input(Returned)` — the
correct shape for a driver conversation that yields between turns. That shape
does not finalise via a single `.run()`, so `scripts/gen_topology_records.py`
cannot generate a bundled CI record from `session_topology` alone.

`ci_session_topology(turns=[...])` composes over `session_topology` with three
additions: (1) a `driver_stepper` producer that yields one `UserMessage` per
firing, indexed by turn; (2) an `initial("driver_stepper", ...)` binding that
opens the first turn on `.run()`; (3) a `driver-stepper-on-returned` trigger that fires
the next turn's `UserMessage` on every turn end (`Returned`, or `Park` on an old record)
until the script exhausts. The
last entry in `turns` is `/exit`, which the existing `end-on-exit` trigger
converts to `SessionEnded(reason="user_exit")`; `session_topology`'s
termination is then overwritten with `threshold_count("SessionEnded", 1)` so
the run finalises cleanly on that event.

Everything else — the Structs, producers, triggers, views and the `_refuse_all_completed`
guard — comes from `session_topology` unchanged. The CI record is a byte-stable proof of the
wiring end to end.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from ... import api
from ...adapters import DeterministicResponder
from ..tool_loop.tools import CALCULATOR
from . import UserMessage, session_topology
from .vocabulary import (
    PRODUCER_KIND_DRIVER_STEPPER,
    SESSION_ENDED,
    TRIGGER_ID_DRIVER_STEPPER_ON_RETURNED,
    TURN_END_KINDS,
)

_CI_SESSION_ID = "s_CI"
_CI_SEED = "you are a companion in a terminal session"
_CI_WORKSPACE = "/tmp/session-ci"  # noqa: S108 — a label on the record; the CI tools (add, mul) touch no files
_CI_TURNS_DEFAULT: tuple[str, ...] = (
    "what is (2 + 3) times 4?",
    "and now what is 6 minus 5?",
    "/exit",
)


def _ci_stepper_factory(turns: tuple[str, ...]) -> Callable[[], Any]:
    async def _stepper(inp: Any) -> AsyncIterator[UserMessage]:
        turn_index = int(inp.get("turn_index", 0)) if hasattr(inp, "get") else 0
        if turn_index >= len(turns):
            return
        text = turns[turn_index]
        yield UserMessage(
            text=text,
            turn_index=turn_index,
            assembled_prompt="",
            slash_source="ci",
        )

    return lambda: _stepper


def ci_session_topology(
    *,
    turns: tuple[str, ...] = _CI_TURNS_DEFAULT,
    session_id: str = _CI_SESSION_ID,
    per_turn: str = "",
    role: str | None = None,
    role_repo_root: Path | None = None,
    bundle: str | None = None,
    parent_context: dict[str, Any] | None = None,
) -> Callable[[api.TopologyBuilder], None]:
    """Build a CI-mode wrapper around `session_topology` that finalises in one `.run()`.

    `turns` is the ordered list of `UserMessage.text` values the driver_stepper
    walks. The last entry MUST be `/exit`; the existing `end-on-exit` trigger
    routes it to `session_end` → `SessionEnded(reason="user_exit")`, and the
    wrapper's `threshold_count("SessionEnded", 1)` termination finalises the
    run on that event. The default script is three turns: two calculator
    questions plus `/exit`.
    """
    if not turns or turns[-1] != "/exit":
        raise api.RegistrationError(
            f"ci_session_topology: turns[-1] must be '/exit' (got {turns[-1]!r}); "
            "the CI record needs a clean finalisation via end-on-exit → SessionEnded."
        )

    def _ci_base() -> Any:
        return session_topology(
            driver=DeterministicResponder(seed=0),
            driver_name="deterministic",
            driver_context_tokens=4096,
            seed=_CI_SEED,
            tools=CALCULATOR,
            per_turn=per_turn,
            max_turns=200,
            turn_max_steps=8,
            session_id=session_id,
            workspace_path=_CI_WORKSPACE,
            script=None,
            role=role,
            role_repo_root=role_repo_root,
            bundle=bundle,
            parent_context=parent_context,
        )

    def topo(b: api.TopologyBuilder) -> None:
        _ci_base()(b)
        b.producer_kind(
            PRODUCER_KIND_DRIVER_STEPPER,
            schemas=[UserMessage],
            schema_version=1,
            factory=_ci_stepper_factory(turns),
            deterministic=True,
        )
        b.initial(PRODUCER_KIND_DRIVER_STEPPER, input={"turn_index": 0})
        b.trigger(
            TRIGGER_ID_DRIVER_STEPPER_ON_RETURNED,
            subscription=api.Subscription(kinds=TURN_END_KINDS),
            predicate=lambda ctx: int(ctx.event.payload.get("turn_index", 0)) + 1 < len(turns),
            starts=PRODUCER_KIND_DRIVER_STEPPER,
            input_builder=lambda ctx: {
                "turn_index": int(ctx.event.payload.get("turn_index", 0)) + 1
            },
            policy=api.PerEvent(),
        )
        # Overwrite session_topology's pause_await_input termination: the CI run
        # drives itself turn-by-turn and finalises on the /exit-produced SessionEnded.
        b.termination(api.threshold_count(SESSION_ENDED, 1))

    return topo
