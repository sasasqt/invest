#!/usr/bin/env bash
# Prepare -> mine -> export -> evaluate on the deterministic synthetic market.
#
# Usage: uv run scripts/synthetic_workflow.sh [OUT_DIR]
# Every step reads only artifacts published by the previous one; no ids or dates are
# copied by hand. Sizes can be reduced for quick runs with INSTRUMENTS, DAYS, TRIALS.
set -euo pipefail

out="${1:-artifacts/synthetic-workflow}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
instruments="${INSTRUMENTS:-60}"
days="${DAYS:-750}"
trials="${TRIALS:-200}"
config="${CONFIG:-$root/strategy-evaluation/examples/quantile_long_short.json}"

invest-data synthetic --out "$out/data/market" --format parquet \
  --instruments "$instruments" --days "$days" \
  --universe-out "$out/data/universe" --fundamentals-out "$out/data/fundamentals"

invest-mine search --data "$out/data/market" --universe "$out/data/universe" \
  --trials "$trials" --out "$out/mining/search"

# The best confirmed factor, from the first confirmation date onwards.
invest-mine export --data "$out/data/market" --universe "$out/data/universe" \
  --from-search "$out/mining/search" --format parquet --out "$out/signals"

# The deflated Sharpe uses the number of search proposals recorded in the signals bundle.
invest-eval run --data "$out/data/market" --universe "$out/data/universe" \
  --signals "$out/signals" --config "$config" --out "$out/eval"
