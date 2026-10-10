# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K264: every session trigger is named `<what it starts>-on-<event>`.

Before: five patterns (`run-tool`, `continue`, `wrap-up`, `emit-interrupt-fragment`,
`advance-on-park`, `end-on-cap`, …), and `end-on-cap` ended the session with `reason=timeout`
for a cap that counts turns. Kind names sat beside their constants as raw strings (lens F096,
F103, F104).
"""

from __future__ import annotations

import re
from pathlib import Path

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session.ci import ci_session_topology
from substrate.topologies.session.vocabulary import (
    LEGACY_SESSION_END_REASONS,
    SESSION_TRIGGER_IDS,
    SessionEndReason,
)
from substrate.topologies.tool_loop.tools import CALCULATOR

_FORM = re.compile(r"^[a-z]+(-[a-z]+)*-on-[a-z]+(-[a-z]+)*$")
_PACKAGE = Path(__file__).resolve().parent.parent / "src/substrate/topologies/session"


def _trigger_ids(topo: object) -> list[str]:
    b = api.TopologyBuilder()
    topo(b)  # type: ignore[operator]
    return [t.id for t in b.build().triggers]


def test_every_declared_trigger_id_has_the_form() -> None:
    bad = sorted(t for t in SESSION_TRIGGER_IDS if not _FORM.match(t))
    assert not bad, bad


def test_the_registered_triggers_are_the_declared_ones(tmp_path: Path) -> None:
    session = session_topology(
        driver=DeterministicResponder(seed=0),
        driver_name="deterministic",
        driver_context_tokens=8_192,
        seed="SEED",
        tools=dict(CALCULATOR),
        session_id="s264",
        workspace_path=str(tmp_path),
        role="reviewer",
        first_turn_user_message=UserMessage(
            text="hi", turn_index=0, assembled_prompt="", slash_source="chat"
        ),
    )
    ids = set(_trigger_ids(session)) | set(_trigger_ids(ci_session_topology()))
    # The SessionStarted instrument's trigger is the kernel's, named after its producer.
    ids.discard("session_started")
    assert ids == set(SESSION_TRIGGER_IDS)


def test_the_turn_cap_reason_names_turns_and_old_records_still_read() -> None:
    assert SessionEndReason.TURN_CAP == "turn_cap"
    assert LEGACY_SESSION_END_REASONS == {"timeout": "turn_cap"}
    assert "timeout" not in {r.value for r in SessionEndReason}


def test_no_raw_kind_literal_in_the_session_package() -> None:
    """Kind names come from constants. Docstrings, comments, `__all__` and the forward reference
    `"UserMessage"` in a type annotation are text, not kind names, and are skipped."""
    kinds = (
        "ToolResult|ToolCall|FinalAnswer|PromptComposed|PromptFragment|InterruptRequested|Park"
        "|Returned|ModelReply|SessionEnded|SessionWarning|SessionStarted|TranscriptCompacted"
    )
    pattern = re.compile(rf'"({kinds})"')
    hits: list[str] = []
    for path in sorted(_PACKAGE.glob("*.py")):
        if path.name == "vocabulary.py":
            continue
        in_doc = False
        for n, line in enumerate(path.read_text().splitlines(), 1):
            stripped = line.strip()
            if stripped.count('"""') == 1:
                in_doc = not in_doc
                continue
            if in_doc or stripped.startswith(("#", '"""')) or re.fullmatch(r'"\w+",', stripped):
                continue
            if pattern.search(line.split("#")[0]):
                hits.append(f"{path.name}:{n}: {stripped}")
    assert not hits, hits
