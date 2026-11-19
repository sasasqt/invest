#!/usr/bin/env bash
# (1) invest-eval never compares the signals' market with --data: signals exported on
#     synthetic-7 run on synthetic-8 (other id, other prices) with exit 0, no warning, and the
#     factor's confirmation_passed beside the portfolio verdict; the eval manifest records the
#     signals' metadata but not their market id, so the record cannot show it either.
# (2) the documented synthetic workflow mines/confirms at horizon 1 (search default) and
#     evaluates with rebalance_every 5; nothing compares horizon_days with the holding period.
set -euo pipefail
R=${OUT:?set OUT to a scratch folder}
W=$R/work   # syn7, uni7, syn8, uni8, search7, sig7 made by the setup commands in NOTES.md
B=${INVEST:?set INVEST to an invest checkout at eb64ad8}/.venv/bin
CFG=${INVEST:?set INVEST to an invest checkout at eb64ad8}/strategy-evaluation/examples/quantile_long_short.json
rm -rf "$W/x_eval_on8"
$B/invest-eval run --data "$W/syn8" --universe "$W/uni8" --signals "$W/sig7" --config "$CFG" --out "$W/x_eval_on8" > "$W/x_eval_on8.stdout" 2> "$W/x_eval_on8.stderr"; echo "exit=$?"
cat "$W/x_eval_on8.stdout"; echo "stderr bytes: $(wc -c < "$W/x_eval_on8.stderr")"
$B/python - "$W" <<'PY'
import json, sys
w = sys.argv[1]
sig = json.load(open(f"{w}/sig7/manifest.json"))
ev = json.load(open(f"{w}/x_eval_on8/manifest.json"))
print("signals provenance market_dataset_id:", sig["provenance"]["market_dataset_id"])
print("eval --data id:", ev["market_dataset"]["id"])
print("eval manifest keys under signals:", sorted(ev["signals"]), "-> market id of the signals recorded:",
      "market_dataset_id" in json.dumps(ev["signals"]))
print("eval warnings:", ev["warnings"])
print("expected: refusal or at least a warning that the signals were scored on synthetic-7, not synthetic-8")
v = json.load(open(f"{w}/x_eval_on8/verdict.json"))
cfg = json.load(open(f"{w}/x_eval_on8/config.json"))
print("(2) factor evidence horizon_days:", v["factor"]["horizon_days"], "| signals horizon_days:", sig["metadata"]["horizon_days"],
      "| backtest rebalance_every:", cfg["strategy"]["rebalance_every"], "| delay:", cfg["execution"]["delay"])
PY
grep -c -i "horizon" "$W/x_eval_on8/report.md" | sed 's/^/report.md lines mentioning horizon: /' || true
