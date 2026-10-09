# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""best_of_n_verified — generate N candidates, verify each, select the survivor (application-parity W1.2).

The agent-CLI "best of N with verification" pattern, as a general application on real input. It
COMPOSES the existing `best_of_n_correction` loop: a drafter model fans out N candidates, each is
verified, and the built-in judge selects the first that passes (feeding failures back for another
round, up to the budget). No new loop, no new vocabulary — the Draft/Candidate/Verdict/Solved
records are best_of_n's.

Verification is CALLER-SUPPLIED, exactly as best_of_n intends: pass a deterministic `check(response)
-> (passed, reason)` (substrate's preferred, when the answer is mechanically checkable), or an
INDEPENDENT judge Responder (a different model family than the drafter, per finding #42 — LLM-as-judge
with the judge disjoint from the generator, not a model grading its own work) for prose/design/
negotiation where no mechanical check exists. Either way the loop and the record are identical.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable
from typing import Any

from ... import api
from ...adapters import ModelUsage, Responder, call_responder_metered
from ..best_of_n import Candidate, Verdict, best_of_n_correction

# A deterministic verify: given the candidate text, return (passed, reason). The substrate-preferred
# verifier when the answer is mechanically checkable — no model in the validator slot.
Check = Callable[[str], tuple[bool, str]]

_PASS = "PASS"  # noqa: S105 — a verdict word, not a credential
_PASS_RE = re.compile(r"\bPASS\b", re.IGNORECASE)
_FAIL_RE = re.compile(r"\bFAIL\b", re.IGNORECASE)


def _verdict_passed(text: str) -> tuple[bool, str]:
    """Read PASS/FAIL from a judge reply ROBUSTLY (F-9). `startswith("PASS")` failed a correct candidate
    whenever the model preambled ("Sure! PASS — …"), which kimi and glm both do (KIT_DIARY #32: prefer
    enforcement over a prompt rule). Take whichever token appears FIRST; on neither token, FAIL CLOSED —
    a verifier must not pass what it cannot confirm — carrying the raw reply so the record stays legible."""
    p, f = _PASS_RE.search(text), _FAIL_RE.search(text)
    reason = text.strip()
    if p and (f is None or p.start() < f.start()):
        return True, reason
    if f is not None:
        return False, reason
    return False, f"(unparseable verdict — no PASS/FAIL token: {reason[:120]})"


def _drafter_factory(task: str, drafter: Responder) -> Callable[[], Any]:
    async def draft(inp: Any) -> AsyncIterator[Any]:
        rnd = int(inp.get("round", 1)) if hasattr(inp, "get") else 1
        slot = int(inp.get("slot", 0)) if hasattr(inp, "get") else 0
        context = str(inp.get("context", "")) if hasattr(inp, "get") else ""
        prompt = task
        if context:
            prompt += f"\n\nA PRIOR attempt was REJECTED. Address the feedback and answer again:\n{context}"
        # death-resilience as a SET (F-4 / KIT_DIARY #16): a failed drafter call must still emit a
        # Candidate — otherwise this slot produces no Verdict, the judge never sees n verdicts, and the
        # round stalls to the silent-no-answer terminal. A failed draft becomes a failing candidate.
        try:
            response, usage = await call_responder_metered(drafter, prompt)
            yield usage  # metered onto the record (inert) — only on a real call
        except Exception as exc:  # noqa: BLE001 — a model failure becomes a recorded candidate; K254 retires this (ledger F127, F189)
            response = f"(draft failed: {type(exc).__name__})"
        yield Candidate(round=rnd, slot=slot, response=response)

    return lambda: draft


def _verify_prompt(task: str, response: str) -> str:
    return (
        f"You are an independent verifier — you did NOT write the answer below. Judge whether it "
        f"correctly and completely satisfies the task. Reply with '{_PASS}' on the first line if it "
        f"does, or 'FAIL' on the first line if it does not, then one sentence of reason.\n\n"
        f"TASK:\n{task}\n\nANSWER:\n{response}"
    )


def _validator_factory(task: str, verify: Check | Responder) -> Callable[[], Any]:
    async def validate(inp: Any) -> AsyncIterator[Verdict | ModelUsage]:
        rnd = int(inp.get("round", 1)) if hasattr(inp, "get") else 1
        slot = int(inp.get("slot", 0)) if hasattr(inp, "get") else 0
        response = str(inp.get("response", "")) if hasattr(inp, "get") else ""
        # the verify seam gets the SET guard too: a raising check or a failed judge call still emits a
        # Verdict (a failed one), so the judge always sees n verdicts and the round never stalls.
        source = "check"
        try:
            if callable(verify) and not isinstance(verify, Responder):
                passed, reason = verify(response)  # deterministic check — no model, no usage
            else:
                # an INDEPENDENT judge model (finding #42: judge-family disjoint from the drafter). Metered
                # onto the record (F-18) so BOTH the draft and the verify model calls are assayable — the
                # "verified with an independent judge" claim is then checkable from the record itself.
                source = (
                    "model"  # C-5: mark the verdict source so returncode reads as a proxy, not exit
                )
                verdict_text, usage = await call_responder_metered(
                    verify, _verify_prompt(task, response)
                )
                yield usage
                passed, reason = _verdict_passed(verdict_text)
        except Exception as exc:  # noqa: BLE001 — a model failure becomes a recorded candidate; K254 retires this (ledger F127, F189)
            passed, reason = False, f"(verify failed: {type(exc).__name__})"
        yield Verdict(
            round=rnd,
            slot=slot,
            passed=passed,
            returncode=0 if passed else 1,
            summary=reason,
            source=source,
        )

    return lambda: validate


def best_of_n_verified_topology(
    task: str,
    *,
    drafter: Responder,
    verify: Check | Responder,
    n: int = 3,
    max_rounds: int = 2,
    deterministic: bool = False,
) -> Callable[[api.TopologyBuilder], None]:
    """Best-of-N with verification over `task`. `drafter` generates candidates; `verify` is either a
    deterministic `check(response) -> (passed, reason)` or an independent judge Responder. Composes
    `best_of_n_correction` with the default select-first judge — the loop, correction, and record are
    best_of_n's; this only supplies the drafter + verifier factories (the work).

    Raises ValueError on `n < 1`: with no candidates the seeder emits nothing, nothing is drafted or
    verified, and the run finalises via `all_completed` with NO terminal application event — the same
    silent-no-answer class as research_sweep's empty-corpus hole (review C-8; the empty-input guard is a
    CLASS, applied to every application, not just the one the first fix touched — KIT_DIARY #16)."""
    if n < 1:
        raise ValueError(f"best_of_n_verified_topology: n must be >= 1, got {n}")

    def topo(b: api.TopologyBuilder) -> None:
        best_of_n_correction(
            b,
            n=n,
            max_rounds=max_rounds,
            draft_factory=_drafter_factory(task, drafter),
            validate_factory=_validator_factory(task, verify),
            # the judge branch meters its call — declare ModelUsage so the emission validates (F-18)
            validator_schemas=[Verdict, ModelUsage],
            deterministic=deterministic,
        )

    return topo
