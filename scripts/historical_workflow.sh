#!/usr/bin/env bash
# Test-only historical workflow on Yahoo Finance daily bars:
# snapshot -> publish -> freeze a fixed formula -> export -> evaluate against SPY
# -> decile and tail portfolios.
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
#
# LEDGER (default ledgers/yahoo-test.jsonl) is the market's confirmation-use ledger. This
# workflow inspects every date it publishes, so it refuses any window that touches the
# reserved confirmation period (2025-01-01 onward) before downloading or publishing.
#
# RECORD (optional, e.g. runs/yahoo-test/2026-10-08) saves the run's small record (reports,
# verdicts, metrics, figures, manifests; no vendor data) there for committing, with
# scripts/save_run.py. It must not exist yet, and the checkout must be clean (no uncommitted
# changes to tracked files, no untracked files Git does not ignore, and the outputs outside
# the checkout or under a folder it ignores) so the recorded code revision describes the
# code that ran; save_run.py also refuses incomplete outputs and evaluation or quantile
# manifests without a clean code revision. A window the ledger does not yet record as
# inspected is recorded first and the run stops before publishing: commit the ledger, then
# rerun with the same settings (the saved snapshot replays offline).
set -euo pipefail

out="${1:-artifacts/historical-workflow}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
symbols_file="${SYMBOLS_FILE:-$root/scripts/sp100_members.txt}"
start="${START:-2010-01-01}"
end="${END:-2024-12-31}"
benchmark="${BENCHMARK:-SPY}"
snapshot="${SNAPSHOT:-$out/snapshot}"
config="${CONFIG:-$root/strategy-evaluation/examples/quantile_long_short.json}"
ledger="${LEDGER:-$root/ledgers/yahoo-test.jsonl}"
expr="close / delay(close, 5) - 1"
orientation=-1
record="${RECORD:-}"

if [[ -n "$record" ]]; then
  if [[ -e "$record" ]]; then
    echo "RECORD $record already exists; run records are never overwritten" >&2
    exit 1
  fi
  if [[ -n "$(git -C "$root" status --porcelain --untracked-files=normal)" ]]; then
    echo "RECORD needs a clean checkout: commit changes to tracked files, and commit, remove or ignore untracked files first" >&2
    exit 1
  fi
  # Outputs inside the checkout that Git does not ignore would be untracked files by the
  # time the evaluation records code_dirty, and save_run.py would refuse the finished run.
  for dir in "$out" "$snapshot"; do
    # Written without a newline (a Windows Python ends a line in CRLF, which command
    # substitution keeps) and with forward slashes, which Git takes on every platform.
    abs="$(python -c 'import os, sys; sys.stdout.write(os.path.abspath(sys.argv[1]).replace(os.sep, "/"))' "$dir")"
    # Asked about as a folder (trailing slash), so that a directory-only pattern such as
    # /artifacts/ matches the folder itself before it exists.
    git -C "$root" check-ignore -q -- "$abs/" 2> /dev/null && continue
    if [[ $? -eq 1 ]]; then
      echo "RECORD needs the outputs outside the checkout or under a folder Git ignores (such as artifacts/): $dir is neither" >&2
      exit 1
    fi
  done
fi

if [[ -f "$snapshot/snapshot.json" ]]; then
  echo "Replaying existing snapshot $snapshot (no download)" >&2
else
  invest-mine ledger check --ledger "$ledger" --start "$start" --end "$end" > /dev/null
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
invest-mine ledger check --ledger "$ledger" --start "$start" --end "$end" > /dev/null

if [[ -n "$record" ]]; then
  # The diagnostics record the market bundle's dates in the ledger unless an inspection
  # already covers them. That append modified the tracked ledger before the evaluation
  # recorded code_dirty, so save_run.py refused every record of a new window (K3). Record
  # the inspection now and stop instead, so that the ledger is committed before the run.
  # The selection and cleaning below mirror `invest-data yahoo publish --exclude` (_yahoo
  # and _publish in invest_data/cli.py); a change there needs the same change here.
  python - "$snapshot" "$benchmark" "$start" "$end" "$ledger" <<'PY'
