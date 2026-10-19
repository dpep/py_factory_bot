#!/usr/bin/env bash
# Full gate: tests, types, lint, format. Run before every commit.
set -euo pipefail
cd "$(dirname "$0")/.."
bin=.venv/bin
[ -x "$bin/pytest" ] || bin=$(dirname "$(command -v python)")

"$bin/coverage" run -m pytest -q "$@"
"$bin/coverage" report
"$bin/pyright" --pythonpath "$bin/python"
"$bin/ruff" check .
"$bin/ruff" format --check .
