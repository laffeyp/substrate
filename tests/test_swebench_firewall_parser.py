# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 142 — firewall_check parses test ids and MUST fail closed on unparseable ones.

The unittest/django test-id branch (matching `test_func (module.sub.Class)`) previously returned
True on parse failure with the reasoning "condition 1 still guards" — but condition 1 checks
patch/test_patch FILE intersection, not held-out test-id resolution, so an unparseable FAIL_TO_PASS
id silently admitted an instance whose held-out tests could not be verified to be added by
test_patch. That is fail-open on a security check. Sprint 142 flips the default: an unparseable id
is treated as "not in test_patch" (a leak), so firewall_check surfaces it and the caller excludes
the instance.
"""

from __future__ import annotations

from substrate.topologies.swebench_solver.firewall import firewall_check


def _instance(*, patch: str = "", test_patch: str = "", fail_to_pass: list[str]) -> dict:
    return {
        "patch": patch,
        "test_patch": test_patch,
        "FAIL_TO_PASS": fail_to_pass,
        "instance_id": "test__sprint-142",
    }


def _test_patch_adding(path: str) -> str:
    # A minimal git-style diff header the _added_files parser recognises.
    return f"diff --git a/{path} b/{path}\n--- /dev/null\n+++ b/{path}\n@@ -0,0 +1 @@\n+pass\n"


def test_unparseable_unittest_id_fails_closed() -> None:
    """An id that matches neither pytest ('::') nor unittest ('(module.Class)') MUST exclude the
    instance. Pre-142 behaviour returned True here."""
    # No "::" (not pytest form), no "(module)" parens (not unittest form).
    ok, reason = firewall_check(_instance(fail_to_pass=["totally_unparseable_id_no_form"]))
    assert ok is False, "unparseable id must fail closed"
    assert "totally_unparseable_id_no_form" in reason


def test_parseable_pytest_id_added_by_test_patch_passes() -> None:
    """Regression bar: a well-formed pytest id whose file IS in test_patch still passes."""
    ok, reason = firewall_check(
        _instance(
            test_patch=_test_patch_adding("tests/test_x.py"),
            fail_to_pass=["tests/test_x.py::test_y"],
        )
    )
    assert ok is True, reason


def test_parseable_pytest_id_missing_from_test_patch_fails() -> None:
    """Regression bar: a well-formed pytest id whose file is NOT in test_patch still fails."""
    ok, reason = firewall_check(
        _instance(
            test_patch=_test_patch_adding("tests/test_other.py"),
            fail_to_pass=["tests/test_x.py::test_y"],
        )
    )
    assert ok is False
    assert "tests/test_x.py::test_y" in reason


def test_parseable_unittest_id_added_by_test_patch_passes() -> None:
    """Direct-add case: test_patch adds the derived file at the project root. F7-round-2 rule:
    file must equal the derived path OR end with `"/" + derived` (a legal sys.path prefix)."""
    ok, reason = firewall_check(
        _instance(
            test_patch=_test_patch_adding("module/sub.py"),
            fail_to_pass=["test_method (module.sub.ClassName)"],
        )
    )
    assert ok is True, reason


def test_real_django_shape_passes_post_F7_round_2() -> None:
    """The Pass 1 breakage that motivated F7-round-2 (2026-08-09). Django places `tests/` on
    sys.path at test time, so a FAIL_TO_PASS id `(auth_tests.test_forms.UserChangeFormTest)`
    resolves at run time to `auth_tests/test_forms.py`, and test_patch adds the file at
    `tests/auth_tests/test_forms.py`. The pre-fix equality rule failed this shape — every
    Django instance (~14 on Lite, 114 excluded in the aborted first Pass 1) got excluded.
    Post-fix sys.path-boundary suffix match reads it correctly. Real payload from the actual
    `django__django-16139` instance."""
    ok, reason = firewall_check(
        _instance(
            test_patch=_test_patch_adding("tests/auth_tests/test_forms.py"),
            fail_to_pass=[
                "test_link_to_password_reset_in_helptext_via_to_field "
                "(auth_tests.test_forms.UserChangeFormTest)"
            ],
        )
    )
    assert ok is True, reason


def test_real_django_shape_deep_module_passes() -> None:
    """Deeper Django path — the derived module has multiple internal segments — must match
    when test_patch adds the file under `tests/`. Payload from `django__django-16408`."""
    ok, reason = firewall_check(
        _instance(
            test_patch=_test_patch_adding("tests/known_related_objects/tests.py"),
            fail_to_pass=[
                "test_multilevel_reverse_fk_cyclic_select_related "
                "(known_related_objects.tests.ExistingRelatedInstancesTests)"
            ],
        )
    )
    assert ok is True, reason


def test_unittest_id_substring_leak_fails_closed_post_F7_round_2() -> None:
    """The specific leak the firewall exists to catch. Pre-F7: substring `"myapp"` matched any
    tp_file under `myapp/`. Post-F7-round-2: derived `myapp/tests.py` (class-drop, since `tests`
    is not PascalCase) plus `myapp/tests.py` full-module — neither matches `myapp/other/
    test_foo.py` as an equality or `/`-boundary suffix. Leak fails closed."""
    ok, reason = firewall_check(
        _instance(
            test_patch=_test_patch_adding("myapp/other/test_foo.py"),
            fail_to_pass=["test_foo (myapp.tests)"],
        )
    )
    assert ok is False, "F7 regression: substring-leak of pre-existing tests must fail closed"
    assert "test_foo (myapp.tests)" in reason


def test_leading_slash_boundary_blocks_prefix_confusion() -> None:
    """`myapp/tests.py` must NOT match `some_myapp/tests.py`. The leading `/` in
    `endswith("/" + derived)` forces a segment break."""
    ok, _reason = firewall_check(
        _instance(
            test_patch=_test_patch_adding("some_myapp/tests.py"),
            fail_to_pass=["test_x (myapp.tests.SomeClass)"],
        )
    )
    assert ok is False


def test_new_django_form_with_trailing_method_passes() -> None:
    """Newer Django writes FAIL_TO_PASS as `test_x (module.path.Class.test_x)` — the METHOD
    name appears both outside AND as the last segment inside the parens. F7-round-2 handles
    the legacy `Class` trailing shape; F7-round-3 (2026-08-09) adds the `Class.snake_method`
    trailing shape by dropping the last TWO segments when the second-to-last is PascalCase.
    Real payload from `django__django-16408`."""
    ok, reason = firewall_check(
        _instance(
            test_patch=_test_patch_adding("tests/known_related_objects/tests.py"),
            fail_to_pass=[
                "test_multilevel_reverse_fk_cyclic_select_related "
                "(known_related_objects.tests.ExistingRelatedInstancesTests"
                ".test_multilevel_reverse_fk_cyclic_select_related)"
            ],
        )
    )
    assert ok is True, reason


def test_docstring_form_matched_by_content_search_in_test_patch() -> None:
    """Django's older SimpleTestCase repr uses a DOCSTRING (no parens at all) as the test id.
    F7-round-3 (2026-08-09) falls back to content search: if the docstring appears in an ADDED
    line of test_patch (a `+`-prefixed diff line), the test IS being added and the id passes.
    Real payload shape from `django__django-14608`."""
    docstring_id = "If validate_max is set and max_num is less than TOTAL_FORMS"
    test_patch = (
        "diff --git a/tests/forms_tests/tests/test_formsets.py b/tests/forms_tests/tests/test_formsets.py\n"
        "--- a/tests/forms_tests/tests/test_formsets.py\n"
        "+++ b/tests/forms_tests/tests/test_formsets.py\n"
        "@@ -100,0 +101,7 @@\n"
        "+    def test_max_num_something(self):\n"
        '+        """If validate_max is set and max_num is less than TOTAL_FORMS in the'
        ' formset\\n"""\n'
        "+        pass\n"
    )
    ok, reason = firewall_check(_instance(test_patch=test_patch, fail_to_pass=[docstring_id]))
    assert ok is True, reason


