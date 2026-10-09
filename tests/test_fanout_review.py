# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Observation contract for fanout_review (sprint 137).

CI path: a throwaway git repo gives `changed_files` a real diff; DeterministicResponders drive
the panel so the record is reproducible with no network. Asserts the diff is gathered read-only,
the panel reviews it, the quorum fires the judge, and the run finalises — the application's own
record is the evidence.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.applications import changed_files, fanout_review_topology
from substrate.topologies.code_review import DEFAULT_ROLES


def _repo_with_change(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    for cmd in (
        ["git", "init", "-q", str(repo)],
        ["git", "-C", str(repo), "config", "user.email", "t@t"],
        ["git", "-C", str(repo), "config", "user.name", "t"],
    ):
        subprocess.run(cmd, check=True)
    (repo / "calc.py").write_text("def divide(a, b):\n    return a / b\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True)
    # a change to review, uncommitted (diff vs HEAD)
    (repo / "calc.py").write_text("def divide(a, b):\n    return a / b  # no zero guard\n")
    return repo


def test_changed_files_gathers_the_diff_readonly(tmp_path: Path) -> None:
    repo = _repo_with_change(tmp_path)
    diff = changed_files(repo, ref="HEAD")
    assert "calc.py" in diff and "no zero guard" in diff  # the real change is gathered
    # read-only: the working tree still has the uncommitted change, git status unchanged
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True
    ).stdout
    assert "calc.py" in status  # gathering did not stage/commit/clean anything


def test_changed_files_includes_new_untracked_files(tmp_path: Path) -> None:
    # F-6: `git diff <ref>` lists tracked changes only, so a NEW file — the most review-worthy change —
    # was silently dropped from the panel input. A fixture with an untracked file carrying the bug is the
    # shape sensitive to this failure (Addendum A3); the earlier test's modified-tracked-file could not
    # show it.
    repo = _repo_with_change(tmp_path)  # has a modified tracked file
    (repo / "new_module.py").write_text(
        "def leak(password):\n    print(password)  # new file bug\n"
    )
    diff = changed_files(repo, ref="HEAD")
    assert "calc.py" in diff and "no zero guard" in diff  # tracked change still gathered
    assert "new_module.py" in diff and "new file bug" in diff  # AND the new untracked file


def test_changed_files_empty_diff_is_a_marker_not_a_crash(tmp_path: Path) -> None:
    repo = _repo_with_change(tmp_path)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "change"], check=True)
    diff = changed_files(repo, ref="HEAD")  # nothing uncommitted now
    assert "no changes" in diff.lower()


def test_fanout_review_reviews_the_diff_and_finalises(tmp_path: Path) -> None:
    repo = _repo_with_change(tmp_path)
    responders = {r: DeterministicResponder(seed=i) for i, r in enumerate(DEFAULT_ROLES)}
    topo = fanout_review_topology(
        repo,
        ref="HEAD",
        responders=responders,
        judge=DeterministicResponder(seed=99),
        quorum=3,
    )
    import asyncio

    result = asyncio.run(api.Runtime(tmp_path / "run").run(topo))
    assert result.status == "finalised"  # the runtime's own verdict, not inferred from the tail
    events = list(api.read_record(tmp_path / "run"))
    kinds = [e["kind"] for e in events]

    # the panel reviewed and the judge adjudicated on the gathered diff
    assert kinds.count("CritiquePosted") == len(DEFAULT_ROLES)
    assert "VerdictRendered" in kinds
    verdict = next(e for e in events if e["kind"] == "VerdictRendered")
    assert verdict["payload"]["n_critiques"] >= 3  # the quorum was met
    # the application's own record reaches a terminal — it is replayable evidence
    assert kinds[-1] == "substrate.RunFinalised"
    # C-7: every model call is metered — the 5 reviewers each emit ModelUsage, and the judge does when it
    # fires, so an assay of a fanout_review run sees the model work, not model_calls=0.
    assert kinds.count("ModelUsage") >= len(DEFAULT_ROLES)
    # C-2: the reviewed diff is on the record as a ReviewSubject — a replay carries the SUBJECT, not just
    # the verdict. Before this a fanout_review record held opinions about material that was nowhere on it.
    subjects = [e for e in events if e["kind"] == "ReviewSubject"]
    assert len(subjects) == 1 and "no zero guard" in subjects[0]["payload"]["content"]
    # code_review's kinds + the shared ModelUsage + fanout's own ReviewSubject (locked in the vocab doc)
    assert not any(
        k not in {"CritiquePosted", "VerdictRendered", "ModelUsage", "ReviewSubject"}
        and not k.startswith("substrate.")
        for k in kinds
    )


