#!/usr/bin/env bash
# Test-only historical workflow on Yahoo Finance daily bars:
# snapshot -> publish -> freeze a fixed formula -> export -> evaluate against SPY.
#
# Usage: uv run scripts/historical_workflow.sh [OUT_DIR]
#
# The raw Yahoo responses are saved once under "$SNAPSHOT" (default OUT_DIR/snapshot).
# If that snapshot already exists, nothing is downloaded and every later step replays it
# offline. START/END select an inclusive subset within the saved request; without them,
# replay uses the saved request dates and publishes the same dataset hash.
#
# Defaults: today's S&P 100 members (SURVIVORSHIP-BIASED: names chosen today and applied to
# all history), 2010-01-01 to 2024-12-31, SPY as the benchmark, and the 5-day reversal
# formula frozen a priori (n_trials = 1) with the example quantile long-short config.
# Override with SYMBOLS_FILE (download only), START, END, BENCHMARK, SNAPSHOT, CONFIG.
set -euo pipefail

out="${1:-artifacts/historical-workflow}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
symbols_file="${SYMBOLS_FILE:-$root/scripts/sp100_members.txt}"
start="${START:-2010-01-01}"
end="${END:-2024-12-31}"
benchmark="${BENCHMARK:-SPY}"
snapshot="${SNAPSHOT:-$out/snapshot}"
config="${CONFIG:-$root/strategy-evaluation/examples/quantile_long_short.json}"
expr="close / delay(close, 5) - 1"

if [[ -f "$snapshot/snapshot.json" ]]; then
  echo "Replaying existing snapshot $snapshot (no download)" >&2
else
  invest-data yahoo download --snapshot "$snapshot" --symbols-file "$symbols_file" \
    --symbols "$benchmark" --start "$start" --end "$end"
fi

# Resolve labels from the actual saved request, and validate overrides before publication.
range="$(python - "$snapshot" "${START:-}" "${END:-}" <<'PY'
import sys
from invest_data.yahoo import snapshot_range
print(*snapshot_range(sys.argv[1], sys.argv[2] or None, sys.argv[3] or None))
PY
)"
read -r start end <<< "$range"

invest-data yahoo publish --snapshot "$snapshot" --exclude "$benchmark" --format parquet \
  --start "$start" --end "$end" \
  --dataset-id "yahoo-test-$start-$end" --out "$out/data/market" \
  --universe-note "saved snapshot members applied to all history (survivorship-biased)"
invest-data yahoo publish --snapshot "$snapshot" --symbols "$benchmark" --format parquet \
  --start "$start" --end "$end" \
  --dataset-id "yahoo-test-$benchmark-$start-$end" --out "$out/data/benchmark" \
  --universe-note "benchmark ETF"

# Descriptive factor diagnostics on the full sample (not a confirmatory test).
invest-mine evaluate --data "$out/data/market" --expr "$expr" --horizon 5 \
  --out "$out/mining/diagnostics"

# A fixed formula chosen before looking at this data: low past 5-day return = attractive.
invest-mine freeze --expr "$expr" --horizon 5 --orientation -1 --out "$out/mining/factor.json"
invest-mine export --data "$out/data/market" --factor "$out/mining/factor.json" \
  --format parquet --out "$out/signals"

invest-eval run --data "$out/data/market" --signals "$out/signals" --config "$config" \
  --benchmark "$out/data/benchmark" --out "$out/eval"
