"""Sprint 270: a process as a Producer, and a topology from a TOML file.

The emitting program in these tests is /bin/sh with printf: the program's side needs no Python."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from substrate import api, app

SCHEMAS = {
    "schema_version": 1,
    "kinds": {
        "SESSION_INIT": {
            "vocab_version": {"type": "str", "pattern": r"^[0-9]+\.[0-9]+(\.[0-9]+)?$"},
            "profile": {"type": "str", "min_length": 1},
            "purpose": {"type": "str", "enum": ["conformance", "measurement"]},
        },
        "SESSION_COMPLETED": {
            "discrepancy_count": {"type": "int", "ge": 0},
            "elapsed_seconds": {"type": "float"},
            "note": {"type": "str", "optional": True},
        },
    },
}
INIT = {"vocab_version": "0.9", "profile": "w2m-session-check", "purpose": "conformance"}
DONE = {"discrepancy_count": 0, "elapsed_seconds": 0.25}


def _line(kind: str, payload: dict[str, Any]) -> str:
    return json.dumps({"kind": kind, "payload": payload})


def _printf(*lines: str, status: int = 0) -> list[str]:
    script = "".join(f"printf '%s\\n' {shlex.quote(s)}; " for s in lines) + f"exit {status}"
    return ["/bin/sh", "-c", script]


def _schemas(tmp_path: Path) -> Path:
    path = tmp_path / "schemas.json"
    path.write_text(json.dumps(SCHEMAS))
    return path


def _topology(command: list[str], schema_path: Path) -> Any:
    version, schemas = app.schemas_from_file(schema_path)
    produce = app.process_producer(command, schemas)

    def topology(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "emitter",
            schemas=list(schemas.values()),
            schema_version=version,
            factory=lambda: produce,
        )
        b.initial("emitter")
        b.termination(api.all_completed())

    return topology


def _events(root: Path) -> list[dict[str, Any]]:
    return list(api.read_record(root))


def _app_events(root: Path) -> list[tuple[str, Any]]:
    return [
        (e["kind"], e["payload"]) for e in _events(root) if not e["kind"].startswith("substrate.")
    ]


def _failures(root: Path) -> list[str]:
    return [
        str(e["payload"].get("error")) for e in _events(root) if e["kind"] == api.PRODUCER_FAILED
    ]


@pytest.mark.asyncio
async def test_a_process_events_reach_the_record_field_for_field(tmp_path: Path) -> None:
    command = _printf(_line("SESSION_INIT", INIT), _line("SESSION_COMPLETED", DONE))
    result = await api.Runtime(tmp_path / "r").run(_topology(command, _schemas(tmp_path)))
    assert result.status == "finalised"
    # an optional field the process leaves out is null on the record, as a hand-written Struct with a None default
    assert _app_events(tmp_path / "r") == [
        ("SESSION_INIT", INIT),
        ("SESSION_COMPLETED", DONE | {"note": None}),
    ]
    assert _failures(tmp_path / "r") == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("bad", "names"),
    [
        ("not json", "line 2"),
        (_line("SESSION_STARTED", INIT), "line 2: kind 'SESSION_STARTED' is not in the schemas"),
        (_line("SESSION_COMPLETED", {"elapsed_seconds": 0.5}), "discrepancy_count"),
        (_line("SESSION_COMPLETED", DONE | {"extra": 1}), "extra"),
        (_line("SESSION_INIT", INIT | {"purpose": "fishing"}), "purpose"),
        (_line("SESSION_INIT", INIT | {"vocab_version": "nine"}), "vocab_version"),
        (_line("SESSION_COMPLETED", DONE | {"discrepancy_count": -1}), "discrepancy_count"),
    ],
    ids=[
        "not-json",
        "unknown-kind",
        "missing-field",
        "extra-field",
        "bad-enum",
        "pattern-miss",
        "below-ge",
    ],
)
async def test_a_malformed_line_fails_the_producer_naming_it(
    tmp_path: Path, bad: str, names: str
) -> None:
    command = _printf(_line("SESSION_INIT", INIT), bad, _line("SESSION_COMPLETED", DONE))
    await api.Runtime(tmp_path / "r").run(_topology(command, _schemas(tmp_path)))
    failures = _failures(tmp_path / "r")
    assert len(failures) == 1 and "line 2" in failures[0] and names in failures[0], failures
    # the line before the bad one is on the record; nothing after it is
    assert [k for k, _ in _app_events(tmp_path / "r")] == ["SESSION_INIT"]


@pytest.mark.asyncio
async def test_a_nonzero_exit_fails_the_producer_with_its_status(tmp_path: Path) -> None:
    command = [
        "/bin/sh",
        "-c",
        f"printf '%s\\n' {shlex.quote(_line('SESSION_INIT', INIT))}; echo why >&2; exit 3",
    ]
    await api.Runtime(tmp_path / "r").run(_topology(command, _schemas(tmp_path)))
    failures = _failures(tmp_path / "r")
    assert len(failures) == 1 and "exited with status 3" in failures[0] and "why" in failures[0], (
        failures
    )


@pytest.mark.asyncio
async def test_the_input_reaches_the_process_on_standard_input(tmp_path: Path) -> None:
    # the process echoes its input's profile back as a SESSION_INIT
    script = (
        'read line; profile=$(printf \'%s\' "$line" | sed \'s/.*"profile": *"\\([^"]*\\)".*/\\1/\'); '
        'printf \'{"kind": "SESSION_INIT", "payload": {"vocab_version": "0.9", "profile": "%s", '
        '"purpose": "measurement"}}\\n\' "$profile"'
    )
    version, schemas = app.schemas_from_file(_schemas(tmp_path))
    produce = app.process_producer(["/bin/sh", "-c", script], schemas)

    def topology(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "emitter",
            schemas=list(schemas.values()),
            schema_version=version,
            factory=lambda: produce,
        )
        b.initial("emitter", input={"profile": "from-stdin"})
        b.termination(api.all_completed())

    await api.Runtime(tmp_path / "r").run(topology)
    assert _app_events(tmp_path / "r") == [
        (
            "SESSION_INIT",
            {"vocab_version": "0.9", "profile": "from-stdin", "purpose": "measurement"},
        )
    ]


@pytest.mark.asyncio
async def test_a_record_from_a_process_replays(tmp_path: Path) -> None:
    command = _printf(_line("SESSION_INIT", INIT), _line("SESSION_COMPLETED", DONE))
    await api.Runtime(tmp_path / "r").run(_topology(command, _schemas(tmp_path)))
    result = api.assert_replayable(tmp_path / "r", "2")
    assert result.complete and not result.mismatches


def _write_topology_file(tmp_path: Path, command: list[str]) -> Path:
    _schemas(tmp_path)
    path = tmp_path / "topology.toml"
    path.write_text(
        '[baseline]\nharness = "test"\n\n'
        f'[[producer]]\nkind = "emitter"\ncommand = {json.dumps(command)}\nschemas = "schemas.json"\n\n'
        '[[initial]]\nkind = "emitter"\n\n'
        '[termination]\nrecipe = "all_completed"\n'
    )
    return path


@pytest.mark.asyncio
async def test_a_topology_file_gives_the_same_events_as_the_same_topology_in_python(
    tmp_path: Path,
) -> None:
    command = _printf(_line("SESSION_INIT", INIT), _line("SESSION_COMPLETED", DONE))
    await api.Runtime(tmp_path / "py").run(_topology(command, _schemas(tmp_path)))
    await api.Runtime(tmp_path / "file").run(
        app.topology_from_file(_write_topology_file(tmp_path, command))
    )
    assert _app_events(tmp_path / "file") == _app_events(tmp_path / "py")


def test_run_file_on_the_command_line(tmp_path: Path) -> None:
    command = _printf(_line("SESSION_INIT", INIT), _line("SESSION_COMPLETED", DONE))
    path = _write_topology_file(tmp_path, command)
    out = subprocess.run(
        [
            sys.executable,
            "-m",
            "substrate.cli",
            "run",
            "--file",
            str(path),
            "--root",
            str(tmp_path / "r"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().endswith(str(tmp_path / "r"))
    assert [k for k, _ in _app_events(tmp_path / "r")] == ["SESSION_INIT", "SESSION_COMPLETED"]


@pytest.mark.parametrize(
    ("text", "names"),
    [
        ('[[initial]]\nkind = "x"\n[termination]\nrecipe = "all_completed"\n', "no [[producer]]"),
        (
            '[[producer]]\nkind = "x"\ncommand = ["/bin/true"]\nschemas = "schemas.json"\n'
            '[[initial]]\nkind = "y"\n[termination]\nrecipe = "all_completed"\n',
            "kind 'y' is not a [[producer]]",
        ),
        (
            '[[producer]]\nkind = "x"\ncommand = ["/bin/true"]\nschemas = "schemas.json"\n'
            '[[initial]]\nkind = "x"\n[termination]\nrecipe = "forever"\n',
            "recipe 'forever'",
        ),
    ],
    ids=["no-producer", "unknown-initial", "unknown-recipe"],
)
def test_a_bad_topology_file_is_refused_before_a_run(tmp_path: Path, text: str, names: str) -> None:
    _schemas(tmp_path)
    path = tmp_path / "topology.toml"
    path.write_text(text)
    with pytest.raises(app.TopologyFileError, match=__import__("re").escape(names)):
        app.topology_from_file(path)
