#!/usr/bin/env bash
# One copy of the status-literal gate, run by both repos' pre-commit hooks.
# A status is compared against its enum (SessionStatus, TaskStatus, RunStatus; the generated
# web/vm/statuses.gen.ts in the client), never a retyped string that silently stops matching after
# a rename. Matches ==, !=, ===, !== against a status word in single OR double quotes, in .py, .ts
# and .tsx (lens audit F292: the old gate saw double quotes and Python only).
# Usage: check_status_literals.sh <path>...   (exit 1 and print the lines on a hit)
# Source only: a test asserting a JSON body's "status" against its wire string checks the contract.
set -u
WORDS='ended|parked|interrupted|running|exited|stopped|incomplete|paused|finalised|failed|live'
RE="[=!]==? *[\"'](${WORDS})[\"']|[\"'](${WORDS})[\"'] *[=!]==?"
# reveal_component.ts is the dc-runtime shell UI sprint 112 replaces; the exclusion leaves with it.
if grep -rnE --include='*.py' --include='*.ts' --include='*.tsx' \
     --exclude='*.gen.ts' --exclude='reveal_component.ts' --exclude-dir=dist --exclude-dir=node_modules \
     "$RE" "$@" 2>/dev/null; then
  echo "  ^^ Compare against SessionStatus.* / TaskStatus.* / RunStatus.* (or the generated client enums) instead."
  exit 1
fi
exit 0