import sys

from invest_data.cleaning import clean_bars
from invest_data.yahoo import load_snapshot, read_snapshot_manifest
from invest_mining import ledger

snapshot, benchmark, start, end, path = sys.argv[1:]
symbols = [s for s in read_snapshot_manifest(snapshot)["files"] if s != benchmark]
raw, _ = load_snapshot(snapshot, symbols, start=start, end=end)
bars, _ = clean_bars(raw)
window = ledger.Window(bars["date"].min().date(), bars["date"].max().date())
if not ledger.is_inspected(ledger.load(path), window):
    ledger.append(
        path,
        "inspection",
        {
            "window": window.to_json(),
            "dataset_id": f"yahoo-test-{start}-{end}",
            "note": "invest-mine evaluate (full sample); recorded by the RECORD run before "
            "it started, so that the ledger is committed first",
        },
    )
    sys.exit(
        f"RECORD: {path} now records {window} as inspected; commit it, then rerun with the "
        "same settings (the saved snapshot replays offline; a ledger outside the checkout, or "
        "under a folder Git ignores, needs no commit)"
    )
PY
fi

invest-data yahoo publish --snapshot "$snapshot" --exclude "$benchmark" --format parquet \
  --start "$start" --end "$end" \
  --dataset-id "yahoo-test-$start-$end" --out "$out/data/market" \
  --universe-note "saved snapshot members applied to all history (survivorship-biased)"
invest-data yahoo publish --snapshot "$snapshot" --symbols "$benchmark" --format parquet \
  --start "$start" --end "$end" \
  --dataset-id "yahoo-test-$benchmark-$start-$end" --out "$out/data/benchmark" \
  --universe-note "benchmark ETF"

# Yahoo's closes are adjusted for every later split and dividend, and the snapshot cannot
# undo splits after its window, so these bars carry no as-traded close. A minimum-price rule
# would then let later corporate actions decide earlier eligibility, so evaluation uses a
# copy of CONFIG with execution.min_price = 0.
eval_config="$out/eval-config.json"
# Prints the portfolios' minimum cross-section, used by the diagnostics below.
min_names="$(python - "$config" "$eval_config" <<'PY'
import json
import sys
from invest_evaluation.config import BacktestConfig

config = BacktestConfig.load(sys.argv[1])
raw = json.loads(open(sys.argv[1]).read())
raw.setdefault("execution", {})["min_price"] = 0.0
if config.execution.min_price:
    print(
        f"note: execution.min_price {config.execution.min_price} -> 0 (no as-traded close)",
        file=sys.stderr,
    )
with open(sys.argv[2], "w") as out:
    json.dump(raw, out, indent=2)
print(config.strategy.min_names)
PY
)"

# Descriptive factor diagnostics on the full sample (not a confirmatory test); the ledger
# records the inspected window unless it is already recorded. Use the frozen orientation
# so q10 and the top tails mean the same score direction in both reports, and the
# portfolios' minimum cross-section (applied to scored names here, eligible names there).
invest-mine evaluate --data "$out/data/market" --expr "$expr" --horizon 5 \
  --orientation "$orientation" --min-cross-section "$min_names" \
  --ledger "$ledger" --out "$out/mining/diagnostics"

# A fixed formula chosen before looking at this data: low past 5-day return = attractive.
invest-mine freeze --expr "$expr" --horizon 5 --orientation "$orientation" \
  --out "$out/mining/factor.json"
invest-mine export --data "$out/data/market" --factor "$out/mining/factor.json" \
  --format parquet --out "$out/signals"

invest-eval run --data "$out/data/market" --signals "$out/signals" --config "$eval_config" \
  --benchmark "$out/data/benchmark" --out "$out/eval"

# Every decile and the top/bottom 1/5/10% tails as separate backtests with the same costs
# and timing; slices with fewer than five names on a decision report insufficient_data.
invest-eval quantiles --data "$out/data/market" --signals "$out/signals" --config "$eval_config" \
  --out "$out/quantiles"

if [[ -n "$record" ]]; then
  python "$root/scripts/save_run.py" "$out" "$record" --snapshot "$snapshot"
fi
