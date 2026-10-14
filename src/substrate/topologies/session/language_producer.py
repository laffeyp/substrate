# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The `language` producer (session vocabulary v0.11 § W.3, sprint K310).

One run per turn that ends in a reply, between the final reply and Returned. Its input is the
turn's seq range (`language_input`); it reads the turn's events, and the session's earlier
LanguageProfile events, from its own record (`api.read_range`, the claim check the model step uses
for its history, § L), so the recorded input holds three numbers and no text. It emits the turn's
LanguageProfile events, then a LanguageDrift for each watched measure whose detector alarms on the
newest value.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import msgspec

from ... import api
from ...language import PREPROCESSING, profile
from ...language.drift import DEFAULT_DRIFT, WATCHED, detect
from .language_lines import relation_values, turn_pairings
from .vocabulary import (
    DELEGATE_SLASH_SOURCE,
    LANGUAGE_PROFILE,
    MODEL_REPLY,
    USER_MESSAGE,
    LanguagePairing,
    LanguageStream,
)

# The producer's input keys, written by `language_input` and read here only.
_TURN_INDEX = "turn_index"
_FROM_SEQ = "from_seq"
_TO_SEQ = "to_seq"


def language_input(turn_index: int, from_seq: int, to_seq: int) -> dict[str, int]:
    """The `language-on-reply` trigger's input: the turn, from its UserMessage to its final reply."""
    return {_TURN_INDEX: turn_index, _FROM_SEQ: from_seq, _TO_SEQ: to_seq}


def language_producer_factory(own_record: Callable[[], Path]) -> Callable[[], Any]:
    """The producer body factory; `own_record` names the run's record (the model step's)."""
    from . import LanguageDrift, LanguageProfile, ModelReply, UserMessage

    def _series(earlier: list[LanguageProfile], stream: LanguageStream) -> list[LanguageProfile]:
        """A stream's earlier profiles in record order: user messages, or final replies (the
        replies a relation `final` profile names)."""
        if stream is not LanguageStream.MODEL:
            return [p for p in earlier if p.stream is stream]
        finals = {
            p.source_seq
            for p in earlier
            if p.stream is LanguageStream.RELATION and p.pairing is LanguagePairing.FINAL
        }
        return [p for p in earlier if p.stream is stream and p.source_seq in finals]

    async def _language(inp: Any) -> AsyncIterator[Any]:
        root = own_record()
        turn, first, last = int(inp[_TURN_INDEX]), int(inp[_FROM_SEQ]), int(inp[_TO_SEQ])
        envelopes = list(api.read_range(root, first, last, resolve_blobs=True))
        message_env = next(e for e in envelopes if e["kind"] == USER_MESSAGE)
        message = msgspec.convert(message_env["payload"], UserMessage)
        replies = [
            (int(e["seq"]), msgspec.convert(e["payload"], ModelReply))
            for e in envelopes
            if e["kind"] == MODEL_REPLY
        ]

        def measured(stream: LanguageStream, seq: int, text: str, step: int | None) -> Any:
            out = profile(text)
            return LanguageProfile(
                stream=stream,
                turn_index=turn,
                source_seq=seq,
                step=step,
                pairing=None,
                library=out.library,
                preprocessing=PREPROCESSING,
                instrument_sha256=out.instrument_sha256,
                measures=out.measures,
            )

        delegate = message.slash_source == DELEGATE_SLASH_SOURCE
        user_stream = LanguageStream.DELEGATE if delegate else LanguageStream.USER
        user_profile = measured(user_stream, int(message_env["seq"]), message.text, None)
        reply_profiles = [
            measured(LanguageStream.MODEL, seq, reply.text, reply.step) for seq, reply in replies
        ]
        final_seq = replies[-1][0]
        relation_profiles = [
            LanguageProfile(
                stream=LanguageStream.RELATION,
                turn_index=turn,
                source_seq=final_seq,
                step=None,
                pairing=pairing,
                library=user_profile.library,
                preprocessing=PREPROCESSING,
                instrument_sha256=user_profile.instrument_sha256,
                measures=relation_values(message.text, reply_text),
            )
            for pairing, reply_text in turn_pairings([(r.text, r.stop_reason) for _, r in replies])
        ]
        for item in (user_profile, *reply_profiles, *relation_profiles):
            yield item

        earlier = [
            msgspec.convert(e["payload"], LanguageProfile)
            for e in api.read_range(root, 0, first - 1)
            if e["kind"] == LANGUAGE_PROFILE
        ]
        # The final reply is the turn's last: `language-on-reply` fires on it.
        newest = {LanguageStream.MODEL: reply_profiles[-1]}
        if not delegate:
            newest[LanguageStream.USER] = user_profile
        for stream, now in newest.items():
            series = [*_series(earlier, stream), now]
            for measure in WATCHED:
                if now.measures.get(measure) is None:
                    continue
                values = [float(v) for p in series if (v := p.measures.get(measure)) is not None]
                alarms = detect(values, DEFAULT_DRIFT)
                if alarms and alarms[-1].index == len(values) - 1:
                    yield LanguageDrift(
                        stream=stream,
                        measure=measure,
                        direction=alarms[-1].direction,
                        statistic=alarms[-1].statistic,
                        source_seq=now.source_seq,
                        series_length=len(values),
                        delta=DEFAULT_DRIFT.delta,
                        threshold=DEFAULT_DRIFT.threshold,
                        warmup=DEFAULT_DRIFT.warmup,
                    )

    return lambda: _language


__all__ = ["language_input", "language_producer_factory"]