def test_docstring_form_not_in_test_patch_fails_closed() -> None:
    """Content-search fallback only admits when the docstring appears in an ADDED line. A
    docstring nowhere in test_patch is unresolvable — fail closed."""
    docstring_id = "If validate_max is set and max_num is less than TOTAL_FORMS"
    test_patch = _test_patch_adding("tests/forms_tests/tests/test_something_else.py")
    ok, _ = firewall_check(_instance(test_patch=test_patch, fail_to_pass=[docstring_id]))
    assert ok is False


def test_docstring_form_short_string_fails_closed() -> None:
    """Very short strings (<12 chars) would match too many diff lines. Fail closed rather than
    fabricate a match on `def` or a variable name."""
    ok, _ = firewall_check(
        _instance(test_patch="+++ b/tests/x.py\n+def foo():\n", fail_to_pass=["def foo"])
    )
    assert ok is False


def test_one_segment_parenthesised_group_resolves_to_a_module_file() -> None:
    """A one-segment parenthesised group `(some_module)` names an importable module. F7-round-2
    derives `some_module.py` and applies the sys.path-boundary rule. test_patch adding the
    file at any sys.path-legal path passes; a different filename fails closed."""
    ok_hit, _ = firewall_check(
        _instance(
            test_patch=_test_patch_adding("tests/some_module.py"),
            fail_to_pass=["test_func (some_module)"],
        )
    )
    assert ok_hit is True
    ok_miss, _ = firewall_check(
        _instance(
            test_patch=_test_patch_adding("tests/other_module.py"),
            fail_to_pass=["test_func (some_module)"],
        )
    )
    assert ok_miss is False
