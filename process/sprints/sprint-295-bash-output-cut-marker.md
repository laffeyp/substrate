# Sprint 295 — `bash` says when it cut its output

```yaml
---
id: 295
status: closed
closed_at: 2026-10-11
phase: 1
pass_kind: functional
roadmap: substrate-ui/process/planning/ROADMAP-2026-10-11-before-distribution.md (step 3)
asked: 2026-10-11 (Architect)
---
```

## scope

- `bash` returns the first 8,000 bytes of stdout and the last 2,000 characters of stderr with nothing to say either was cut (`tools.py:513`, `:536`). In the K293 live run, `kimi-k2.7-code:cloud` read 222 lines of a 4,000-line file and answered 222. When either is cut, the result says so: how much was kept of how much, and where the full output is on disk.

## checks

- A command printing more than 8,000 bytes returns the first 8,000 and a line naming the total and the file; the file holds all of it. Short output has no marker.

## result

- **Built** (`tools.py` `_bash`). When stdout passes 8,000 bytes, the result ends with `[bash: stdout cut to its first 8,000 of <N> bytes; the whole output is in <file>. Read it with read_file, or narrow the command with head, tail or grep]`. When stderr passes 2,000 characters, it starts with `[bash: stderr cut to its last 2,000 of <N> characters; the whole of it is in <file>]`. The limits are named constants, `_BASH_STDOUT_BYTES` and `_BASH_STDERR_CHARS`. Background tasks are unchanged: `bash_output` already pages by offset.
- **Tests.** `test_bash_cut_marker_295.py`, 3 of 3: `seq 1 4000` returns the first 8,000 bytes, a marker naming 18,893 bytes, and a file whose last line is 4000; long stderr is marked; short output has no marker. Bash and tool tests: 136 passed.

