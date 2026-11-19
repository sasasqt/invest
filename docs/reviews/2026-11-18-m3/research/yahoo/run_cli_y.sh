#!/usr/bin/env bash
set -euo pipefail
DATA="$1"; OUT="$2"
B=${INVEST:?set INVEST to an invest checkout at eb64ad8}/.venv/bin
CFG=${EVAL_CONFIG:?set EVAL_CONFIG to the historical workflow's eval config}
mkdir -p "$OUT"
i=0
while IFS= read -r expr; do
  [[ -z "$expr" ]] && continue
  i=$((i+1))
  $B/invest-mine freeze --expr "$expr" --horizon 5 --orientation -1 --out "$OUT/f$i.json" > /dev/null
  $B/invest-mine export --data "$DATA/market" --factor "$OUT/f$i.json" --format parquet --out "$OUT/sig$i" > /dev/null &
done < "$(dirname "$0")/exprs.txt"
for expr in "close / delay(close, 5) - 1" "cs_rank(dollar_volume)"; do
  i=$((i+1))
  $B/invest-mine evaluate --data "$DATA/market" --expr "$expr" --horizon 5 --orientation -1 \
    --min-cross-section 10 --out "$OUT/diag$i" > /dev/null &
done
wait
$B/invest-eval run --data "$DATA/market" --signals "$OUT/sig1" --config "$CFG" --no-scenarios --out "$OUT/eval" > /dev/null &
$B/invest-eval quantiles --data "$DATA/market" --signals "$OUT/sig1" --config "$CFG" --out "$OUT/quant" > /dev/null &
wait
echo "done $OUT"
