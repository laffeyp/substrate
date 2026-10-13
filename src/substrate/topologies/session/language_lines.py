# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Language lines: every text of a session record, measured (sprint 308; research round 5).

A read-only projection. It reads a record, adds nothing to it, and yields one dict per measured
text: each user message, each model reply, each turn's relation (twice: with the final reply, and
with all the turn's replies), and each composed prompt. `line_json` writes a line as canonical JSON,
so the same record always gives the same bytes.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

from ... import api
from ...constants import RUN_STARTED
from ...language import parse, profile, words
from ...language import relation as rel
from ...language.measures import MIN_WORDS_ENTROPY, MIN_WORDS_LSM
from .vocabulary import (
    DELEGATE_SLASH_SOURCE,
    LanguagePairing as Pairing,
    LanguageStream as Stream,
    MODEL_REPLY,
    PROMPT_COMPOSED,
    SESSION_CHANGE_FIELDS,
    SESSION_CHANGED,
    SESSION_STARTED,
    USER_MESSAGE,
    StopReason,
)

# The trailing window: back to the largest one-text minimum (research round 5, "Windows").
WINDOW_WORDS = MIN_WORDS_ENTROPY


def _provenance(p: Mapping[str, Any]) -> dict[str, Any]:
    return {
        k: p[k]
        for k in (
            "library",
            "preprocessing",
            "instrument_sha256",
            "params",
            "minimums",
            "lexicons",
            "compressor",
        )
    }


class _Window:
    """One stream's latest texts, back to WINDOW_WORDS words."""

    def __init__(self) -> None:
        self.texts: list[tuple[str, int]] = []

    def add(self, text: str) -> None:
        self.texts.append((text, len(words(parse(text)))))
        total = 0
        for i in range(len(self.texts) - 1, -1, -1):
            total += self.texts[i][1]
            if total >= WINDOW_WORDS:
                self.texts = self.texts[i:]
                return

    def joined(self) -> str:
        return "\n\n".join(t for t, _ in self.texts)

    def size(self) -> dict[str, int]:
        return {"window_words": sum(n for _, n in self.texts), "window_texts": len(self.texts)}


def language_lines(record: Path | Iterable[Mapping[str, Any]]) -> Iterator[dict[str, Any]]:
    """One measured line per text of a session record, in record order."""
    events: Iterable[Mapping[str, Any]] = (
        api.read_record(record, resolve_blobs=True) if isinstance(record, Path) else record
    )
    keys: dict[str, Any] = {}
    settings: dict[str, Any] = {}
    guidance: str | None = None
    windows = {Stream.USER: _Window(), Stream.MODEL: _Window()}
    turns: dict[int, dict[str, Any]] = {}

    def base(e: Mapping[str, Any], stream: Stream) -> dict[str, Any]:
        return {
            **keys,
            **{f"setting_{k}": v for k, v in sorted(settings.items())},
            "seq": e["seq"],
            "t": e["t"],
            "stream": str(stream),
            "guidance_sha256": guidance,
        }

    def relation_lines(turn: dict[str, Any]) -> Iterator[dict[str, Any]]:
        replies: list[Mapping[str, Any]] = turn["replies"]
        if not replies:
            return
        # Replies recorded before ModelReply carried stop_reason have none; the last reply is final.
        finals = [
            r for r in replies if r.get("stop_reason") in (StopReason.END_TURN, StopReason.WRAP_UP)
        ]
        user = parse(turn["text"])
        for pairing, reply_text in (
            (Pairing.FINAL, (finals or replies)[-1]["text"]),
            (Pairing.TURN, "\n\n".join(r["text"] for r in replies)),
        ):
            reply = parse(reply_text)
            values: dict[str, Any] = {
                "length_ratio": rel.length_ratio(user, reply),
                "lexical_echo": rel.lexical_echo(user, reply),
                **{f"phrase_copy_{k}": v for k, v in rel.phrase_copy(user, reply).items()},
                "ncd": rel.ncd(turn["text"], reply_text),
                **rel.lsm(user, reply),
                **{
                    f"window_{k}": v
                    for k, v in rel.lsm(
                        parse(windows[Stream.USER].joined()),
                        parse(windows[Stream.MODEL].joined()),
                        MIN_WORDS_LSM,
                    ).items()
                },
            }
            yield {
                **turn["base"],
                **_provenance(profile("")),
                "turn": turn["turn"],
                "pairing": str(pairing),
                "values": values,
            }

    pending: int | None = None  # the turn whose relation lines are due
    for e in events:
        kind, p = e["kind"], e["payload"]
        if pending is not None and kind == USER_MESSAGE:
            yield from relation_lines(turns[pending])
            pending = None
        if kind == RUN_STARTED:
            keys["topology"] = p.get("name")
        elif kind == SESSION_STARTED:
            keys.update(
                session_id=p["session_id"],
                driver_model=p["driver_model"],
                model_class=p.get("model_class", ""),
                workspace_shape=p["workspace_shape"],
            )
            settings.update({f: p[f] for f in SESSION_CHANGE_FIELDS if f in p})
            settings["driver"] = p["driver_model"]
        elif kind == SESSION_CHANGED and p["field"] in SESSION_CHANGE_FIELDS:
            settings[p["field"]] = p["new"]
        elif kind == PROMPT_COMPOSED:
            system = p.get("system", "")
            guidance = hashlib.sha256(system.encode("utf-8")).hexdigest()
            text_profile, system_profile = profile(p["text"]), profile(system)
            yield {
                **base(e, Stream.COMPOSED),
                **_provenance(text_profile),
                "values": {"text": text_profile["measures"], "system": system_profile["measures"]},
            }
        elif kind == USER_MESSAGE:
            delegate = p.get("slash_source") == DELEGATE_SLASH_SOURCE
            stream = Stream.DELEGATE if delegate else Stream.USER
            if not delegate:
                windows[Stream.USER].add(p["text"])
            turns[p["turn_index"]] = {"turn": p["turn_index"], "text": p["text"], "replies": []}
            yield _text_line(
                e, base(e, stream), p["text"], windows[Stream.USER] if not delegate else None
            ) | {
                "turn": p["turn_index"],
                "slash_source": p.get("slash_source"),
            }
        elif kind == MODEL_REPLY:
            windows[Stream.MODEL].add(p["text"])
            turn = turns.setdefault(
                p["turn_index"], {"turn": p["turn_index"], "text": "", "replies": []}
            )
            turn["replies"].append(p)
            # The relation lines carry the keys as they stand at the turn's last reply.
            turn["base"] = base(e, Stream.RELATION)
            pending = p["turn_index"]
            yield _text_line(e, base(e, Stream.MODEL), p["text"], windows[Stream.MODEL]) | {
                "turn": p["turn_index"],
                "step": p.get("step"),
                "stop_reason": p.get("stop_reason"),
                # `usage` since ModelReply gained it; `model_usage` in older records.
                "reply_model": (p.get("usage") or p.get("model_usage") or {}).get("model"),
            }
    if pending is not None:
        yield from relation_lines(turns[pending])


def _text_line(
    e: Mapping[str, Any], head: dict[str, Any], text: str, window: _Window | None
) -> dict[str, Any]:
    own = profile(text)
    values: dict[str, Any] = {"text": own["measures"]}
    if window is not None:
        values["window"] = {**profile(window.joined())["measures"], **window.size()}
    return {**head, **_provenance(own), "values": values, "partials": own["partials"]}


def line_json(line: Mapping[str, Any]) -> str:
    """One line as canonical JSON: sorted keys, no NaN, UTF-8 as written."""
    return json.dumps(
        line, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
