"""UI sprint 107: a kind constant is its event struct's class name, pinned here.

The constants live in leaf modules (tool_loop/kinds.py, session/vocabulary.py) so any module can
import them without a cycle; that leaves them as strings, so this test is what keeps each one
equal to the struct whose envelopes it names.
"""

from __future__ import annotations

from substrate.topologies import session as s
from substrate.topologies import tool_loop as tl
from substrate.topologies.session import vocabulary as sv
from substrate.topologies.tool_loop import kinds as tk


def test_tool_loop_kinds_match_their_structs() -> None:
    assert tk.TOOL_CALL == tl.ToolCall.__name__
    assert tk.TOOL_RESULT == tl.ToolResult.__name__
    assert tk.FINAL_ANSWER == tl.FinalAnswer.__name__
    assert tk.TOOL_PROGRESS == tl.ToolProgress.__name__


def test_session_kinds_match_their_structs() -> None:
    pairs = {
        sv.SESSION_STARTED: s.SessionStarted,
        sv.USER_MESSAGE: s.UserMessage,
        sv.MODEL_REPLY: s.ModelReply,
        sv.PARK: s.Park,
        sv.SESSION_ENDED: s.SessionEnded,
        sv.SESSION_END_REQUESTED: s.SessionEndRequested,
        sv.BACKGROUND_TASK_ENDED: s.BackgroundTaskEnded,
    }
    for name, struct in pairs.items():
        assert name == struct.__name__, (name, struct.__name__)
