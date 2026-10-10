# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Count arguments a model supplies (`limit`, `offset`) are validated, never silently honored.

Regression for 2026-10-01: a real model called list_records with {"limit": 0} and the tool
returned zero rows as a success. inspect_record advertised `limit` in its schema and ignored it.
"""

import json
from pathlib import Path

import pytest
from msgspec import Struct

from substrate.api import Runtime, quiescence
from substrate.topologies.tool_loop.substrate_tools import (
    _INSPECT_RECORD_SCHEMA,
    _LIST_RECORDS_SCHEMA,
    make_inspect_record,
    make_list_records,
)
from substrate.topologies.tool_loop.tools import positive_int


def _seed(root: Path, n: int) -> None:
    for i in range(n):
        d = root / f"s_{i:04d}"
        d.mkdir(parents=True)
        (d / "manifest.json").write_text(
            json.dumps({"session_id": d.name, "created_at": 1000.0 + i})
        )


def test_positive_int_defaults_and_rejects() -> None:
    assert positive_int(None, "limit", 20) == 20
    assert positive_int("5", "limit", 20) == 5
    for bad in (0, -1, "x"):
        with pytest.raises(ValueError, match="limit must be"):
            positive_int(bad, "limit", 20)


def test_list_records_rejects_limit_zero_and_honors_a_valid_limit(tmp_path: Path) -> None:
    _seed(tmp_path, 3)
    tool = make_list_records(tmp_path)
    with pytest.raises(ValueError, match="limit must be >= 1"):
        tool.run([{"limit": 0}])
    assert tool.run([{"limit": 2}])["count"] == 2
    assert tool.run([{}])["count"] == 3


def test_schemas_declare_the_minimum() -> None:
    assert _LIST_RECORDS_SCHEMA["properties"]["limit"]["minimum"] == 1
    assert _INSPECT_RECORD_SCHEMA["properties"]["limit"]["minimum"] == 1


class Tick(Struct, frozen=True):
    n: int


async def _ticks(_input):
    for i in range(5):
        yield Tick(n=i)


def _topo(b):
    b.producer_kind("p", schemas=[Tick], schema_version=1, factory=lambda: _ticks)
    b.initial("p", input=None)
    b.termination(quiescence())


async def test_inspect_record_pages_by_limit(tmp_path: Path) -> None:
    root = tmp_path / "run"
    await Runtime(root).run(_topo)
    tool = make_inspect_record(driver_context_tokens=1_000_000)
    page = tool.run(
        [{"record": str(root), "format": "events", "filter": {"kinds": ["Tick"]}, "limit": 2}]
    )
    assert [e["payload"]["n"] for e in page["events"]] == [0, 1]
    assert page["has_more"] is True
    nxt = tool.run([{"continue_from": page["cursor"], "format": "events", "limit": 2}])
    assert [e["payload"]["n"] for e in nxt["events"]] == [2, 3]


def test_ollama_requests_are_always_capped_and_truncation_fails_loud() -> None:
    from substrate.adapters.models import OllamaResponder

    r = OllamaResponder("m")
    _headers, payload = r._request("hi")
    # Ollama's own default is -1 (unlimited); ours is the request's context window (UI sprint 101)
    assert payload["options"]["num_predict"] == payload["options"]["num_ctx"]
    assert OllamaResponder("m", max_tokens=64)._request("hi")[1]["options"]["num_predict"] == 64
    # a cloud tag leaves the output cap to the provider (glm-5.2:cloud refused num_predict=num_ctx)
    for cloud in ("glm-5.2:cloud", "qwen3-coder:480b-cloud"):
        assert (
            "num_predict" not in OllamaResponder(cloud, num_ctx=262144)._request("hi")[1]["options"]
        )
    assert (
        OllamaResponder("glm-5.2:cloud", max_tokens=64)._request("hi")[1]["options"]["num_predict"]
        == 64
    )
    assert "num_predict" in OllamaResponder("cloud")._request("hi")[1]["options"]
    with pytest.raises(RuntimeError, match="token cap"):
        r._content({"done_reason": "length", "message": {"content": "partial"}})
    assert r._content({"done_reason": "stop", "message": {"content": " ok "}}) == "ok"


async def test_read_first_envelope_reads_only_the_first_frame(tmp_path: Path) -> None:
    from substrate.api import RUN_STARTED, read_first_envelope, read_record

    root = tmp_path / "run"
    await Runtime(root).run(_topo)
    first = read_first_envelope(root)
    assert first == next(iter(read_record(root)))
    assert first["kind"] == RUN_STARTED and first["seq"] == 0
    assert read_first_envelope(tmp_path / "missing") is None


async def test_run_name_is_recorded_and_list_records_filters_on_it(tmp_path: Path) -> None:
    from substrate.api import read_first_envelope

    sessions = tmp_path / "sessions"
    for sid, name in (("s_a", "game_of_life"), ("s_b", None)):
        root = sessions / sid / "record"
        await Runtime(root).run(_topo, name=name)
    assert read_first_envelope(sessions / "s_a" / "record")["payload"]["name"] == "game_of_life"
    assert "name" not in read_first_envelope(sessions / "s_b" / "record")["payload"]  # byte-stable
    out = make_list_records(sessions).run([{"topology": "game_of_life"}])
    assert [r["session_id"] for r in out["records"]] == ["s_a"]
