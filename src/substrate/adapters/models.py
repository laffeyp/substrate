# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The dual-mode model seam for the reference topologies (product §8).

Every reference topology is dual-mode: a CI mode with DETERMINISTIC stand-in Producers
(proves the wiring, runs every commit, no network) and a WALKTHROUGH mode with real local
LLMs (proves the claim — adjudication in R-1, overlap in R-3). The seam is a `Responder`:
`respond(prompt) -> str`. Topologies are written against the Responder, not against any
model; the mode is chosen by which Responder the run is handed.

  - DeterministicResponder — canned, seed-derived answers; pure, no I/O. The CI mode. The
    spec is explicit that CI mode alone "sanitizes away the thing each topology exists to
    demonstrate", so CI mode proves WIRING only and never masquerades as the demonstration.
  - OllamaResponder — a real call to Ollama's native /api/chat (http://localhost:11434 by
    default) over httpx (the `openai-compat` optional extra; the kernel imports none of it —
    httpx is imported lazily here). Sets think=False + num_ctx + retry, the things a real model
    actually needs to work (a naive single-shot call silently breaks reasoning models and
    long transcripts). The WALKTHROUGH mode.

Model reach: the R-1..R-3 walkthroughs pin small local models (llama3.2:1b members;
huihui_ai/qwen2.5-coder-abliterate:7b adjudicator/writer) so the documented demonstrations run
on any Ollama box. Beyond the walkthroughs, every Ollama model is a legitimate driver — local
or `:cloud` tags alike (the 2026-06-27 correction: all models are on the free tier here, so
there is no local-vs-cloud cost tier; the only distinction that matters is sample size) — and
`CliResponder` extends the seam to any command-line model or agent.
"""

from __future__ import annotations

import asyncio
import hashlib
import os

from msgspec import Struct

# The Responder Protocol lives among the structural protocols (substrate.protocols) and is public
# as substrate.api.Responder; re-exported here (and via the substrate.reference back-compat module)
# so `from substrate.adapters import Responder` and legacy `...reference._models` imports both work.
from ..protocols import Responder

__all__ = [
    "Responder",
    "DeterministicResponder",
    "OllamaResponder",
    "CliResponder",
    "call_responder",
    "ModelUsage",
    "call_responder_metered",
    "ContextTokensUnknown",
    "DriverIntrospectionUnavailable",
    "ollama_base_url",
]


class DriverIntrospectionUnavailable(Exception):
    """The driver's introspection endpoint could not be reached.

    Sprint 208, sprint 207.5 bridge row: `OllamaResponder.context_tokens()` raises
    this on connection refused (daemon down), malformed body, or timeout. Callers
    fall back to the `~/.substrate/config.toml` `[driver.<name>].context_tokens`
    value; the daemon logs the failure but does not halt the session open.
    """


class ContextTokensUnknown(Exception):
    """The driver responded but declared no context length the caller can read.

    For Ollama: `/api/show` returned `model_info` with no `*.context_length` key.
    Callers treat this as an authoritative "unknown" and fall back to the config
    table; the daemon may print a stderr note naming the driver.
    """


class ModelUsage(Struct, frozen=True):
    """Per-model-call resource usage, emitted as an application event at the Responder seam so token
    counts and latency land on the inner record — the measurement the seam used to throw away.
    Tokens + wall time + the model id. No money is tracked anywhere: these are local / subscription
    models, so there is no per-call dollar amount and never will be. A
    DeterministicResponder reports wall_ms=0 and word-count token estimates so a CI record stays
    byte-stable; a real OllamaResponder reports Ollama's own prompt_eval_count / eval_count and an
    inference-only wall time. `estimated` is True when the counts are a word-count stand-in rather
    than provider truth, so a reader tells them apart from the DATA, not by parsing the model string.
    All fields RFC-8785-encodable, so the event rides the bus like any other application kind
    (Producer-declared, not a reserved substrate.* kind — the ToolCall precedent)."""

    model: str
    prompt_tokens: int
    completion_tokens: int
    wall_ms: int  # INFERENCE latency (prompt-eval + generation); excludes model load — see _usage
    estimated: bool = False  # True = word-count stand-in, not provider truth

    def total_tokens(self) -> int:
        """prompt + completion. A method, not a field, so it never lands on the wire (the durable
        facts are the two counts; the sum is derived)."""
        return self.prompt_tokens + self.completion_tokens


class DeterministicResponder:
    """A pure, seeded stand-in (CI mode). Same prompt + seed => same answer, no network — so
    the topology's WIRING is exercised reproducibly and replay/D-8 hold. It does NOT pretend
    to reason; it returns a stable canned answer derived from (seed, prompt, optional menu).
    The spec requires CI mode to never masquerade as the real demonstration; this responder is
    deliberately trivial so no one mistakes its output for model output."""

    def __init__(self, seed: int = 0, menu: list[str] | None = None) -> None:
        self._seed = seed
        self._menu = menu

    def respond(self, prompt: str) -> str:
        h = hashlib.sha256(f"{self._seed}:{prompt}".encode()).hexdigest()
        if self._menu:
            return self._menu[int(h[:8], 16) % len(self._menu)]
        return f"stub[{self._seed}]:{h[:12]}"

    async def arespond(self, prompt: str) -> str:
        """Async sibling of `respond` — pure delegation. Every Responder must
        expose both surfaces per the protocol (sprint 244); the async path is
        the one the session model producer awaits so cancel_producer has a
        window during a slow real driver's call. DeterministicResponder is
        already fast + synchronous; arespond just wraps respond, keeping the
        byte-identical CI record contract."""
        return self.respond(prompt)


# Output cap for an OllamaResponder request when the caller sets none (UI sprint 101): the
# request's own context window, `num_ctx`. No reply can outgrow the context, so this is the
# physical bound, not a guess at how long a model should work. Sprint 097 used 16,384, half the
# default context; Ollama counts a thinking model's reasoning against num_predict (ollama issues
# #16583, #17561), so a reasoning model that thought hard hit the cap and failed the turn with
# done_reason "length" and no answer. A looping small model still stops when the window fills.


def ollama_base_url(base_url: str | None = None) -> str:
    """The Ollama server's base URL: `base_url`, else `OLLAMA_BASE_URL`, else localhost:11434.

    `OLLAMA_BASE_URL` lets a run reach Ollama across a boundary (the container test arena points it
    at host.docker.internal) without touching call sites. A trailing `/v1` from the old
    OpenAI-compat default is dropped; the native routes are `<base>/api/...`. The console's model
    listing and capability probe call this too, so one setting moves every Ollama call (lens
    audit F304).
    """
    base = (base_url or os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
    return base[:-3] if base.endswith("/v1") else base


class OllamaResponder:
    """A real local-LLM responder over Ollama's native `/api/chat` (walkthrough mode).

    Rebuilt to the standard a precursor orchestrator proved is REQUIRED to make open-source models
    actually work — a naive single-shot OpenAI-compat call is a toy that fails on real models:

      - `think=False`: thinking-capable models (deepseek-r1, qwen3, kimi, gpt-oss, most cloud
        reasoning models) otherwise route their whole output budget into a hidden `thinking` field
        and return EMPTY `content`. Without this every reasoning model is silently broken.
      - explicit `num_ctx`: Ollama defaults the context window to **2048** regardless of the model's
        real capacity, so a long input (a growing conversation transcript) is truncated to its tail
        and the model parrots the last turn. Set it to the model's actual window.
      - retry with backoff: a daemon hiccup or a cloud-tier 503 must not crash a whole run.

    Native `/api/chat` (not the OpenAI-compat `/v1`) because that endpoint is where `num_ctx` and
    `think` live. httpx is imported lazily (the `openai-compat` extra), so importing this module
    never requires httpx in CI. temperature defaults to 0 for as-reproducible-as-a-real-model-gets
    walkthroughs. Local Ollama needs no auth; set `api_key` for direct api.ollama.com cloud access
    (local `:cloud` tags route through the daemon with no key once `ollama signin` has run)."""

    def __init__(
        self,
        model: str,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 0,  # 0 = num_ctx, the context window; never uncapped (see below)
        num_ctx: int = 32768,
        think: bool = False,
        timeout: float | None = None,
        max_retries: int = 3,
        system: str | None = None,
    ) -> None:
        self._endpoint = f"{ollama_base_url(base_url)}/api/chat"
        self._model = model
        self._api_key = api_key
        self._temperature = temperature
        # Ollama's own default is NumPredict=-1, unlimited (ollama api/types.go DefaultOptions).
        # Uncapped, a looping small model generates until the read timeout: 2026-10-01,
        # llama3.2:1b on a 117-byte prompt took 3 x 300 s ReadTimeout. Every request is capped;
        # a reply that hits the cap fails loud in _content.
        self._max_tokens = max_tokens if max_tokens > 0 else num_ctx
        self._num_ctx = num_ctx
        self._think = think
        # UI sprint 101: no default limit on how long the model works. num_predict above ends every
        # generation; `timeout` (driver_params) caps reading the reply only when set. Connecting to
        # Ollama still fails after 10 s.
        self._timeout = timeout
        self._max_retries = max_retries
        self._system = system

    def _request(
        self, prompt: str, tools: list[dict[str, object]] | None = None
    ) -> tuple[dict[str, str], dict[str, object]]:
        messages: list[dict[str, str]] = []
        if self._system:
            messages.append({"role": "system", "content": self._system})
        messages.append({"role": "user", "content": prompt})
        options: dict[str, object] = {
            "num_ctx": self._num_ctx,
            "temperature": self._temperature,
            "num_predict": self._max_tokens,
        }
        payload: dict[str, object] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "think": self._think,  # force useful output into `content`, not a hidden thinking field
            "options": options,
        }
        if tools:  # native function-tool calling (Ollama /api/chat `tools`)
            payload["tools"] = tools
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers, payload

    def _content(self, data: dict[str, object]) -> str:
        if data.get("done_reason") == "length":
            raise RuntimeError(
                f"OllamaResponder({self._model}) reply hit the {self._max_tokens}-token cap "
                "(num_predict); the output is truncated. Raise max_tokens or ask for less."
            )
        message = data.get("message")
        text = message.get("content", "") if isinstance(message, dict) else ""
        return str(text).strip()

    @staticmethod
    def _usage(data: dict[str, object], model: str) -> ModelUsage:
        """Read Ollama's native /api/chat accounting off the response — the fields `_content` used to
        discard. prompt_eval_count = prompt tokens, eval_count = generated tokens. wall_ms is the
        INFERENCE latency (prompt_eval_duration + eval_duration, ns -> ms) — NOT total_duration, which
        folds in load_duration (seconds of VRAM load on a cold call) and would confound a
        latency comparison by cache state. Falls back to total_duration only if the
        eval phases are absent. Missing or odd-typed fields degrade to 0, never raise."""

        def _i(key: str) -> int:
            v = data.get(key)
            return int(v) if isinstance(v, (int, float)) else 0

        eval_ns = _i("prompt_eval_duration") + _i("eval_duration")
        wall_ns = eval_ns if eval_ns > 0 else _i("total_duration")
        return ModelUsage(
            model=model,
            prompt_tokens=_i("prompt_eval_count"),
            completion_tokens=_i("eval_count"),
            wall_ms=wall_ns // 1_000_000,
            estimated=False,  # provider truth
        )

    def _chat(self, prompt: str) -> dict[str, object]:
        """One POST to /api/chat with simple geometric retry, returning the parsed response dict.
        `max_retries` attempts, 1s/2s/4s backoff, then raise. Rate limits are a real error —
        halting the sweep is the honest response. The 8-attempt 429 marathon (2026-08-09) was a
        compensation for wrong concurrency; it hid systemic failure as slow progress. Reverted.

        2026-08-09 diagnostics fix: on an HTTPStatusError, capture the response body in the
        raised RuntimeError. Pre-fix the error carried only `Client error '400 Bad Request' for
        url` — Ollama's actual reason (unsupported model tag, context overflow, malformed
        payload) was thrown away. On pass 1 that hid the SYSTEMIC bug that every drafter call to
        the ensemble cloud tags was returning 400 with a specific body reason, silently."""
        import time

        import httpx  # lazy: the openai-compat optional extra; kernel/CI need not have it

        headers, payload = self._request(prompt)
        last_exc: Exception | None = None
        last_body: str = ""
        for attempt in range(self._max_retries):
            try:
                resp = httpx.post(
                    self._endpoint,
                    headers=headers,
                    json=payload,
                    timeout=httpx.Timeout(self._timeout, connect=10.0),
                )
                if resp.status_code >= 400:
                    last_body = resp.text[:400]
                resp.raise_for_status()
                data: dict[str, object] = resp.json()
                return data
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < self._max_retries - 1:
                    time.sleep(1.0 * (2**attempt))
        body_note = f" body={last_body!r}" if last_body else ""
        raise RuntimeError(
            f"OllamaResponder({self._model}) failed after {self._max_retries} attempts: "
            f"{last_exc!r}{body_note}"
        )

    async def _achat(
        self, prompt: str, tools: list[dict[str, object]] | None = None
    ) -> dict[str, object]:
        """Async sibling of `_chat`. Same simple geometric retry (2026-08-09 halt-on-error
        rewrite): `max_retries` attempts, 1s/2s/4s backoff, then raise. Rate-limit halting is the
        honest response. Same response-body capture as `_chat` (see its docstring)."""
        import asyncio as _asyncio

        import httpx

        headers, payload = self._request(prompt, tools)
        last_exc: Exception | None = None
        last_body: str = ""
        for attempt in range(self._max_retries):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(self._timeout, connect=10.0)
                ) as client:
                    resp = await client.post(self._endpoint, headers=headers, json=payload)
                if resp.status_code >= 400:
                    last_body = resp.text[:400]
                resp.raise_for_status()
                data: dict[str, object] = resp.json()
                return data
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < self._max_retries - 1:
                    await _asyncio.sleep(1.0 * (2**attempt))
        body_note = f" body={last_body!r}" if last_body else ""
        raise RuntimeError(
            f"OllamaResponder({self._model}) failed after {self._max_retries} attempts: "
            f"{last_exc!r}{body_note}"
        )

    def respond(self, prompt: str) -> str:
        """Synchronous call (the Responder protocol + non-async callers). For use INSIDE an async
        Producer, prefer `call_responder`, which routes through `arespond` so the call is cancellable
        rather than orphaning a worker thread on cancel-others / finalise."""
        return self._content(self._chat(prompt))

    def respond_metered(self, prompt: str) -> tuple[str, ModelUsage]:
        """`respond`, plus the provider's own token/latency accounting as a ModelUsage — the
        measurement that `_content` alone throws away."""
        data = self._chat(prompt)
        return self._content(data), self._usage(data, self._model)

    async def arespond(self, prompt: str) -> str:
        """Async, cancellable call (see `_achat`) — the path `call_responder` prefers."""
        return self._content(await self._achat(prompt))

    async def arespond_metered(self, prompt: str) -> tuple[str, ModelUsage]:
        """Async sibling of `respond_metered`: the cancellable call plus ModelUsage accounting."""
        data = await self._achat(prompt)
        return self._content(data), self._usage(data, self._model)

    async def achat_tools(self, prompt: str, tools: list[dict[str, object]]) -> dict[str, object]:
        """Async tools-chat: hand the model the function `tools` and return the raw `message` dict
        (its `content` + any `tool_calls`) for the caller to parse. Native tool-calling where the
        model supports it (llama3.2 returns `tool_calls`); models that instead emit the call as JSON
        in `content` (qwen2.5-coder) are handled by the caller's `parse_tool_call`. Cancellable like
        `arespond` (routes through `_achat`)."""
        data = await self._achat(prompt, tools)
        msg = data.get("message")
        return msg if isinstance(msg, dict) else {"content": "", "tool_calls": []}

    def context_tokens(self) -> int:
        """Return the driver's advertised context window in tokens.

        Reads `POST <base>/api/show` with the responder's own model tag, then
        iterates `model_info` for the first key ending in `.context_length`.
        Bridge mapping: `substrate/process/WORKING_AGREEMENT.md` §"Ollama /api/show"
        (verified 2026-08-25). Family names — `llama.context_length`,
        `qwen2.context_length`, `deepseek4.context_length` — differ per model
        family, so the read never hardcodes a prefix. Raises `ContextTokensUnknown`
        when the response carries no matching key; raises `DriverIntrospectionUnavailable`
        when the daemon is unreachable, the body is malformed, or the request
        times out.
        """
        import httpx  # lazy: matches the /api/chat call site

        base = self._endpoint[: -len("/api/chat")]
        show_url = f"{base}/api/show"
        try:
            # metadata lookup, not model work: bounded
            resp = httpx.post(
                show_url, json={"name": self._model}, timeout=httpx.Timeout(30.0, connect=10.0)
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise DriverIntrospectionUnavailable(
                f"OllamaResponder.context_tokens: /api/show failed for {self._model!r}: {exc}"
            ) from exc
        except ValueError as exc:
            raise DriverIntrospectionUnavailable(
                f"OllamaResponder.context_tokens: /api/show returned unparseable body: {exc}"
            ) from exc
        model_info = data.get("model_info") if isinstance(data, dict) else None
        if not isinstance(model_info, dict):
            raise ContextTokensUnknown(
                f"OllamaResponder.context_tokens: {self._model!r} response has no model_info dict"
            )
        for key, value in model_info.items():
            if key.endswith(".context_length") and isinstance(value, int) and value > 0:
                return value
        raise ContextTokensUnknown(
            f"OllamaResponder.context_tokens: {self._model!r} model_info has no *.context_length key"
        )


class CliResponder:
    """A Responder backed by ANY command-line model or agent — Claude Code (`claude -p`), Gemini
    (`gemini -p`), or any CLI that takes a prompt and prints a reply. `respond(prompt)` runs the
    command with the prompt appended as the final argument (claude/gemini/ollama all accept this),
    captures stdout as the reply, and fails LOUD on a non-zero exit or empty output — never a silent
    stub. It has no native tool-calling, so Substrate's tool loop drives the tools via the text
    convention (describe the tools, parse the model's JSON tool call): even a plain prompt->text CLI
    becomes a tool-using agent ON substrate. `arespond` uses an async subprocess so the call is
    cancellable and Producers overlap, matching OllamaResponder's concurrency contract."""

    def __init__(
        self, command: list[str], *, timeout: float | None = None, name: str | None = None
    ) -> None:
        if not command:
            raise ValueError("CliResponder needs a non-empty command, e.g. ['claude', '-p']")
        self._command = list(command)
        self._timeout = timeout
        self.name = name or command[0]

    def respond(self, prompt: str) -> str:
        import subprocess

        proc = subprocess.run(  # noqa: S603 — an explicit, operator-chosen agent CLI driver
            [*self._command, prompt], capture_output=True, text=True, timeout=self._timeout
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"CliResponder({self.name}) exit {proc.returncode}: {proc.stderr.strip()[:300]}"
            )
        out = proc.stdout.strip()
        if not out:
            raise RuntimeError(
                f"CliResponder({self.name}) produced no output (stderr: {proc.stderr.strip()[:200]})"
            )
        return out

    async def arespond(self, prompt: str) -> str:
        """Async, cancellable call over an asyncio subprocess (the path `call_responder` prefers)."""
        import asyncio as _asyncio
        import os as _os
        import signal as _signal

        proc = await _asyncio.create_subprocess_exec(
            *self._command,
            prompt,
            stdout=_asyncio.subprocess.PIPE,
            stderr=_asyncio.subprocess.PIPE,
            start_new_session=True,  # own process group: a kill reaches the agent's children
        )

        async def _kill_group() -> None:
            try:
                _os.killpg(proc.pid, _signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            # UI sprint 107: reap the child. Unwaited, it stayed a zombie and its pipe transports
            # open until garbage collection (ResourceWarning in the kernel suite).
            try:
                await proc.wait()
            except _asyncio.CancelledError:
                pass

        try:
            stdout, stderr = await _asyncio.wait_for(proc.communicate(), timeout=self._timeout)
        except (TimeoutError, _asyncio.TimeoutError):
            await _kill_group()
            raise RuntimeError(
                f"CliResponder({self.name}) timed out after {self._timeout}s"
            ) from None
        except _asyncio.CancelledError:
            # UI sprint 102: the user's interrupt cancels this call. Before, only a timeout
            # killed the process, so an interrupted CLI agent kept running (and editing files)
            # after the turn had parked.
            await _kill_group()
            raise
        if proc.returncode != 0:
            raise RuntimeError(
                f"CliResponder({self.name}) exit {proc.returncode}: "
                f"{stderr.decode('utf-8', 'replace').strip()[:300]}"
            )
        out = stdout.decode("utf-8", "replace").strip()
        if not out:
            raise RuntimeError(f"CliResponder({self.name}) produced no output")
        return out


async def call_responder(responder: Responder, prompt: str) -> str:
    """Invoke a Responder from inside an async Producer WITHOUT blocking the event loop.

    A real responder (OllamaResponder, any network/IO-backed model) does blocking I/O. Calling it
    directly serializes every Producer on the single event loop — so the substrate's headline
    property (N candidates streaming concurrently; "wall-clock latency drops because nothing is
    sequential that doesn't have to be") is NOT realized on the real-model path: the candidates run
    one after another. Offload the blocking call to a worker thread so the loop stays free and the
    Producers genuinely overlap.

    A responder that exposes an async `arespond` (OllamaResponder does) is awaited DIRECTLY — real
    network I/O over httpx.AsyncClient, genuinely cancellable, so a cancelled Producer cancels the
    request rather than orphaning a worker thread (which `asyncio.to_thread` cannot cancel, stalling
    process shutdown up to the responder timeout — REVIEW.md kernel-correctness-1).

    DeterministicResponder is pure CPU and instant; it is called SYNCHRONOUSLY here (no thread, and
    this coroutine then completes without awaiting, so it never yields control). That is deliberate:
    in CI the deterministic stand-ins must complete in a fixed order so concurrent Producers produce
    a byte-identical record (N-DET-1 / conformance check 9). A blocking custom responder (pure-code
    transform, etc.) still offloads to a thread for concurrency. So: async real responders are
    cancellable; stand-ins stay sync (determinism); other blocking responders offload.
    """
    arespond = getattr(responder, "arespond", None)
    if callable(arespond):
        return str(await arespond(prompt))
    if isinstance(responder, DeterministicResponder):
        return responder.respond(prompt)
    return await asyncio.to_thread(responder.respond, prompt)


async def call_responder_metered(responder: Responder, prompt: str) -> tuple[str, ModelUsage]:
    """Like `call_responder`, but also returns a `ModelUsage` for the call — emit it from the Producer
    so the inner record carries per-call token/latency accounting.

    A responder exposing `arespond_metered` (OllamaResponder) returns the provider's REAL counts. Any
    other responder (the DeterministicResponder stand-in, a custom seam) has no native accounting, so
    usage is DERIVED deterministically — word-count token estimates and wall_ms=0: stable enough to
    keep a CI record byte-identical, and honest that it is an estimate, not provider truth (the model
    field carries the responder's identity so a reader can tell the two apart). The text is obtained
    through the same `call_responder` path, preserving its concurrency/cancellation discipline."""
    ametered = getattr(responder, "arespond_metered", None)
    if callable(ametered):
        text, usage = await ametered(prompt)
        return str(text), usage
    text = await call_responder(responder, prompt)
    model = str(getattr(responder, "_model", type(responder).__name__))
    usage = ModelUsage(
        model=model,
        prompt_tokens=len(prompt.split()),
        completion_tokens=len(text.split()),
        wall_ms=0,
        estimated=True,  # word-count stand-in, NOT provider truth — marked in the data
    )
    return text, usage
