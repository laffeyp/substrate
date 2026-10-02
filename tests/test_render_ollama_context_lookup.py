# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 208 — Ollama /api/show driver context lookup + 60-s TTL cache.

Live daemon lookup happens through `OllamaResponder.context_tokens()`, verified
against the /api/show contract in `WORKING_AGREEMENT.md` §"Ollama /api/show".
Every model family carries its own `<family>.context_length` key —
`llama.context_length`, `qwen2.context_length`, `deepseek4.context_length`
(the last verified live 2026-08-25 = 1_048_576). The reader iterates
`model_info` and takes the first key ending in `.context_length`, so a new
family (say `gemma3.context_length`) requires no code change.
"""

from __future__ import annotations

from typing import Any

import pytest

from substrate.adapters import (
    ContextTokensUnknown,
    DriverIntrospectionUnavailable,
    OllamaResponder,
)
from substrate.topologies.session.transcript import (
    _context_cache,
    resolve_driver_context_tokens,
)


@pytest.fixture(autouse=True)
def _clear_context_cache() -> None:
    _context_cache.clear()


class _StubResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


def _fake_httpx(payload: dict[str, Any] | Exception, calls: list[dict[str, Any]]) -> Any:
    import types

    module = types.SimpleNamespace()

    class _HTTPError(Exception):
        pass

    def post(url: str, json: dict[str, Any], timeout: float) -> _StubResponse:
        calls.append({"url": url, "body": json, "timeout": timeout})
        if isinstance(payload, Exception):
            raise payload
        return _StubResponse(payload)

    module.post = post
    module.Timeout = lambda read, connect: {"read": read, "connect": connect}
    module.HTTPError = _HTTPError
    return module


def test_llama_family_key_returns_context_length(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    payload = {
        "model_info": {"llama.context_length": 131_072, "general.parameter_count": 1_000_000}
    }
    monkeypatch.setitem(__import__("sys").modules, "httpx", _fake_httpx(payload, calls))
    r = OllamaResponder("llama3.2:1b")
    assert r.context_tokens() == 131_072
    assert calls == [
        {
            "url": "http://localhost:11434/api/show",
            "body": {"name": "llama3.2:1b"},
            # the capability probe is metadata, not model work: bounded (UI sprint 101)
            "timeout": {"read": 30.0, "connect": 10.0},
        }
    ]


def test_qwen2_family_key_returns_context_length(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    payload = {"model_info": {"qwen2.context_length": 32_768}}
    monkeypatch.setitem(__import__("sys").modules, "httpx", _fake_httpx(payload, calls))
    r = OllamaResponder("huihui_ai/qwen2.5-coder-abliterate:7b")
    assert r.context_tokens() == 32_768


def test_deepseek4_family_key_returns_context_length(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    payload = {"model_info": {"deepseek4.context_length": 1_048_576}}
    monkeypatch.setitem(__import__("sys").modules, "httpx", _fake_httpx(payload, calls))
    r = OllamaResponder("deepseek-v4-flash:cloud")
    assert r.context_tokens() == 1_048_576


def test_missing_context_length_key_raises_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    payload = {"model_info": {"general.parameter_count": 1_000_000}}
    monkeypatch.setitem(__import__("sys").modules, "httpx", _fake_httpx(payload, calls))
    r = OllamaResponder("mystery:1b")
    with pytest.raises(ContextTokensUnknown):
        r.context_tokens()


def test_missing_model_info_dict_raises_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setitem(__import__("sys").modules, "httpx", _fake_httpx({}, calls))
    r = OllamaResponder("mystery:1b")
    with pytest.raises(ContextTokensUnknown):
        r.context_tokens()


def test_ttl_cache_returns_same_value_within_60_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    payload = {"model_info": {"llama.context_length": 131_072}}
    monkeypatch.setitem(__import__("sys").modules, "httpx", _fake_httpx(payload, calls))
    r = OllamaResponder("llama3.2:1b")
    assert resolve_driver_context_tokens("llama3.2:1b", r, now=0.0) == 131_072
    assert resolve_driver_context_tokens("llama3.2:1b", r, now=30.0) == 131_072
    assert resolve_driver_context_tokens("llama3.2:1b", r, now=59.999) == 131_072
    assert len(calls) == 1  # one HTTP call under the TTL window


def test_ttl_expiry_re_fetches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    payload = {"model_info": {"llama.context_length": 131_072}}
    monkeypatch.setitem(__import__("sys").modules, "httpx", _fake_httpx(payload, calls))
    r = OllamaResponder("llama3.2:1b")
    resolve_driver_context_tokens("llama3.2:1b", r, now=0.0)
    resolve_driver_context_tokens("llama3.2:1b", r, now=61.0)
    assert len(calls) == 2  # ttl expired, re-fetched


def test_introspection_failure_falls_back_to_config_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    calls: list[dict[str, Any]] = []
    fake = _fake_httpx({}, calls)  # placeholder; overwrite `post` to raise
    err = fake.HTTPError("connection refused")

    def _raising_post(url: str, json: dict[str, Any], timeout: float) -> None:
        calls.append({"url": url, "body": json, "timeout": timeout})
        raise err

    fake.post = _raising_post
    monkeypatch.setitem(__import__("sys").modules, "httpx", fake)
    r = OllamaResponder("dead:1b")
    with pytest.raises(DriverIntrospectionUnavailable):
        r.context_tokens()
    # No config file → resolve falls back to the default 100_000.
    value = resolve_driver_context_tokens("dead:1b", r, config_path=tmp_path / "nope.toml", now=0.0)
    assert value == 100_000
    assert len(calls) >= 2  # bare probe + resolve's own live probe
