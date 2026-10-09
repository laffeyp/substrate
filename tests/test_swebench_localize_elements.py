# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Element-level localizer — sprint 157a.

Two subjects: the pure `extract_elements(source)` AST utility and the
`element_localizer_factory` producer. AST tests cover top-level functions, sync + async methods,
nested classes/functions, syntax errors (return empty, don't raise), and the qualified-name
convention. Producer tests exercise the wire: LLM picks files, the module reads each from disk,
emits SuspectElements per Python file, degrades gracefully on non-Python and unreadable paths.
"""

from __future__ import annotations

from pathlib import Path

from substrate import api
from substrate.api import Runtime, read_record
from substrate.reference._models import DeterministicResponder, ModelUsage
from substrate.topologies.swebench_solver.localize_elements import (
    element_localizer_factory,
    extract_elements,
)
from substrate.topologies.swebench_solver.records import (
    EditLocations,
    SuspectElements,
    SuspectFiles,
)


def test_extract_elements_top_level_functions():
    src = "def alpha():\n    pass\n\ndef bravo(x):\n    return x\n"
    assert extract_elements(src) == ["alpha", "bravo"]


def test_extract_elements_qualifies_methods_with_class_name():
    src = "class Foo:\n    def m1(self):\n        pass\n\n    def m2(self, x):\n        return x\n"
    assert extract_elements(src) == ["Foo.m1", "Foo.m2"]


def test_extract_elements_handles_async_functions_and_methods():
    src = (
        "async def top_async():\n"
        "    pass\n"
        "\n"
        "class Bar:\n"
        "    async def method_async(self):\n"
        "        return None\n"
    )
    assert extract_elements(src) == ["top_async", "Bar.method_async"]


def test_extract_elements_preserves_file_order():
    src = (
        "def z_first():\n    pass\n"
        "class A:\n"
        "    def a_method(self):\n        pass\n"
        "def m_middle():\n    pass\n"
    )
    # File order matters — the Repairer's edit_context builder may prefer file-order for grep-like
    # locality. Assert we don't sort alphabetically or by declaration type.
    assert extract_elements(src) == ["z_first", "A.a_method", "m_middle"]


def test_extract_elements_on_syntax_error_returns_empty_not_raises():
    # A partially-parseable file is a normal repo state — an unfinished edit, a Python 2 remnant.
    # extract_elements must not raise; the file-level localizer's suspect set stays useful.
    src = "def broken(:\n    pass\n"
    assert extract_elements(src) == []


def test_extract_elements_empty_source_returns_empty():
    # An empty file is legal Python (a module with no definitions) — extract yields [].
    assert extract_elements("") == []
    assert extract_elements("# just a comment\n") == []


def test_extract_elements_skips_module_level_statements_and_imports():
    # Imports, assignments, if-blocks at module level are NOT elements — only defs count. A
    # dispatch dict or CONSTANT = ... doesn't need to appear in EditLocations.
    src = (
        "import os\n"
        "from typing import Any\n"
        "\n"
        "CONSTANT = 42\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    print('go')\n"
        "\n"
        "def real_target():\n"
        "    pass\n"
    )
    assert extract_elements(src) == ["real_target"]


def test_extract_elements_handles_nested_classes():
    src = (
        "class Outer:\n"
        "    def outer_method(self):\n"
        "        pass\n"
        "\n"
        "    class Inner:\n"
        "        def inner_method(self):\n"
        "            pass\n"
    )
    names = extract_elements(src)
    assert "Outer.outer_method" in names
    assert "Outer.Inner.inner_method" in names


async def _run(tmp_path, responder, issue, repo_skeleton, base_checkout, known_files) -> list[dict]:  # type: ignore[no-untyped-def]
    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "loc",
            schemas=[SuspectFiles, SuspectElements, EditLocations, ModelUsage],
            schema_version=1,
            factory=element_localizer_factory(
                responder, issue, repo_skeleton, str(base_checkout), known_files
            ),
            deterministic=False,
        )
        b.initial("loc", input=None)
        b.termination(
            api.any_of(
                api.threshold_count("EditLocations", 1),
                api.quiescence(),
            )
        )

    await Runtime(tmp_path / "run").run(topo)
    return list(read_record(tmp_path / "run"))


def _write_repo(root: Path, tree: dict[str, str]) -> None:
    for rel, body in tree.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)


async def test_element_localizer_emits_suspect_elements_per_python_file(tmp_path):  # type: ignore[no-untyped-def]
    checkout = tmp_path / "repo"
    _write_repo(
        checkout,
        {
            "src/app.py": "class Router:\n    def route(self):\n        pass\n\ndef helper():\n    pass\n",
            "src/util.py": "def one():\n    pass\n\ndef two():\n    pass\n",
            "README.md": "# not python\n",
        },
    )
    known = {"src/app.py", "src/util.py", "README.md"}
    responder = DeterministicResponder(seed=0, menu=["src/app.py\nsrc/util.py"])
    events = await _run(tmp_path, responder, "fix", "src/app.py\nsrc/util.py", checkout, known)

    # SuspectFiles: the file list the LLM produced.
    suspects = [e["payload"] for e in events if e["kind"] == "SuspectFiles"]
    assert len(suspects) == 1
    assert list(suspects[0]["files"]) == ["src/app.py", "src/util.py"]

    # SuspectElements: one per Python file, elements in file order.
    elements = [e["payload"] for e in events if e["kind"] == "SuspectElements"]
    by_file = {e["file"]: list(e["elements"]) for e in elements}
    assert by_file == {
        "src/app.py": ["Router.route", "helper"],
        "src/util.py": ["one", "two"],
    }

    # EditLocations: `file::element` targets in file order.
    locs = [e["payload"] for e in events if e["kind"] == "EditLocations"]
    assert len(locs) == 1
    assert list(locs[0]["targets"]) == [
        "src/app.py::Router.route",
        "src/app.py::helper",
        "src/util.py::one",
        "src/util.py::two",
    ]


async def test_element_localizer_keeps_non_python_files_as_whole_file_targets(tmp_path):  # type: ignore[no-untyped-def]
    # A non-Python target (a config, a doc, a JSON fixture) stays in EditLocations without
    # element trimming — the Repairer can still route to it. NOT a silent drop.
    checkout = tmp_path / "repo"
    _write_repo(checkout, {"setup.cfg": "[metadata]\nname = flask\n"})
    responder = DeterministicResponder(seed=0, menu=["setup.cfg"])
    events = await _run(tmp_path, responder, "fix", "setup.cfg", checkout, {"setup.cfg"})

    # No SuspectElements for the non-Python file.
    assert not any(e["kind"] == "SuspectElements" for e in events)
    # EditLocations still carries the whole-file target.
    locs = [e["payload"] for e in events if e["kind"] == "EditLocations"]
    assert list(locs[0]["targets"]) == ["setup.cfg"]


async def test_element_localizer_degrades_on_unreadable_or_missing_python(tmp_path):  # type: ignore[no-untyped-def]
    # A .py file the LLM named that doesn't exist on disk (a hallucinated path — filtered by
    # `known_files` in `parse_suspect_files`, so this shouldn't happen; but a race between LLM
    # response and repo mutation could produce a missing file). Element extraction returns (),
    # the file stays as a whole-file target.
    checkout = tmp_path / "repo"
    _write_repo(checkout, {"real.py": "def real():\n    pass\n"})
    responder = DeterministicResponder(seed=0, menu=["real.py"])
    events = await _run(tmp_path, responder, "fix", "real.py", checkout, {"real.py"})

    elements = [e["payload"] for e in events if e["kind"] == "SuspectElements"]
    assert len(elements) == 1
    assert list(elements[0]["elements"]) == ["real"]


async def test_element_localizer_model_error_records_producer_failed(tmp_path):  # type: ignore[no-untyped-def]
    # 2026-08-09 halt-on-error contract: a failed LLM call in the element localizer propagates.
    # The producer dies, the kernel records ProducerFailed, and no SuspectFiles/SuspectElements/
    # EditLocations emit. Runner sees an incomplete cell and halts the sweep.
    class _Dying:
        def respond(self, prompt: str) -> str:
            raise RuntimeError("model died mid-localize")

    checkout = tmp_path / "repo"
    _write_repo(checkout, {"any.py": "def any():\n    pass\n"})
    events = await _run(tmp_path, _Dying(), "fix", "any.py", checkout, {"any.py"})

    assert any(e["kind"] == "substrate.ProducerFailed" for e in events), (
        "localizer model error must record ProducerFailed"
    )
    assert not any(e["kind"] == "SuspectFiles" for e in events), (
        "no fake empty-SuspectFiles cover for a real crash"
    )
    assert not any(e["kind"] == "EditLocations" for e in events)


async def test_element_localizer_syntax_error_file_stays_as_whole_file_target(tmp_path):  # type: ignore[no-untyped-def]
    # A Python file with a syntax error → extract_elements returns [] → the file falls through
    # to the whole-file branch and stays in EditLocations. Not silently dropped.
    checkout = tmp_path / "repo"
    _write_repo(checkout, {"broken.py": "def bad(:\n    pass\n"})
    responder = DeterministicResponder(seed=0, menu=["broken.py"])
    events = await _run(tmp_path, responder, "fix", "broken.py", checkout, {"broken.py"})

    assert not any(e["kind"] == "SuspectElements" for e in events)
    locs = [e["payload"] for e in events if e["kind"] == "EditLocations"]
    assert list(locs[0]["targets"]) == ["broken.py"]
