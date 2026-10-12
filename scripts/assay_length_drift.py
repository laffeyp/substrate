# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Does a Length change made mid-session hold? (2026-10-12)

Five arms per model, the same ten questions in the same order, each turn a real session turn
through the kernel (`session_topology`, the `standard` guidance bundle, no tools). A change is a
SessionChanged before that turn (§ T.3), drawn in the history beside its message (§ P.4):

- `normal`         — normal throughout;
- `terse`          — terse throughout;
- `n2t@2`, `n2t@5` — normal, changed to terse before turn 2 (early) or turn 5 (halfway);
- `t2n@5`          — terse, changed to normal before turn 5 (a loosening).

Every reply's word count and text go to `<out>/<model>.jsonl`, one line per turn. The texts are
kept for later language measures. Run:

    uv run python scripts/assay_length_drift.py --sessions 8 --out process/runs/assays/length_drift_2026-10-12
"""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from substrate import api
from substrate.adapters import OllamaResponder
from substrate.topologies.session import UserMessage, session_topology

QUESTIONS = [
    "Explain how a hash map handles collisions.",
    "Explain what a database index is and when it hurts.",
    "Explain how TCP keeps data in order.",
    "Explain what a mutex protects against.",
    "Explain how garbage collection finds unused memory.",
    "Explain what a race condition is, with an example.",
    "Explain how a CPU cache speeds up a program.",
    "Explain what idempotency means for an HTTP API.",
    "Explain how DNS turns a name into an address.",
    "Explain what a deadlock is and one way to avoid it.",
]
# arm -> (length before the change, length after, the turn the change comes before)
ARMS: dict[str, tuple[str, str, int]] = {
    "normal": ("normal", "normal", 0),
    "terse": ("terse", "terse", 0),
    "n2t@2": ("normal", "terse", 2),
    "n2t@5": ("normal", "terse", 5),
    "t2n@5": ("terse", "normal", 5),
}


def length_at(arm: str, turn: int) -> str:
    before, after, at = ARMS[arm]
    return before if turn < at else after


def run_session(model: str, arm: str, rep: int, records: Path) -> list[dict[str, Any]]:
    root = records / f"{model.replace(':', '_')}-{arm}-{rep}"
    sid = f"s_ld_{arm}_{rep}"
    rows: list[dict[str, Any]] = []
    seen = 0
    for turn, question in enumerate(QUESTIONS):
        um = UserMessage(text=question, turn_index=turn, assembled_prompt="", slash_source="chat")
        topo = session_topology(
            driver=OllamaResponder(model),
            driver_name=model,
            driver_context_tokens=100_000,
            seed="",
            tools={},
            session_id=sid,
            workspace_path=str(records),
            first_turn_user_message=um if turn == 0 else None,
            bundle="standard",
            length=length_at(arm, turn),
            tone="neutral",
        )
        rt = api.Runtime(root, persistent=True)
        if turn == 0:
            asyncio.run(rt.run(topo, name="session"))
        else:
            asyncio.run(rt.resume(topo, resume_event=um))
        events = list(api.read_record(root, resolve_blobs=True))
        replies = [
            e["payload"] for e in events if e["kind"] == "ModelReply" and e["payload"].get("text")
        ]
        changed = [e["payload"] for e in events if e["kind"] == "SessionChanged"]
        new = replies[seen:]
        seen = len(replies)
        text = new[-1]["text"] if new else ""
        rows.append(
            {
                "model": model,
                "arm": arm,
                "rep": rep,
                "turn": turn,
                "length": length_at(arm, turn),
                "words": len(text.split()),
                "changes": len(changed),
                "text": text,
            }
        )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="kimi-k2.7-code:cloud,glm-5.2:cloud")
    ap.add_argument("--sessions", type=int, default=8)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    with tempfile.TemporaryDirectory(prefix="length-drift-") as tmp:
        records = Path(tmp)
        jobs = [
            (m, a, r) for m in args.models.split(",") for a in ARMS for r in range(args.sessions)
        ]
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(run_session, m, a, r, records): (m, a, r) for m, a, r in jobs}
            for future in futures:
                m, a, r = futures[future]
                try:
                    rows = future.result()
                except Exception as exc:  # noqa: BLE001 — one failed session is reported, the rest still count
                    print(f"FAILED {m} {a} {r}: {api.describe_error(exc)}", flush=True)
                    continue
                with lock, (args.out / f"{m.replace(':', '_')}.jsonl").open("a") as fh:
                    for row in rows:
                        fh.write(json.dumps(row) + "\n")
                print(f"done {m} {a} {r}: {[row['words'] for row in rows]}", flush=True)


if __name__ == "__main__":
    main()
