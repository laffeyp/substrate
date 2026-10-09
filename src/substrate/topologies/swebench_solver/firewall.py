"""The solver's input rule: the held-out tests never reach the solver.

`firewall_check` decides, from the instance's own data, whether a SWE-bench instance can be solved
without the solver seeing the tests that grade it; `FirewallViolation` is the typed refusal. Both
lived in `substrate.assay.swebench` until UI sprint 109 (lens audit F199): the solver topology
imported them from assay while assay imported the solver, a package cycle. The rule belongs to
the solver's inputs; assay imports it from here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class FirewallViolation(ValueError):
    """Sprint 143 — typed exception raised by `prepare_swebench_case` when `firewall_check` fails.

    Categorical (not stringly-typed) so a caller that catches the wrong ValueError does not
    silently admit a leaky instance. IS-A ValueError, so existing broad handlers keep working; new
    code should catch `FirewallViolation` explicitly. The `reason` attribute carries the string
    `firewall_check` returned.
    """

    def __init__(self, instance_id: str, reason: str) -> None:
        super().__init__(f"instance {instance_id} fails the firewall: {reason}")
        self.instance_id = instance_id
        self.reason = reason


def firewall_check(instance: Mapping[str, Any]) -> tuple[bool, str]:
    """Per-instance firewall assertion (reviews #53 / #58 / #64) — the solver may NEVER see the held-out
    tests. Two conditions, both data-level over the instance:

      - files(patch) ∩ files(test_patch) == ∅: the gold SOURCE fix does not touch the graded test files.
        A shared file means a held-out (FAIL_TO_PASS) test could be a PRE-EXISTING test the gold patch
        flips fail->pass — present at base_commit, visible to the solver. That instance leaks the grade.
      - every FAIL_TO_PASS test file ∈ files(test_patch): the graded tests are ADDED by test_patch, so they
        are ABSENT from the base repo the solver works on (the structural firewall).

    Returns (ok, reason). Exclude or flag any instance that fails when assembling a firewall-clean set;
    prefer SWE-bench_Verified (human-curated) as the base."""
    import ast
    import re

    def _added_files(diff: str) -> set[str]:
        return {
            ln[6:] for ln in diff.splitlines() if ln.startswith("+++ b/") and ln[6:] != "dev/null"
        }

    def _f2p_in_test_patch(test_id: str, tp_files: set[str]) -> bool:
        # pytest: "path/test_x.py::Class::test" -> the file is the path before "::".
        if "::" in test_id:
            return test_id.split("::")[0] in tp_files
        # unittest/django parenthesised form: "test_func (module.path[.Class[.method]])". The
        # unittest loader resolves this by importing `module.path` and walking attributes. The
        # FILE is `module/path.py` at some sys.path prefix. Match rule (F7-round-2, 2026-08-09):
        # tp_file matches iff it EQUALS the derived path OR ends with `"/" + derived` (`/` forces
        # a segment boundary so `myapp/tests.py` cannot match `some_myapp/tests.py`).
        #
        # Trailing segments: the parenthesised group can end in a Class, or Class.method
        # (Django's newer test-id form appends the method name to the parens too). Python
        # convention — Classes are PascalCase, modules and methods are snake_case. Peel off:
        #   * last segment IF PascalCase (class-drop): `module.path.py`
        #   * last two segments IF second-to-last is PascalCase (class-plus-method drop)
        #   * always try full-module (`module.path.class.method.py`) as fallback
        # Any candidate matching in tp_files admits the id.
        m = re.search(r"\(([\w.]+)\)", test_id)
        if m:
            parts = m.group(1).split(".")
            candidates: list[str] = []
            # New-Django form: `module.Class.snake_method` — drop the last two.
            if len(parts) >= 3 and parts[-2][:1].isupper() and not parts[-1][:1].isupper():
                candidates.append("/".join(parts[:-2]) + ".py")
            # Legacy form: `module.Class` — drop the class.
            if len(parts) >= 2 and parts[-1][:1].isupper():
                candidates.append("/".join(parts[:-1]) + ".py")
            # Full-module — last segment IS a module (rare but legal, e.g. `some_module`).
            candidates.append("/".join(parts) + ".py")

            for derived in candidates:
                for f in tp_files:
                    if f == derived or f.endswith("/" + derived):
                        return True

        # Docstring form (no parens at all) — Django's SimpleTestCase repr uses the docstring's
        # first line as the id. Cannot derive a file. Fall back to CONTENT match against
        # test_patch: if the id string appears in an ADDED line (starts with `+` in the diff),
        # the test IS being added by test_patch. Coarser than the structural match; only used
        # when structural resolution fails. The lookup is against the raw test_patch text,
        # which the outer scope has as `str(instance.get("test_patch", ""))`.
        tp_text = str(instance.get("test_patch", ""))
        # Truncated docstrings still work — even a 40-char prefix in an added line is a strong
        # match. Django's SWE-bench ids tend to run 40-80 chars.
        needle = test_id.strip()
        if len(needle) < 12:
            # Very short strings (a single word or two) would match too many `+` lines. Fail
            # closed rather than fabricate a match on `def` or a variable name.
            return False
        for line in tp_text.splitlines():
            if line.startswith("+") and not line.startswith("+++") and needle in line:
                return True
        return False

    patch_files = _added_files(str(instance.get("patch", "")))
    tp_files = _added_files(str(instance.get("test_patch", "")))
    f2p_raw = instance.get("FAIL_TO_PASS", [])
    f2p = ast.literal_eval(f2p_raw) if isinstance(f2p_raw, str) else list(f2p_raw)

    shared = patch_files & tp_files
    if shared:
        return (False, f"patch and test_patch share files (grade leak): {sorted(shared)}")
    leaked = [str(t) for t in f2p if not _f2p_in_test_patch(str(t), tp_files)]
    if leaked:
        return (
            False,
            f"FAIL_TO_PASS tests not added by test_patch (pre-existing -> leak): {leaked[:3]}",
        )
    return (True, "firewall ok")


__all__ = ["FirewallViolation", "firewall_check"]
