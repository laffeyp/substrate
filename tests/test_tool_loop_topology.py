# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Tool-using loop — CI structural + determinism tests (Wave 14).

Covers the three behaviors the loop is built around: the model -> tool -> model chain with the
result fed back in; a failed tool surfacing as a typed observation (not a crash); and the step
budget ending the run on a FinalAnswer rather than a silent stop.
"""

import pytest

from substrate.api import Runtime, first_divergence, read_record
from substrate.topologies.tool_loop import tool_loop_topology


@pytest.mark.timeout(15)
async def test_tool_loop_runs_to_final_answer(tmp_path):
    result = await Runtime(tmp_path / "run").run(tool_loop_topology())
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    calls = [e for e in envs if e["kind"] == "ToolCall"]
    results = [e for e in envs if e["kind"] == "ToolResult"]
    finals = [e for e in envs if e["kind"] == "FinalAnswer"]
    # model -> tool -> model chain: add(2,3)=5, then mul(5,4)=20, then answer "20".
    assert [c["payload"]["tool"] for c in calls] == ["add", "mul"]
    assert [r["payload"]["output"] for r in results] == [5, 20]
    assert all(r["payload"]["ok"] for r in results)
    assert len(finals) == 1 and finals[0]["payload"]["text"] == "20"
    # the result was fed back: the second call multiplied the first tool's output, not a constant.
    assert calls[1]["payload"]["args"] == [5, 4]
    # the continue Trigger re-fired the model once per ToolResult, bounded — no runaway.
    continued = [
        e
        for e in envs
        if e["kind"] == "substrate.TriggerFired" and e["payload"].get("trigger_id") == "continue"
    ]
    assert len(continued) == 2
    assert envs[-1]["kind"] == "substrate.RunFinalised"


@pytest.mark.timeout(15)
async def test_failed_tool_is_an_observation_not_a_crash(tmp_path):
    # the model calls a tool that does not exist; the run must NOT crash — the failure comes back
    # as a typed ToolResult the model reads, and the model answers citing it.
    result = await Runtime(tmp_path / "run").run(tool_loop_topology(script=[("divide", [1, 0])]))
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    bad = [e for e in envs if e["kind"] == "ToolResult" and not e["payload"]["ok"]]
    assert len(bad) == 1 and "unknown tool 'divide'" in bad[0]["payload"]["error"]
    finals = [e for e in envs if e["kind"] == "FinalAnswer"]
    assert len(finals) == 1 and "stopped" in finals[0]["payload"]["text"]
    # no Producer failed: the error stayed on the typed-event path, never an exception.
    assert not [e for e in envs if e["kind"] == "substrate.ProducerFailed"]


@pytest.mark.timeout(15)
async def test_step_budget_ends_on_a_final_answer(tmp_path):
    # a model that would never stop (always calls a tool) is capped at max_steps and the run still
    # ends cleanly on a FinalAnswer (the graceful-budget behavior), not a silent quiescence stop.
    result = await Runtime(tmp_path / "run").run(
        tool_loop_topology(script=[("add", [1, 1])] * 9, max_steps=3)
    )
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    calls = [e for e in envs if e["kind"] == "ToolCall"]
    finals = [e for e in envs if e["kind"] == "FinalAnswer"]
    assert len(calls) == 3  # capped at the budget, not 9
    assert len(finals) == 1  # and it still produced a final answer
    assert envs[-1]["kind"] == "substrate.RunFinalised"


@pytest.mark.timeout(15)
async def test_tool_loop_is_deterministic(tmp_path):
    await Runtime(tmp_path / "a").run(tool_loop_topology())
    await Runtime(tmp_path / "b").run(tool_loop_topology())
    assert first_divergence(tmp_path / "a", tmp_path / "b") is None


@pytest.mark.timeout(20)
async def test_full_suite_runs_real_tools_and_errors_stay_observations(tmp_path):
    # the real tool suite (write / read / surgical edit_file) runs through the SAME loop. The
    # edit_file actually mutates the file — the line-numbered read-back proves it (line 2 beta -> BETA)
    # — and a bad edit comes back as a typed ToolResult(ok=False), never a crash. FULL_SUITE has
    # side-effecting tools, so the run is deterministic=False (still a real, inspectable record).
    from substrate.topologies.tool_loop.tools import FULL_SUITE

    f = tmp_path / "work.txt"
    result = await Runtime(tmp_path / "run").run(
        tool_loop_topology(
            tools=FULL_SUITE,
            deterministic=False,
            max_steps=8,
            script=[
                ("write_file", [str(f), "alpha\nbeta\n"]),
                ("read_file", [str(f)]),
                ("edit_file", [str(f), "beta", "BETA"]),
                ("read_file", [str(f)]),
                ("edit_file", [str(f), "nope", "x"]),  # search not found -> typed failure
            ],
        )
    )
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    results = [e for e in envs if e["kind"] == "ToolResult"]
    # the surgical edit took effect end-to-end: the second read sees BETA on line 2, not beta.
    # read_file is now line-numbered ("<n>\t<line>", canonical `read`), so the mutation is visible
    # AND line-addressable.
    reads = [
        r["payload"]["output"]
        for r in results
        if r["payload"]["tool"] == "read_file" and r["payload"]["ok"]
    ]
    assert reads == ["1\talpha\n2\tbeta", "1\talpha\n2\tBETA"]
    # the bad edit is a typed observation, not a crash; no Producer failed.
    bad = [r for r in results if not r["payload"]["ok"]]
    assert len(bad) == 1 and "search text not found" in bad[0]["payload"]["error"]
    assert not [e for e in envs if e["kind"] == "substrate.ProducerFailed"]


@pytest.mark.timeout(20)
async def test_edit_file_rejects_ambiguous_match_instead_of_mis_splicing(tmp_path):
    # reproduce-then-kill (audit round-1 headline; KIT_DIARY #15): a non-unique `search` must be a
    # typed ToolResult(ok=False), NEVER a silent first-occurrence edit of the wrong region. Here
    # `x = 1` also appears inside `x = 12` — a first-occurrence `.replace(..., 1)` would corrupt one
    # of them and report success. The uniqueness guard rejects it and leaves the file UNTOUCHED.
    from substrate.topologies.tool_loop.tools import FULL_SUITE

    f = tmp_path / "code.py"
    original = "x = 1\ny = x = 12\n"  # "x = 1" occurs twice (once as a prefix of "x = 12")
    f.write_text(original, encoding="utf-8")
    result = await Runtime(tmp_path / "run").run(
        tool_loop_topology(
            tools=FULL_SUITE,
            deterministic=False,
            max_steps=4,
            script=[("edit_file", [str(f), "x = 1", "x = 99"])],  # AMBIGUOUS -> must reject
        )
    )
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    results = [e for e in envs if e["kind"] == "ToolResult"]
    bad = [r for r in results if not r["payload"]["ok"]]
    assert len(bad) == 1 and "not unique" in bad[0]["payload"]["error"]
    # the file on disk is byte-identical to before — no wrong-region splice happened.
    assert f.read_text(encoding="utf-8") == original
    assert not [e for e in envs if e["kind"] == "substrate.ProducerFailed"]


async def test_consecutive_rewrite_of_the_same_file_is_a_typed_observation_not_a_spin(tmp_path):
    # reproduce-then-kill (arena, 2026-07-02): a strong model, told in-prompt not to, re-wrote the SAME
    # file 16x without ever running it. A prompt is a request; the loop ENFORCES — a second consecutive
    # write to the same file with no run/read between comes back ok=False, redirecting to verification.
    from substrate.topologies.tool_loop.tools import FULL_SUITE

    f = tmp_path / "app.py"
    result = await Runtime(tmp_path / "run").run(
        tool_loop_topology(
            tools=FULL_SUITE,
            deterministic=False,
            max_steps=4,
            script=[("write_file", [str(f), "v1"]), ("write_file", [str(f), "v2"])],  # 2nd = spin
        )
    )
    assert result.status == "finalised"
    results = [e for e in read_record(tmp_path / "run") if e["kind"] == "ToolResult"]
    assert results[0]["payload"]["ok"] is True  # first write lands
    assert results[1]["payload"]["ok"] is False  # second consecutive write is refused
    assert "verify" in results[1]["payload"]["error"] or "run" in results[1]["payload"]["error"]
    assert f.read_text(encoding="utf-8") == "v1"  # the spin write never touched the file


async def test_refuse_done_when_the_last_run_exited_nonzero(tmp_path):
    # R-11a: externalize the verify policy the model may not hold. A model that RAN a failing command
    # and then tries to declare success must not have "done" laundered — the loop re-prompts once, and
    # if it STILL insists the FinalAnswer is marked [unverified] so the record can't claim success over
    # a real exit != 0. Deterministic: a stub achat_tools responder (no live model, no luck).
    from substrate.topologies.tool_loop.tools import FULL_SUITE

    class _Stub:
        def __init__(self) -> None:
            self.n = 0

        async def achat_tools(self, prompt: str, tools: list) -> dict:  # noqa: ANN001, ARG002
            self.n += 1
            if self.n == 1:  # first turn: run a command that FAILS (exit 3)
                return {
                    "content": "",
                    "tool_calls": [{"function": {"name": "bash", "arguments": {"cmd": "exit 3"}}}],
                }
            return {"content": "All done — the program works great."}  # then insist it's done

    result = await Runtime(tmp_path / "run").run(
        tool_loop_topology(
            model=_Stub(),
            walkthrough=True,
            deterministic=False,
            tools=FULL_SUITE,
            task="build it and prove it runs",
            max_steps=6,
        )
    )
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    bash = [e for e in envs if e["kind"] == "ToolResult" and e["payload"]["tool"] == "bash"]
    assert bash and bash[-1]["payload"]["output"]["exit"] == 3  # the failing run is on the record
    finals = [e for e in envs if e["kind"] == "FinalAnswer"]
    # the model insisted "done"; the harness refused to launder it — the claim is marked unverified.
    assert finals and "unverified" in finals[-1]["payload"]["text"].lower()


async def test_reprompt_CONVERTS_an_answer_attempt_into_a_fix(tmp_path):
    # R-11a conversion path (the branch the test above does NOT cover): a model runs a FAILING command,
    # tries to declare done, gets re-prompted — and this time RESPONDS with a tool call that fixes it.
    # The loop must CONTINUE (not halt), the fix must run clean, and the final answer must be clean (no
    # [unverified]). Deterministic: a stub that fails, answers, then on the re-prompt runs a passing cmd.
    from substrate.topologies.tool_loop.agency import score_agency
    from substrate.topologies.tool_loop.tools import FULL_SUITE

    class _Stub:
        def __init__(self) -> None:
            self.n = 0

        async def achat_tools(self, prompt: str, tools: list) -> dict:  # noqa: ANN001, ARG002
            self.n += 1
            if self.n == 1:  # run a failing command
                return {
                    "tool_calls": [{"function": {"name": "bash", "arguments": {"cmd": "exit 3"}}}]
                }
            if self.n == 2:  # try to declare done over the failure -> triggers the re-prompt
                return {"content": "All done."}
            if self.n == 3:  # the re-prompt CONVERTS: respond with a fix that runs clean
                return {
                    "tool_calls": [{"function": {"name": "bash", "arguments": {"cmd": "echo ok"}}}]
                }
            return {"content": "Fixed and verified — it runs cleanly now."}

    result = await Runtime(tmp_path / "run").run(
        tool_loop_topology(
            model=_Stub(),
            walkthrough=True,
            deterministic=False,
            tools=FULL_SUITE,
            task="run it, fix it, verify",
            max_steps=8,
        )
    )
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    bash = [
        e["payload"]["output"]["exit"]
        for e in envs
        if e["kind"] == "ToolResult" and e["payload"]["tool"] == "bash"
    ]
    assert bash == [3, 0]  # failed first, then the re-prompt drove a clean run
    finals = [e for e in envs if e["kind"] == "FinalAnswer"]
    assert finals and "unverified" not in finals[-1]["payload"]["text"].lower()  # honest, clean
    # the trajectory is VERIFIED: ran, recovered from the failure, saw exit 0.
    assert score_agency(envs).label == "VERIFIED" and score_agency(envs).resilient


def test_edit_file_replace_all_is_the_explicit_opt_out_for_renames(tmp_path):
    # unique-or-error stays the DEFAULT (the mis-splice guard above); replace_all=true is the explicit
    # opt-out for a deliberate rename-everywhere (Claude Code parity). The uniqueness safety is only
    # waived when the caller asks for it, and the count is reported honestly.
    from substrate.topologies.tool_loop.tools import FULL_SUITE

    edit = FULL_SUITE["edit_file"].run
    f = tmp_path / "code.py"
    f.write_text("old = 1\nold = old + old\n", encoding="utf-8")  # "old" appears 4x
    # without replace_all a non-unique search still errors and leaves the file untouched.
    import pytest as _pytest

    with _pytest.raises(ValueError, match="not unique"):
        edit([str(f), "old", "new"])
    assert f.read_text(encoding="utf-8") == "old = 1\nold = old + old\n"
    # with replace_all=true every occurrence is renamed and the count is reported.
    assert edit([str(f), "old", "new", True]) == f"edited {f} (4 replacements)"
    assert f.read_text(encoding="utf-8") == "new = 1\nnew = new + new\n"


def test_edit_file_stringified_false_does_not_enable_replace_all(tmp_path):
    # reproduce-then-kill (adversarial review, 2026-07-01): small models stringify scalars, and
    # bool("false") is True — a naive bool(arg) would read replace_all="false" as True and DISABLE the
    # unique-or-error guard (the destructive mis-splice class). The falsey spellings must stay False.
    import pytest as _pytest

    from substrate.topologies.tool_loop.tools import FULL_SUITE

    edit = FULL_SUITE["edit_file"].run
    f = tmp_path / "code.py"
    original = "old = 1\nold = old\n"  # "old" is non-unique
    for falsey in ("false", "False", "0", "no", "", "off"):
        f.write_text(original, encoding="utf-8")
        with _pytest.raises(ValueError, match="not unique"):
            edit([str(f), "old", "new", falsey])  # must NOT replace-all
        assert f.read_text(encoding="utf-8") == original  # untouched
    # a truthy string still enables it (a model that stringifies `true`); "old" occurs 3x.
    assert edit([str(f), "old", "new", "true"]) == f"edited {f} (3 replacements)"
    assert f.read_text(encoding="utf-8") == "new = 1\nnew = new\n"


@pytest.mark.timeout(20)
async def test_under_specified_tool_call_is_a_clear_typed_error(tmp_path):
    # surfaced by a live llama3.2:1b run: the model re-called write_file with NO args and the tool
    # body threw a raw IndexError. It was caught (typed ok=False, no crash) but the message was
    # useless to the model. A missing required arg must now be a CLEAR, actionable typed error.
    from substrate.topologies.tool_loop.tools import FULL_SUITE

    result = await Runtime(tmp_path / "run").run(
        tool_loop_topology(
            tools=FULL_SUITE,
            deterministic=False,
            max_steps=4,
            script=[("write_file", [str(tmp_path / "x.txt")])],  # missing `text`
        )
    )
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    bad = [e for e in envs if e["kind"] == "ToolResult" and not e["payload"]["ok"]]
    assert len(bad) == 1
    err = bad[0]["payload"]["error"]
    assert "missing required argument(s): text" in err and "IndexError" not in err
    assert not [e for e in envs if e["kind"] == "substrate.ProducerFailed"]


@pytest.mark.timeout(15)
async def test_non_encodable_tool_output_is_an_observation_not_an_emit_crash(tmp_path):
    # review #51 finding 2: a tool returning a non-RFC-8785-encodable value (a set) must come back as
    # ToolResult(ok=False), NOT crash the Producer at emit. The loop pre-validates the output inside
    # the try (canonical_bytes), so output-encodability is covered, not just tool exceptions.
    from substrate.topologies.tool_loop.tools import CALCULATOR, Tool

    suite = dict(CALCULATOR)
    # NaN is valid Python but NOT RFC-8785-encodable (JCS rejects it) — and unlike a set, msgspec
    # won't silently coerce it to something encodable. The exact "non-encodable output" case.
    suite["rogue"] = Tool("rogue", "rogue() -> a non-encodable NaN", False, lambda a: float("nan"))
    result = await Runtime(tmp_path / "run").run(
        tool_loop_topology(tools=suite, deterministic=False, script=[("rogue", [])])
    )
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    bad = [e for e in envs if e["kind"] == "ToolResult" and not e["payload"]["ok"]]
    assert len(bad) == 1  # the non-encodable return became a typed failure...
    assert not [e for e in envs if e["kind"] == "substrate.ProducerFailed"]  # ...not an emit crash
    assert not [
        e for e in envs if e["kind"] == "substrate.ProducerEmittedInvalidEvent"
    ]  # nor at emit


# ── canonical-semantics unit tests for the hardened read-only tools ───────────────────────────────
# These call the tool `run` functions directly: they're deterministic given a filesystem, so a unit
# test is the precise, cheap check (the loop integration is covered above). Behaviors match the
# canonical agent_toolset_20260401 contracts (line-numbered read, real-regex grep, glob).


def test_read_file_is_line_numbered_with_offset_limit_and_no_silent_truncation(tmp_path):
    from substrate.topologies.tool_loop.tools import FULL_SUITE

    read = FULL_SUITE["read_file"].run
    f = tmp_path / "f.txt"
    f.write_text("".join(f"line{i}\n" for i in range(1, 6)), encoding="utf-8")  # 5 lines
    # full read: canonical "<n>\t<line>", 1-based, reaches EOF -> no marker.
    assert read([str(f)]) == "1\tline1\n2\tline2\n3\tline3\n4\tline4\n5\tline5"
    # offset windows from line 4 to EOF, numbered from the offset, and — since it reaches EOF —
    # carries NO trailing marker.
    assert read([str(f), 4]) == "4\tline4\n5\tline5"
    # a window that stops SHORT of EOF does NOT cut silently — it says how many remain and how to page.
    out = read([str(f), 1, 2])
    assert out.startswith("1\tline1\n2\tline2")
    assert "3 more line(s)" in out and "read_file(path, 3)" in out
    # even a mid-file window that stops short reports the remainder from its own end (lines 4-5 left).
    mid = read([str(f), 2, 2])
    assert mid.startswith("2\tline2\n3\tline3")
    assert "2 more line(s)" in mid and "read_file(path, 4)" in mid
    # an EMPTY file returns an explicit marker, not "" — a bare empty string reads as a failed read to
    # the model (it retries or gives up). (Hardening lifted from Claude Code's leaked read tool.)
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    assert read([str(empty)]) == "(file is empty)"
    # reproduce-then-kill (adversarial review, 2026-07-01): an out-of-range offset (past EOF) yielded a
    # bare "" — the SAME ambiguity the empty-file marker kills — and limit<=0 pointed a pagination
    # marker back to the same offset (a re-page loop). An empty window now says what happened.
    assert read([str(f), 10]) == "(no lines at offset 10; the file has 5 line(s))"  # past EOF
    assert read([str(f), 2, 0]) == "(no lines at offset 2; the file has 5 line(s))"  # limit 0


def test_grep_is_a_real_regex_and_invalid_pattern_is_a_typed_failure(tmp_path):
    from substrate.topologies.tool_loop.tools import FULL_SUITE

    grep = FULL_SUITE["grep"].run
    f = tmp_path / "code.py"
    f.write_text("foo = 1\nbar = 22\nfoo_bar = 3\n", encoding="utf-8")
    # a regex (anchored digits) — a substring test could not express this.
    hits = grep([r"= \d\d$", str(f)])
    assert len(hits) == 1 and "bar = 22" in hits[0]
    # alternation, also regex-only.
    assert len(grep([r"^foo(_bar)? =", str(f)])) == 2
    # an invalid regex is a typed failure the model can read, not a crash.
    with pytest.raises(ValueError, match="invalid regex"):
        grep(["(unclosed", str(f)])


def test_glob_matches_files_by_pattern_sorted(tmp_path):
    from substrate.topologies.tool_loop.tools import FULL_SUITE

    glob = FULL_SUITE["glob"].run
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "b.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "c.txt").write_text("", encoding="utf-8")
    hits = glob(["**/*.py", str(tmp_path)])
    assert [h.rsplit("/", 1)[-1] for h in hits] == ["a.py", "b.py"]  # sorted, .txt excluded
    assert hits == sorted(hits)  # stable order for a replayable list


# ── native tool-calling parser: grounded in REAL local-model output shapes ────────────────────────
# The two shapes below were captured live (2026-07-01) from Ollama: llama3.2:1b returns a native
# `tool_calls` array; qwen2.5-coder:7b emits the SAME call as a bare JSON object in `content` with no
# `tool_calls`. The parser must handle BOTH or it silently fails on one model (finding-28). Testing
# against the recorded real shapes, not an invented one, is the point.


def test_parse_tool_call_handles_native_toolcalls_and_json_in_content():
    from substrate.topologies.tool_loop.tools import FULL_SUITE, parse_tool_call

    expected = ("tool", ("write_file", ["/tmp/hi.txt", "hello world"]))

    # llama3.2:1b — native tool_calls, arguments as a dict.
    llama = {
        "content": "",
        "tool_calls": [
            {
                "function": {
                    "name": "write_file",
                    "arguments": {"path": "/tmp/hi.txt", "text": "hello world"},
                }
            }
        ],
    }
    assert parse_tool_call(llama, FULL_SUITE) == expected

    # qwen2.5-coder:7b — the SAME call as a JSON object in content, tool_calls absent.
    qwen = {
        "content": '{\n  "name": "write_file",\n  "arguments": {\n    "path": "/tmp/hi.txt",\n    "text": "hello world"\n  }\n}',
        "tool_calls": None,
    }
    assert parse_tool_call(qwen, FULL_SUITE) == expected

    # a ```json-fenced call in content is still recovered (outer braces delimit it).
    fenced = {
        "content": '```json\n{"name": "list_dir", "arguments": {"path": "/etc"}}\n```',
        "tool_calls": None,
    }
    assert parse_tool_call(fenced, FULL_SUITE) == ("tool", ("list_dir", ["/etc"]))

    # named args mapped to positional in schema order (path, search, replace).
    edit = {
        "content": "",
        "tool_calls": [
            {
                "function": {
                    "name": "edit_file",
                    "arguments": {"path": "f.py", "search": "a", "replace": "b"},
                }
            }
        ],
    }
    assert parse_tool_call(edit, FULL_SUITE) == ("tool", ("edit_file", ["f.py", "a", "b"]))

    # plain prose with no call -> a final answer, not a bogus tool.
    assert parse_tool_call({"content": "The result is 20.", "tool_calls": None}, FULL_SUITE) == (
        "answer",
        "The result is 20.",
    )
    # an unknown tool name is NOT treated as a call.
    assert parse_tool_call(
        {"content": '{"name": "rm_rf", "arguments": {"path": "/"}}', "tool_calls": None}, FULL_SUITE
    ) == ("answer", '{"name": "rm_rf", "arguments": {"path": "/"}}')

    # reproduce-then-kill (arena, qwen2.5-coder:7b, 2026-07-01): a model that BATCHES several tool
    # calls into one message emits concatenated objects. The old greedy first-{-to-last-} span was
    # invalid JSON -> the whole thing degraded to a no-op FinalAnswer and ZERO tools ran. The
    # first-balanced-object parse extracts the FIRST call; the loop runs it and the model continues.
    batched = {
        "content": (
            '{"name": "write_file", "arguments": {"path": "g.py", "text": "x"}}\n'
            '{"name": "grep", "arguments": {"regex": "x", "path": "g.py"}}'
        ),
        "tool_calls": None,
    }
    assert parse_tool_call(batched, FULL_SUITE) == ("tool", ("write_file", ["g.py", "x"]))


def test_glob_caps_and_reports_a_huge_match(tmp_path):
    # glob must CAP: an uncapped match over a big tree returns 100s of KB and blob-offloads the
    # ToolResult (see the loop test below). 250 files -> 200 hits + a "N more" marker.
    from substrate.topologies.tool_loop.tools import FULL_SUITE

    for i in range(250):
        (tmp_path / f"f{i}.py").write_text("", encoding="utf-8")
    hits = FULL_SUITE["glob"].run(["**/*.py", str(tmp_path)])
    assert len(hits) == 201 and "more" in hits[-1]


@pytest.mark.timeout(20)
async def test_read_file_byte_cap_truncates_and_appends_the_same_pagination_marker(tmp_path):
    # r2 spike (SPIKE-2026-09-15-r2-read-file-byte-cap.md): pre-fix, a read_file whose output
    # exceeded _MAX_RESULT_BYTES (12 KB) fell to the generic "narrow the request" stub — no
    # verb, no cursor, no continuation call. The model repeated the same call. r2: on read_file
    # the outer wrap truncates to what fits and appends the SAME marker read_file emits when
    # its own line window doesn't reach EOF. One shape for both caps.
    from substrate.topologies.tool_loop.tools import FULL_SUITE

    big = tmp_path / "big.txt"
    # 3000 lines × ~30 bytes each ≈ 90 KB of content — the raw ToolResult (line-numbered)
    # exceeds 12 KB many times over. read_file's own line window (_MAX_READ_LINES=2000)
    # already can't page it in one call; the byte cap trips first.
    big.write_text(
        "".join(f"the quick brown fox jumped {i}\n" for i in range(3000)), encoding="utf-8"
    )

    result = await Runtime(tmp_path / "run").run(
        tool_loop_topology(
            tools=FULL_SUITE,
            deterministic=False,
            max_steps=4,
            script=[("read_file", [str(big)])],
        )
    )
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    tr = next(e for e in envs if e["kind"] == "ToolResult")
    out = tr["payload"]["output"]
    # Must NOT be the generic stub — the whole point of the r2 change.
    assert "too large to inline" not in out
    assert "narrow the request" not in out
    # Must carry the actionable pagination marker with a concrete next offset.
    assert "read_file(" in out and "for the rest" in out
    # Truncated content is still there (line-numbered tab prefix intact).
    assert "1\tthe quick brown fox" in out
    # Under the cap (with a bit of margin for the marker).
    assert len(out.encode("utf-8")) <= 12_000


@pytest.mark.timeout(20)
async def test_a_huge_tool_output_cannot_wedge_the_loop(tmp_path):
    # reproduce-then-kill (seen live): glob over a big tree returned 341 KB, blob-offloading the
    # ToolResult so `step` left the frame -> the `continue` predicate KeyError('step') -> quarantine
    # -> the loop wedged. Now glob caps its output AND the step-read is defensive, so the loop runs
    # clean: no PredicateQuarantined, the ToolResult is inline (not $blob), the run finalises.
    from substrate.topologies.tool_loop.tools import FULL_SUITE

    big = tmp_path / "repo"
    big.mkdir()
    for i in range(250):
        (big / f"m{i}.py").write_text("x = 1\n", encoding="utf-8")
    result = await Runtime(tmp_path / "run").run(
        tool_loop_topology(
            tools=FULL_SUITE,
            deterministic=False,
            max_steps=4,
            script=[("glob", ["**/*.py", str(big)])],
        )
    )
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    assert not [e for e in envs if e["kind"] == "substrate.PredicateQuarantined"]  # not wedged
    assert not [e for e in envs if e["kind"] == "substrate.ProducerFailed"]
    tr = next(e for e in envs if e["kind"] == "ToolResult")
    assert (
        "step" in tr["payload"] and "$blob" not in tr["payload"]
    )  # inline (capped), step on the frame
