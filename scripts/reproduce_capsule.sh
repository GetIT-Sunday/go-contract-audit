#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-${TMPDIR:-/tmp}/goaudit-capsule-result.json}"
if [[ -e "$OUT" ]]; then
  echo "Refusing to overwrite existing output: $OUT" >&2
  exit 2
fi
cd "$ROOT/examples/diagnosis_capsule"
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" audit_examples.py audit --out "$OUT"
"$PYTHON_BIN" audit_examples.py check --out "$OUT"
