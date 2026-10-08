"""The tool loop's envelope kind names (a kind is its event struct's class name).

UI sprint 107: these names were retyped as string literals in eight comparisons across the CLI,
the delegate tool, the agency scorer and the session transcript. A leaf module, so any of them can
import it without a cycle; `tests/test_kind_constants_match_structs_107.py` pins each constant to
its struct's `__name__`.
"""

from __future__ import annotations

from typing import Final

TOOL_CALL: Final[str] = "ToolCall"
TOOL_RESULT: Final[str] = "ToolResult"
FINAL_ANSWER: Final[str] = "FinalAnswer"
TOOL_PROGRESS: Final[str] = "ToolProgress"
