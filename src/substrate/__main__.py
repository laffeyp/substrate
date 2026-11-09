# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""`python -m substrate` runs the `substrate` command through the interpreter that installed it, so
the command works when the install's script folder is not on PATH."""

from substrate.cli import main

main()