def test_a_narrow_panel_still_adjudicates(tmp_path: Path) -> None:
    # F-7: quorum defaults to 3, but `roles` is caller-set. A 2-role panel with the default quorum posts
    # 2 critiques, never reaches 3, and would finalise with NO VerdictRendered. The topology clamps the
    # quorum to the panel size so a narrow panel still adjudicates.
    import asyncio

    repo = _repo_with_change(tmp_path)
    roles = ("security", "correctness")  # 2 roles, default quorum 3
    responders = {r: DeterministicResponder(seed=i) for i, r in enumerate(roles)}
    topo = fanout_review_topology(
        repo,
        ref="HEAD",
        responders=responders,
        judge=DeterministicResponder(seed=99),
        roles=roles,  # quorum left at its default of 3, above the 2-role panel size
    )
    result = asyncio.run(api.Runtime(tmp_path / "run").run(topo))
    kinds = [e["kind"] for e in api.read_record(tmp_path / "run")]
    assert result.status == "finalised"
    assert kinds.count("CritiquePosted") == 2
    assert (
        "VerdictRendered" in kinds
    )  # the clamped quorum let the judge fire — no silent no-verdict


class _SpyResponder:
    """Records prompts, returns a fixed reply — asserts what the reviewer model actually SAW (F-11)."""

    def __init__(self, reply: str = "looks fine") -> None:
        self.prompts: list[str] = []
        self._reply = reply

    def respond(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._reply


def test_the_gathered_diff_reaches_the_reviewers(tmp_path: Path) -> None:
    # F-11: sprint 137's contract DECLARED "critiques with the gathered diff reflected in the reviewer
    # input" but no test ran that leg — changed_files was tested in isolation, and throwing the diff away
    # (fanout_review.py:62, code="") left the suite green. A spy reviewer proves the real diff reaches the
    # panel: blanking the gathered code now turns this red.
    import asyncio

    repo = _repo_with_change(tmp_path)
    roles = ("security", "correctness")
    responders = {r: _SpyResponder() for r in roles}
    topo = fanout_review_topology(
        repo,
        ref="HEAD",
        responders=responders,
        judge=DeterministicResponder(seed=99),
        roles=roles,
    )
    asyncio.run(api.Runtime(tmp_path / "run").run(topo))
    # every reviewer's prompt carried the actual gathered diff, not an empty blob
    for role, spy in responders.items():
        assert spy.prompts, f"{role} reviewer was never called"
        assert any("no zero guard" in p for p in spy.prompts), f"{role} did not see the diff"


def test_changed_files_truncates_a_huge_diff_with_a_marker(tmp_path: Path) -> None:
    # F-14: the _MAX_DIFF_CHARS truncation path was never exercised. A diff over the cap must be cut with
    # a visible marker, never a silent drop that hands the panel a partial diff it thinks is whole.
    repo = _repo_with_change(tmp_path)
    (repo / "big.py").write_text("# " + "y" * 30_000 + "\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "big"], check=True)
    (repo / "big.py").write_text("# " + "z" * 30_000 + "\n")  # a large tracked change
    diff = changed_files(repo, ref="HEAD")
    assert len(diff) < 30_000  # bounded
    assert "truncated" in diff  # the cut is announced


def test_non_repo_path_raises_not_swallowed(tmp_path: Path) -> None:
    with pytest.raises(subprocess.CalledProcessError):
        changed_files(tmp_path / "not-a-repo", ref="HEAD")
