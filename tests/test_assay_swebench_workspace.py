# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The SWE-bench workspace diff seam: turn a changed checkout into a model_patch, dropping test-file edits
(which collide with the held-out test_patch and cause false not-resolves). git is real; no Docker."""

import subprocess
from pathlib import Path

from substrate.assay.swebench_workspace import (
    filter_diff,
    graded_test_files,
    is_test_file,
    workspace_diff,
)


def test_is_test_file():
    assert is_test_file("tests/test_basic.py")
    assert is_test_file("pkg/foo_test.py")
    assert is_test_file("conftest.py") and is_test_file("tests/conftest.py")
    assert is_test_file(
        "django/contrib/admin/tests.py"
    )  # django's bare tests.py convention (review fix)
    assert not is_test_file("src/flask/blueprints.py")
    assert not is_test_file("setup.py")  # config is KEPT — a real fix may touch it
    assert not is_test_file(
        "django/test/client.py"
    )  # django/test/ is SOURCE, not a test — must be KEPT


def test_graded_test_files_parses_the_graded_test_set():
    tp = (
        "diff --git a/tests/test_x.py b/tests/test_x.py\n--- a/tests/test_x.py\n+++ b/tests/test_x.py\n"
        "diff --git a/app/tests.py b/app/tests.py\n--- /dev/null\n+++ b/app/tests.py\n"
    )
    assert graded_test_files(tp) == {"tests/test_x.py", "app/tests.py"}


def test_filter_diff_drops_drop_files_even_when_not_test_named():
    # a file the held-out test_patch touches but that ISN'T test-named must still be dropped (collision).
    diff = (
        "diff --git a/app/weird_grader.py b/app/weird_grader.py\n@@ -1 +1 @@\n-a\n+b\n"
        "diff --git a/src/app.py b/src/app.py\n@@ -1 +1 @@\n-x\n+y\n"
    )
    out = filter_diff(diff, drop_files=frozenset({"app/weird_grader.py"}))
    assert "src/app.py" in out and "weird_grader.py" not in out


_DIFF = """diff --git a/src/app.py b/src/app.py
index 111..222 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1 +1 @@
-x = 1
+x = 2
diff --git a/tests/test_app.py b/tests/test_app.py
index 333..444 100644
--- a/tests/test_app.py
+++ b/tests/test_app.py
@@ -1 +1 @@
-assert x == 1
+assert x == 2
"""


def test_filter_diff_drops_test_sections_keeps_source():
    out = filter_diff(_DIFF)
    assert "a/src/app.py" in out and "+x = 2" in out  # source kept
    assert "tests/test_app.py" not in out and "assert x == 2" not in out  # test section dropped


def test_filter_diff_handles_quoted_test_path():
    # git quotes paths with spaces; a quoted TEST path (test_*.py with a space) must still be dropped,
    # not inherit the previous section's keep-state (review #71 NET 1).
    diff = (
        'diff --git "a/tests/test_weird thing.py" "b/tests/test_weird thing.py"\n@@ -1 +1 @@\n-a\n+b\n'
        "diff --git a/src/app.py b/src/app.py\n@@ -1 +1 @@\n-x\n+y\n"
    )
    out = filter_diff(diff)
    assert "src/app.py" in out and "+y" in out  # source kept
    assert "test_weird thing.py" not in out  # quoted test path dropped


def test_filter_diff_drops_unparseable_header_fail_safe():
    # a header matching NEITHER form -> FAIL SAFE (drop), never inherit the prior keep-state.
    diff = (
        "diff --git a/src/keep.py b/src/keep.py\n@@ -1 +1 @@\n-x\n+y\n"
        "diff --git mangled-header-no-paths\n@@ -1 +1 @@\n-secret\n+leak\n"
    )
    out = filter_diff(diff)
    assert "src/keep.py" in out and "+y" in out  # the parseable source section is kept
    assert "+leak" not in out  # the unparseable section is dropped, not inherited-keep


def _git_repo(tmp_path) -> Path:
    d = tmp_path / "repo"
    d.mkdir()
    (d / "app.py").write_text("def f():\n    return 1\n")
    (d / "tests").mkdir()
    (d / "tests" / "test_app.py").write_text("assert f() == 1\n")
    for args in (
        ["init", "-q"],
        ["config", "user.email", "t@t"],
        ["config", "user.name", "t"],
        ["add", "-A"],
        ["commit", "-qm", "base"],
    ):
        subprocess.run(["git", "-C", str(d), *args], check=True, capture_output=True)
    return d


def test_workspace_diff_on_a_real_repo_drops_test_edits(tmp_path):
    repo = _git_repo(tmp_path)
    # a topology edits BOTH a source file and a test file in the checkout.
    (repo / "app.py").write_text("def f():\n    return 2\n")
    (repo / "tests" / "test_app.py").write_text("assert f() == 2\n")
    patch = workspace_diff(str(repo))
    assert "app.py" in patch and "+    return 2" in patch  # the real fix is in the patch
    assert (
        "test_app.py" not in patch
    )  # the test edit is dropped (would collide with the held-out tests)


def test_workspace_diff_empty_when_nothing_changed(tmp_path):
    repo = _git_repo(tmp_path)
    assert (
        workspace_diff(str(repo)) == ""
    )  # no changes -> empty patch (graded not-resolved, no crash)


def test_workspace_diff_captures_a_new_file(tmp_path):
    repo = _git_repo(tmp_path)
    (repo / "newmod.py").write_text("y = 9\n")  # git add -A must surface new files
    patch = workspace_diff(str(repo))
    assert "newmod.py" in patch and "+y = 9" in patch


def test_section_b_path_parses_bare_header():
    # F8 fix regression pin: the standard `diff --git a/X b/Y` form still parses.
    from substrate.assay.swebench_workspace import _section_b_path

    assert _section_b_path("diff --git a/src/foo.py b/src/foo.py") == "src/foo.py"


def test_section_b_path_parses_both_sides_quoted_header():
    # Path with spaces or special chars — git C-quotes both sides.
    from substrate.assay.swebench_workspace import _section_b_path

    assert (
        _section_b_path('diff --git "a/path with space.py" "b/path with space.py"')
        == "path with space.py"
    )


def test_section_b_path_parses_mixed_quote_headers_post_F8():
    # F8 fix (review 2026-08-08): git emits ONE-side-quoted headers for renames where only one
    # side contains special chars, and for some rename-and-mode-change combinations. Pre-fix the
    # regex only matched bare-both and quoted-both — a mixed-quote rename returned None, the
    # section was dropped from filter_diff, and the patch graded not-resolved silently.
    from substrate.assay.swebench_workspace import _section_b_path

    # a-side bare, b-side quoted (new path has a space).
    assert _section_b_path('diff --git a/old_name.py "b/new name.py"') == "new name.py"
    # a-side quoted, b-side bare.
    assert _section_b_path('diff --git "a/old name.py" b/new_name.py') == "new_name.py"


def test_section_b_path_returns_none_on_unparseable_header():
    # Malformed header MUST return None so the caller's fail-safe drop fires.
    from substrate.assay.swebench_workspace import _section_b_path

    assert _section_b_path("not a diff header at all") is None
    assert _section_b_path("diff --git broken") is None
