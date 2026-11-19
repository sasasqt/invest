#!/usr/bin/env bash
# Run the mining and evaluation CLIs on one set of bundles (DATA dir holds market/,
# universe/, fundamentals/) into OUT. SIG_FOR_EVAL optionally names a signals bundle to
# backtest instead of the one exported here (to isolate the engine from the signals).
set -euo pipefail
DATA="$1"; OUT="$2"; SIG_FOR_EVAL="${3:-}"
B=${INVEST:?set INVEST to an invest checkout at eb64ad8}/.venv/bin
CFG=${INVEST:?set INVEST to an invest checkout at eb64ad8}/strategy-evaluation/examples/quantile_long_short.json
mkdir -p "$OUT"
i=0
while IFS= read -r expr; do
  [[ -z "$expr" ]] && continue
  i=$((i+1))
  $B/invest-mine freeze --expr "$expr" --horizon 5 --out "$OUT/f$i.json" > /dev/null
  $B/invest-mine export --data "$DATA/market" --universe "$DATA/universe" \
    --fundamentals "$DATA/fundamentals" --factor "$OUT/f$i.json" --out "$OUT/sig$i" > /dev/null &
done < "$(dirname "$0")/exprs.txt"
for expr in "cs_rank(fund_book_to_price)" "close / delay(close, 5) - 1"; do
  i=$((i+1))
  $B/invest-mine evaluate --data "$DATA/market" --universe "$DATA/universe" \
    --fundamentals "$DATA/fundamentals" --expr "$expr" --horizon 5 --orientation -1 \
    --min-cross-section 10 --out "$OUT/diag$i" > /dev/null &
done
wait
SIG="${SIG_FOR_EVAL:-$OUT/sig1}"
$B/invest-eval run --data "$DATA/market" --signals "$SIG" --universe "$DATA/universe" \
  --config "$CFG" --no-scenarios --out "$OUT/eval" > /dev/null &
$B/invest-eval quantiles --data "$DATA/market" --signals "$SIG" --universe "$DATA/universe" \
  --config "$CFG" --out "$OUT/quant" > /dev/null &
wait
echo "done $OUT"
