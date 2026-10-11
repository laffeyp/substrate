# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Session-topology Views (piece A, sprint 205).

`TurnHistory` keeps each turn's seq span and size, for the model step's history window.

`FragmentCohort` owns turn-scoping for the model step's prompt. Session-open fragments (role,
bundle_*, tools_suite, parent_context), written once by `session_prompt`, land in every prompt.
Turn-scoped fragments (an interrupt directive) belong only to the next prompt: the cohort
clears its turn slice on every PromptComposed, which the model step records before each call.
"""

from __future__ import annotations

from typing import Any

from ...types import Event, Subscription
from .vocabulary import (
    PROMPT_COMPOSED,
    PROMPT_FRAGMENT,
    SESSION_CHANGED,
    SESSION_STARTED,
    SESSION_OPEN_SOURCES,
    TURN_SCOPED_SOURCES,
    parse_prompt_source,
)


def producer_kind_from_lifecycle_payload(payload: Any) -> str | None:
    """Read `producer.kind` off a `substrate.ProducerStarted / Failed / Cancelled` payload.

    The lifecycle envelopes carry `payload["producer"]` as `{kind, instance, parent}` per
    kernel §4. The session's trigger predicates filter by that kind; this helper is the one
    source of truth for the defensive `isinstance` ladder.
    """
    ref = payload.get("producer") if isinstance(payload, dict) else None
    return ref.get("kind") if isinstance(ref, dict) else None


class TurnHistory:
    """Each turn's seq span and estimated rendered size, in record order (K261, K268).

    The model triggers choose the prompt's history window from these sizes and hand the model step
    a ticket to the kept seq range of the record; the model step reads those events with
    `api.read_range`. The view keeps only the current turn's events (to price it as it grows);
    finished turns are a span and a size.
    """

    deterministic = True

    def __init__(self, kinds: frozenset[str]) -> None:
        self.subscription = Subscription(kinds=kinds)
        self._turns: list[list[int]] = []  # [from_seq, to_seq, cost]
        self._current: list[dict[str, Any]] = []

    def update(self, event: Event) -> None:
        from .transcript import turn_cost
        from .vocabulary import USER_MESSAGE

        env = {"seq": event.seq, "kind": event.kind, "payload": event.payload}
        if event.kind == USER_MESSAGE:
            self._current = [env]
            self._turns.append([event.seq, event.seq, 0])
        elif self._current:
            self._current.append(env)
        else:
            return  # before the first UserMessage: not part of any turn
        self._turns[-1][1] = event.seq
        self._turns[-1][2] = turn_cost(self._current)

    def value(self) -> list[tuple[int, int, int]]:
        return [(a, b, c) for a, b, c in self._turns]


class FragmentCohort:
    """Turn-scoped view over `PromptFragment` events.

    Two internal buckets. `_session_open` keeps every session-open fragment in arrival order;
    `session_prompt` writes them once per session (a bundle's `extends` chain gives one
    methodology fragment per link), and a resume writes none (K265). Before K265 it kept one slot
    per source and the newest won, which dropped all but the last link's methodology. `_turn`
    accumulates turn-scoped fragments in arrival order and clears on every `PromptComposed`, so a
    fragment reaches exactly one prompt.

    `value()` returns a merged list of `(seq, payload)` tuples ordered by seq. The model
    triggers pass them as the step's `fragments`, and PromptComposed records their seqs in
    `fragment_seqs`, so a reader can trace a prompt back to every source PromptFragment.

    An unknown source value is dropped with no state change. Deterministic
    (payload-derived, no wall-clock read); the compose-emit boundary is a
    typed record event, not an external timer.
    """

    deterministic = True

    def __init__(self) -> None:
        self.subscription = Subscription(kinds=frozenset({PROMPT_FRAGMENT, PROMPT_COMPOSED}))
        self._session_open: list[tuple[int, dict[str, Any]]] = []
        self._turn: list[tuple[int, dict[str, Any]]] = []

    def update(self, event: Event) -> None:
        payload = event.payload if isinstance(event.payload, dict) else {}
        if event.kind == PROMPT_COMPOSED:
            self._turn.clear()
            return
        raw_source = payload.get("source")
        if not isinstance(raw_source, str):
            return
        source = parse_prompt_source(raw_source)
        if source is None:
            return
        entry = (event.seq, dict(payload))
        if source in SESSION_OPEN_SOURCES:
            self._session_open.append(entry)
        elif source in TURN_SCOPED_SOURCES:
            self._turn.append(entry)

    def value(self) -> list[tuple[int, dict[str, Any]]]:
        merged = _newest_generation(self._session_open) + self._turn
        merged.sort(key=lambda item: item[0])
        return merged


def _generation(payload: dict[str, Any]) -> int:
    provenance = payload.get("provenance")
    raw = provenance.get("generation") if isinstance(provenance, dict) else None
    return int(raw) if isinstance(raw, int) else -1


def _newest_generation(
    entries: list[tuple[int, dict[str, Any]]],
) -> list[tuple[int, dict[str, Any]]]:
    """K274: a SessionChanged of the bundle or per_turn writes those sources again, each fragment
    carrying the change's seq as `generation`. For each source keep only its newest generation;
    fragments written at session open are generation -1."""
    newest: dict[str, int] = {}
    for _seq, payload in entries:
        source = str(payload.get("source", ""))
        newest[source] = max(newest.get(source, -1), _generation(payload))
    return [
        (seq, payload)
        for seq, payload in entries
        if _generation(payload) == newest[str(payload.get("source", ""))]
    ]


class SessionSettings:
    """The last recorded driver, bundle, reminder line and date (K274). The model step compares
    them with the session's current settings and writes a SessionChanged for each that differs.

    Folds `SessionStarted` (driver, bundle, the baseline's date), the newest `per_turn` fragment,
    and `SessionChanged` (the new value). A field never recorded is absent, and absent fields
    are not compared."""

    deterministic = True

    def __init__(self) -> None:
        self.subscription = Subscription(
            kinds=frozenset({SESSION_STARTED, PROMPT_FRAGMENT, SESSION_CHANGED})
        )
        self._settings: dict[str, str] = {}

    def update(self, event: Event) -> None:
        payload = event.payload if isinstance(event.payload, dict) else {}
        if event.kind == SESSION_STARTED:
            self._settings["driver"] = str(payload.get("driver_model") or "")
            self._settings["bundle"] = str(payload.get("bundle") or "")
            self._settings.setdefault("per_turn", "")
            baseline = payload.get("baseline")
            if isinstance(baseline, dict) and baseline.get("date"):
                self._settings["date"] = str(baseline["date"])
        elif event.kind == PROMPT_FRAGMENT:
            if parse_prompt_source(str(payload.get("source", ""))) == "per_turn":
                self._settings["per_turn"] = str(payload.get("text", ""))
        elif event.kind == SESSION_CHANGED:
            self._settings[str(payload.get("field", ""))] = str(payload.get("new", ""))

    def value(self) -> dict[str, str]:
        return dict(self._settings)
