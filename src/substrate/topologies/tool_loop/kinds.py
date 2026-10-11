"""The tool loop's envelope kind names (a kind is its event struct's class name).

UI sprint 107: these names were retyped as string literals in eight comparisons across the CLI,
the delegate tool, the agency scorer and the session transcript. A leaf module, so any of them can
import it without a cycle; `tests/test_kind_constants_match_structs_107.py` pins each constant to
its struct's `__name__`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

TOOL_CALL: Final[str] = "ToolCall"
TOOL_RESULT: Final[str] = "ToolResult"
FINAL_ANSWER: Final[str] = "FinalAnswer"
TOOL_PROGRESS: Final[str] = "ToolProgress"


class ToolCallOrigin(StrEnum):
    """ToolCall.origin and ToolResult.origin (session vocabulary § Q.6, K286): who asked for the
    call. Either way Substrate's tool producer runs it and writes its ToolResult."""

    REPLY = "reply"  # the model step's reply asked for it; the next model step reads the result
    MCP = "mcp"  # a harness driver called it over MCP; the result goes back over MCP
