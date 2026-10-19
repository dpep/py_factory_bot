#!/usr/bin/env bash
# Full gate: tests, lint, format. Run before every commit.
set -euo pipefail
cd "$(dirname "$0")/.."
bin=.venv/bin
[ -x "$bin/pytest" ] || bin=$(dirname "$(command -v python)")

"$bin/pytest" -q "$@"
"$bin/ruff" check .
"$bin/ruff" format --check .
